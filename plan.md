# EVEmu Crucible — Private Server Redirection Plan

**Date:** 2026-07-07
**Status:** Planning phase
**Goal:** Redirect this fork toward a stable, private-use server simulating the Crucible era of EVE Online, with (1) a hardened core, (2) a web GUI providing server-wide console controls over the simulated environment, and (3) an AI engine simulating NPCs and NPC player characters so the server feels populated.

---

## TL;DR

The codebase is a mature but fragile single-threaded C++ monolith. The three goals map well onto infrastructure that already exists (CommandDispatcher, APIServer, MarketBot). The right redirection is **not** to build new features into the monolith — it is to treat the C++ core as a "space simulation kernel," stabilize it, and build the web GUI and AI engine as satellite services that talk to it through a new admin API.

One architectural insight ties everything together: **a headless protocol-level bot client is simultaneously the stability test harness and the NPC-player engine.**

---

## 1. Current-state assessment

- **~350 .cpp / ~410 .h files** across `eve-core`, `eve-common`, `eve-server`, plus tooling (`eve-tool`, `eve-xmlpktgen`, a thin `eve-test`). MariaDB 11.4 backend, Docker Compose deployment.
- **Single-threaded game loop** — `src/eve-server/eve-server.cpp` (~line 911) runs `sEntityList.Process()` then `sConsole.Process()` in one loop. Singletons everywhere. One bad pointer anywhere takes down the whole universe. Recent commit history (`ProcessWander` segfault, mission-offer crash, destiny distance overflow) shows crashes concentrate in the destiny/physics and spawn systems.
- **Console control exists but is primitive:** `ConsoleCommands` is a blocking stdin reader wired into `CommandDispatcher`, which already routes a large library of GM/slash commands with permission levels (`src/eve-server/admin/`). This is the biggest existing asset for the GUI goal.
- **APIServer** (`src/eve-server/apiserver/`) emulates the old EVE XML API — an existing embedded HTTP listener pattern to crib from, though it is read-only character/corp data, not a control plane.
- **MarketBot ("Trader Joe")** is a working in-process economic NPC actor (PR #303) — precedent for simulated players.
- **NPC AI** is a per-entity enum state machine (Idle/Chasing/Following/Engaged, ~900 lines in `src/eve-server/npc/NPCAI.cpp`). Functional for combat rats; no goals, no persistence, no life outside loaded systems. **Systems only tick when a player is in them** — the core obstacle to a "living universe."
- **Almost no test coverage** (`eve-test` covers marshal/auth/utils only); CI is a single cmake workflow. There is no automated way to know a change didn't break undock/warp/dock.

## 2. Strategic redirection

### Guiding principle: stop growing the monolith — harden it and put seams around it

Every new feature added in-process (the MarketBot pattern) increases crash surface in a process that already segfaults. The C++ server's job is *simulating space*. Control, observation, and population simulation become external services with defined interfaces. This "strangler" approach means the fragile core changes as little as possible while new capabilities live where a crash can't kill the universe.

### Pillar 1 — Stability (first; everything else depends on it)

1. **Define the Crucible feature matrix.** Write down what "done" means: which Crucible-era systems must work (market, missions, mining, PvP, POS, PI, ...) and — just as important — what is explicitly out of scope. This freezes scope creep, the historical killer of emulator projects.
2. **Sanitizer builds + crash capture.** Add ASan/UBSan CMake presets and a CI job; run the docker server under them in a nightly soak. The destiny/spawn crash class (`ProcessWander`-style dangling pointers) is exactly what ASan finds in hours instead of months.
3. **Build the headless smoke-test bot.** A minimal client that speaks the real protocol (the marshal code in `eve-common` and packet definitions in `eve-xmlpktgen` already define it): log in → create character → undock → warp → dock. Run it against the docker stack in CI. *This artifact becomes the foundation of the AI engine in Pillar 3* — that dual use is why it is worth the upfront cost.
4. **Watchdog + state safety.** Auto-restart on crash (docker `restart: unless-stopped` plus a health endpoint), and audit that periodic DB saves leave consistent state so a crash costs minutes, not a corrupted universe. For private use, "crashes but recovers cleanly in 30 seconds" is 90% of perceived stability.
5. **Fix top crashers only.** Resist refactoring the loop or threading model. Single-threaded is fine for a private server — it is a *feature* for debuggability.

### Pillar 2 — Web GUI with server-wide console controls

**Inside the C++ server, add one thing only:** an embedded admin HTTP + WebSocket endpoint (civetweb or similar, following the existing `APIServer` listener pattern) with token auth, exposing:

- `POST /admin/command` → routes straight into the existing `CommandDispatcher` (inherits the entire GM command library — spawn NPCs, teleport, adjust standings, kick, broadcast — for free);
- `GET /admin/status` → what `ConsoleCommands::UpdateStatus()` and `StatisticMgr` already collect (players online, loaded systems, memory, tick time);
- WebSocket log stream (tap `sLog`) — the "server-wide console" in the browser;
- config live-tuning via the existing `LiveUpdateDB`/`sConfig` machinery (rates, spawn timers, event toggles).

**Everything else is a separate web app** (React/Svelte frontend + thin backend) that talks to that admin API for control and reads MariaDB directly for dashboards: live map of loaded systems, economy graphs, market browser, character/entity inspector, event scheduler ("trigger incursion in Amarr space at 20:00"). It can restart the server, roll back DB snapshots, and stays up when the server is down — which an in-process GUI never could.

### Pillar 3 — AI engine: two tiers, one director

- **Tier 1 — In-process/DB-level ambient simulation (cheap, start here):** extend the MarketBot pattern into a small family of DB-level actors — market makers per region, mission-runner statistics, NPC corp activity, chat chatter in rookie help. These fake a population's *economic footprint* without any entities in space. Back this with dedicated DB tables for simulated actors, economy history, and scheduled events so ambient state persists across server restarts.
- **Tier 2 — Protocol-level NPC player characters:** grow the smoke-test bot into a bot framework (Python is the natural fit given the protocol is Python-marshal based). Each bot is a real client: it logs in, appears in local, flies, mines, rats, trades, talks. Because bots exercise exactly the player code path, every hour of bot flight is also a stability soak test. Expect a practical ceiling (each bot is a full client connection into a single-threaded server — measure, but think dozens-to-low-hundreds, not thousands).
- **The AI Director (separate service):** a scheduler/orchestrator that owns the illusion of a living server — decides "6 bots mine in Lonetrek this hour, a 3-bot roam hits low-sec at 21:00, hauler moves goods Jita→Amarr," spawns/despawns Tier-2 bots near where the human player actually is, and drives Tier-1 DB actors everywhere else. Behavior trees or utility AI for decisions; deterministic core. LLM integration is an optional later layer for chat personality — keep it out of the control loop.
- This hybrid solves the "systems only tick when loaded" problem correctly: statistical/DB simulation for the 5,000 systems nobody is in, live bots for the handful the player can see.
- **Private-server UX:** ship activity presets (low/medium/high simulated population) as config profiles, plus a "populated universe" DB seed so a fresh install feels alive on first launch rather than after hours of director warm-up.

## 3. Phase plan

| Phase | Deliverable | Success criteria (exit test) | Why first |
|---|---|---|---|
| 0 | Feature matrix doc, ASan CI, crash capture, health endpoint | CI runs sanitizer build; matrix doc merged; `/health` answers | Observability before change |
| 1 | Headless smoke-test bot in CI, watchdog/recovery, top-crasher fixes | Bot completes login→undock→warp→dock in CI; server survives a 24h bot soak or auto-recovers in <60s | Stability floor; bot foundation |
| 2 | Embedded admin API + WebSocket console; standalone web GUI (console, dashboard, config, events) | Any existing GM command executable from the browser; live log stream; GUI stays up through a server restart | High leverage — mostly wiring existing systems |
| 3 | Bot framework + AI Director MVP (miners, ratters, haulers, chat) + Tier-1 market/economy actors | A human logging in sees non-empty local, active market, and ships in space they didn't spawn | The "alive server" MVP |
| 4 | Living-universe layer: offline universe sim, faction conflict loops, scheduled events from GUI | Universe state visibly evolves over a week of wall-clock time without human input | Depth, driven by what Phase 3 teaches |

Phases 2 and 3 can proceed in parallel once Phase 1 lands, since they touch different seams. Within Phase 2, start with a single static HTML page (command box + status + log stream) against the admin API before investing in the full web app — it validates the seam cheaply.

## 4. Risks

- **Don't rewrite the core.** The destiny/dogma/marshal code embodies years of reverse-engineering; a rewrite restarts that clock. Harden and wrap instead.
- **Bot count vs. single thread:** the director must budget live bots against tick time (expose tick duration via the admin API and make the director back off automatically).
- **Client lock-in:** everything assumes the Crucible client build — pin its exact version in the feature matrix and never chase newer protocol versions.
- **Licensing/scope:** LGPL fork for private use is fine; keep the "private use" framing — the upstream project explicitly does not support public servers.

## 5. Next steps

1. Draft the Phase 0 feature matrix (supported Crucible systems, explicit non-goals, pinned client version).
2. Technical design for the embedded admin API (endpoints, auth, log streaming, tick-time/bot-budget exposure for the director).
3. Technical design for the bot framework (protocol client skeleton, director interface).

## Appendix — Implementation reference (key files)

Verified starting points for each pillar when implementation begins:

- **Main loop / service registration:** `src/eve-server/eve-server.cpp` (game loop ~line 911)
- **Command routing (GUI backbone):** `src/eve-server/admin/` — `CommandDispatcher`, `SlashService`, `AllCommands`, `GMCommands`
- **Existing consoles/listeners to crib from:** `src/eve-server/ConsoleCommands.*` (stdin console), `src/eve-server/apiserver/` (embedded HTTP listener pattern), `src/eve-server/imageserver/`
- **NPC/spawn systems:** `src/eve-server/npc/NPCAI.*`, `src/eve-server/system/cosmicMgrs/` (`SpawnMgr`, `AnomalyMgr`, `BeltMgr`, `CivilianMgr`, `DungeonMgr`)
- **Tier-1 actor precedent:** `src/eve-server/market/MarketBot*` (+ `utils/config/MarketBot.xml`)
- **World state:** `src/eve-server/EntityList.*`, `src/eve-server/system/SystemManager.*`, `src/eve-server/system/DestinyManager.*`
- **Config/live tuning:** `src/eve-server/EVEServerConfig.*`, `src/eve-server/LiveUpdateDB.*`, `utils/config/eve-server.xml`
- **Protocol (bot client foundation):** `src/eve-common/` marshal code, `src/eve-xmlpktgen/` packet definitions, `src/eve-test/` (auth/marshal tests)

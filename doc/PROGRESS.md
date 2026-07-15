# EVEmu Crucible Private Server — Progress Report

**Fork started:** 2026-07-07 · **This checkpoint:** 2026-07-15 · **172 commits**
**Base:** EvEmu-Project/evemu_Crucible (via the sargentscrufy fork) · **Branch:** `phase-1-commerce`

---

## What this project is

A private EVE Online server for the Crucible-era (2011) client, built for one goal:
**a stable, genuinely playable world for a handful of real people**, with the empty
space filled in by simulated pilots. The upstream emulator could log a client in;
almost everything past that — combat that fights back, markets that trade, missions
that run start to finish — was broken, hollow, or crashed the server. Eight days of
work later, all three of those are real.

The work has three pillars:

1. **Stability** — find and kill every crash. The server runs under GDB with
   automatic backtraces; every live crash so far has been root-caused and fixed.
2. **Playability** — make the core loops (fight, mine, trade, missions) work the
   way a player remembers them working on live.
3. **Population** — bot pilots that undock, haul, trade, fight, and die like
   players, so the world feels inhabited.

---

## The story so far, in five acts

### Act 1 — Foundation (Jul 7-8)
Sanitizer builds and CI caught the first undefined-behavior bug on day one. A
protocol-level **smoke bot** logs in like a real client on every deploy. A
transparent **debug proxy** on the login port captures and decodes live
client-server traffic — it became the single most valuable diagnostic tool in the
project. The **warp math was rewritten** to CCP's speed-scaled curve after bots
proved ships arrived at the wrong time and place.

### Act 2 — Making space livable (Jul 8)
The first live play sessions surfaced a wall of foundational bugs: asteroids
vanishing off clients, drones that couldn't launch or return, rats that stood
still and never shot, ships flung to the far end of the universe on undock. All
fixed. Gate guards patrol hisec, rats roam and respawn, and a **market economy
bootstrap** seeded hub-weighted buy walls so a trader has something to trade
against.

### Act 3 — The bot population (Jul 10)
The **simfleet** framework arrived: provisioned sim-pilots that form fleets, fly
multi-system routes (stargate jumps with a BFS route planner), run **arbitrage
trading loops with per-pilot personalities**, and escort high-value haulers with
destroyer wings. Building it flushed out an entire tier of server bugs — fleet
warp was a no-op, market orders couldn't cross, six crash bugs died — because bots
exercise code paths humans are too careful to hit. A dedicated **connection
server** now fronts the cluster as the single public contact point.

### Act 4 — Combat and industry validation (Jul 10-11)
Systematic harnesses measured what players only feel: a **50-battle bot-vs-bot
tank suite** validated EHP and damage mechanics; module-matrix QA found two
client-triggered server crashes; a **combat-disconnect use-after-free** (DESTINY-7)
was caught mid-battle. Smartbombs got implemented. The full **industry chain was
validated end-to-end** — reprocessing, manufacturing, ME/TE research, blueprint
copies, and PI command centers (two PI crashes fixed on the way).

### Act 5 — Security missions & live polish (Jul 12-15)
The headline feature: **security (encounter) missions**, absent from the emulator
entirely, now run the full retail arc — custom-written Guristas mission fiction,
briefings from the database, an acceleration gate at a warp-in, a deadspace pocket
with scenery props, a leader who taunts you as you commit, henchmen that lock you
back **and shoot** (a server-wide NPC bug fixed here: reactively-aggroed rats never
started their weapon timers — every rat a player shot first had been silent
forever), a mission transport whose death drops the objective in a jettisoned
container, time bonuses that actually pay, and a right-click **Agent Missions menu
with working labels and a Warp option** — reverse-engineered from the client's own
localization data and call signatures, since the client code itself is encrypted.
Certified by a 9-point automated QA bot that flies the whole mission like a player.

Alongside it, live play sessions with a real tester drove a rapid-fire polish
loop: market quick-sell, warp-in distances that don't clip you into objects,
capacitor full on undock, throttle settling at 50%, weapon effects rebuilt to
match live packet captures, and the stuck-warping bug family hunted to
extinction.

---

## Features added (what exists now that didn't)

| Area | What was built |
|---|---|
| **Security missions** | Full retail two-room encounter arc: DB-driven mission content (7 missions, L1+L2), acceleration gates, deadspace pockets, scenery, leader taunts, escort scaling, objective container drops, journal bookmarks, agent-menu warp, time bonuses, People & Places backup bookmark |
| **Bot population** | simchars provisioning, simfleet (fleets, arbitrage traders with personalities, escorted convoys, hauler loops), multi-system travel with route planning, killmail history import |
| **Market economy** | Hub-weighted seed economy with NPC buy walls, range-aware order matching with partial fills and order crossing, NPC-corp replenishment (Trader Joe), quick-sell, system-wide asks fallback |
| **Combat systems** | Drone control (engage/return/scoop), smartbomb AoE, NPC reactive return-fire, NPC EWAR (points/scrams with release-on-death), standings loss on faction kills + faction police response, empire gate guards |
| **World simulation** | Rat roaming/respawn, wave despawn, stale-spawn cleanup, wreck loot, gate-to-gate NPC traffic tools |
| **Ops & QA** | Sanitizer CI + nightly smoke test, protocol debug proxy, GDB auto-backtrace on crash, deploy gate (no restart with pilots in space), connection front-end server, in-game BUG reporting to server logs, docker recovery scripts, portable x86-64-v2 builds |
| **Player QoL** | Login MOTD dialog (patch notes), full cap+shield on undock, 50% throttle default, warp-in standoff distances, mission journal titles/briefings |

---

## Bugs fixed (the ledger)

Roughly **80 tracked bug IDs closed** across eight days. The heavy hitters, by family:

**Server crashes (all root-caused, all fixed):**
- CORE-1 XML parser UB · MKT-1 market order crash · COMP-A/B module crashes
- NETWORK-1 disconnect data race · DESTINY-7 combat-disconnect UAF
- HARDEN-2 undock SIGSEGV · PI-1/PI-2 planetary interaction crashes
- GRID-3 warp UAF · TARG-1 target-manager lifetime (two paths) · TARG-2
  system-unload teardown UAF · SECMISSION transport-death segfault
- CHAR-2 /giveskill infinite loop (server hang)

**The warp/movement saga (DESTINY-2 through -13):** login-warp landings, the
warp math rework, undock stomps, wedged "warping while stationary" states (three
separate root causes across DESTINY-6, -12, and -13 — the last one, an in-warp
speed change silently demoting the ball mode, was the true killer), warp-to-dock,
orbit-target-death heading loss, the 1e16-meter login fling, and unclamped
collision bumps (mitigated; root fix still open).

**NPCs that actually fight:** rats now move, classify, shoot, and resync
(NPC-1/1b/2/3, GUN-1); reactive aggro starts weapon timers (NPC-FIRE-1 — the
"enemies never shoot back" bug that had silently applied to every NPC a player
shot first, since forever).

**Client-poisoning data bugs** (found by reading the live client's own relayed
tracebacks): NaN damage states crashing the client on targeting scenery (PROP-1),
jetcan slims broadcasting itemID 0 and aborting whole grid updates (CAN-SLIM-1),
weapon effects sent in a mode the client never renders (EFFECT-1/EFFECT-2),
ghost balls left on clients (VIS-1).

**Markets:** MKT-1 through MKT-6 — from "the market crashes the server" to
bot-certified 15/15 range-aware matching with partial fills.

**Missions:** BONUS-1 (time bonus never paid, always showed expired), EXPIRY-1
(missions expired in minutes instead of a day), LOOT-1/2 (objective loot
ownership and the full-but-empty wreck), plus the entire agent-menu
reverse-engineering chain (M3c→M3f).

**Everything else:** belt spawn family (SPAWN-9/10/11/11b/12/13), fleet warp
(FLEET-1), capacitor-empty sessions (CAP-1), drone ghosts (DRONE-2/3), ore merges
(CHAR-4), asteroid one-shots (ROID-1/2), skill-less fitting (SKILL-1), container
log flood (HANG-1), and more — full detail lives in [bug-log.md](bug-log.md).

---

## Open issues (what's next)

1. **DESTINY-11** — unclamped collision/bump physics (highest-leverage remaining fix)
2. **CRASH-1** — escort-dock segfault after multi-system fleet runs (GDB armed)
3. **SPAWN-14** — belt spawns don't arm when the pilot lands in a non-belt sub-bubble
4. **EFFECT-2 verification** — per-cycle weapon FX deployed, awaiting live confirmation
5. **MUSIC-1** — mission sites don't switch to combat music
6. **GATE-ORIENT** — acceleration gate model doesn't face the pocket (cosmetic)
7. **M4 mission backlog** — site cleanup without restart, bookmark push without
   relog, Local-channel NPC taunts, faction-matched rats per region
8. **COMP-D/E** — module-state edge cases (low)

---

## By the numbers

- **172** commits in 8 days
- **~80** tracked bug IDs closed, **~8** open
- **12+** server crash classes eliminated; zero unexplained crashes remaining
- **9/9** automated security-mission QA, **15/15** market certification
- **50** bot-vs-bot battles validating combat math
- **3** live play-testers' worth of production feedback triaged (13 BUG reports → 12 fixes)
- **1** encrypted client reverse-engineered around, twice

# EVEmu Crucible Private Server — Progress Report

**Fork started:** 2026-07-07 · **This checkpoint:** 2026-08-03 · **branch `phase-1-commerce`**
**Base:** EvEmu-Project/evemu_Crucible (via the sargentscrufy fork)

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
capacitor full on undock, undock throttle (full burn / 100% is accepted — no
need to settle at 50%), weapon effects rebuilt to match live packet captures,
and the stuck-warping bug family hunted to extinction.

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
| **Player QoL** | Login MOTD dialog (patch notes), full cap+shield on undock, undock at full throttle approved (live play preference), warp-in standoff distances, mission journal titles/briefings |

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

### Closed / improved — interactive playtest 2026-08-02…03
Human session (Admiral_Mullins / SARGENTSCRUFY, Rokh *Cold Steel 2*):
- **TURN-1** — structural turn model (live heading, nlerp, no land/turn snaps)
- **JUMP-CLOAK / LOGIN-CLOAK** — 30s gate cloak FX; 20s login cloak with timer + land uncloak
- **WARP-LAND / GRID-WARP** — soft residual land facing travel; no grid wipe mid-warp
- **GUN-FX** — beams stay up mid-fight (FX before damage; no stretch-to-corpse)
- **HOSTILE-1** — rats free-fire (securityStatus −10; no peaceful confirm)
- **DRONE-4/5/6** — Warden/control/bandwidth/ownership
- **MOTD** — Local + login modal patch notes / known soft spots
- **OPS** — do not redeploy mid-session (SIGTERM 143 looks like a crash)

### Still open (priority for next docked deploy)
1. **ALIGN-TIMEOUT** — warp still often force-InitWarp after `time > shipTimeToWarp` (log DestinyError; may feel like late align)
2. **CLIENT-LOGIN** — Neocom `_UpdateSkillInfo` TypeError float/None; occasional `No ballpark` / `GetBalls` on session edges
3. **FX radius** — rare `AttributeError: radius` when stretching FX to a missing ball
4. **HUNT M2 kill** — pin/scram PASS; civ-gun kill still soft (bot cert)
5. **SPAWN-14** — belt spawns in non-belt sub-bubble
6. **MUSIC-1 human sign-off** — combat music in mission pockets
7. **HUNT M3–M4** — CrimeWatch, convoy dispositions
8. **Destroyable belt rocks** — intentional for gun testing (not a bug; decide for “retail” belts later)

### Policy
- Batch fixes; redeploy only when docked/logged out or on explicit request.
- Real crashes = non-143 exit / OOM / GDB backtrace — not compose recreate.

---

## By the numbers

- Multi-week fork; continuous playtest-driven polish on `phase-1-commerce`
- **~90+** tracked bug IDs closed; open list above
- **9/9** automated security-mission QA, **15/15** market certification (prior cert suite)
- Live play-tester feedback loop (Local `BUG` lines + session notes)

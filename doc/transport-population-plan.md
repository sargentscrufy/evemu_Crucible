# Transport Population Plan — thousands of haulers, player-huntable convoys

Extends [phase-1-commerce-plan.md](phase-1-commerce-plan.md) (M5) into the
full population vision: thousands of bot transports moving goods across
the cluster, escorted convoys, and — the content payoff — **players can
target, destroy, and loot these transports in low-security space**.

## Population spec (user requirements)

| Class | Share | Hulls | Escort doctrine |
|---|---|---|---|
| Small transport | ~80% | Badger, Badger Mk II, Wreathe, Iteron III... (group 28) | **~50%** fly with **1-2 frigate** escorts |
| Ultra-large | **~20%** | Providence 20183, Charon 20185, Obelisk 20187, Fenrir 20189 (group 513, 720-785k m3) | **~80%** escorted (1-3, destroyer/frigate mix) |

- Convoys **fleet-warp together** (FLEET-1, certified 2026-07-10).
- Escort disposition state machine:
  - `FOLLOW` (default): shadow the transport; fleet warps carry them
    in-system; gate-follow between systems.
  - `ENGAGE` (on aggression against any convoy member): escorts lock and
    attack the aggressor and hold the grid.
  - Transport disposition on aggression: `ESCAPE` — align/warp to the
    next route point or nearest station/gate, re-route around the
    hostile system, dock up if pursued.
- Routing: a configurable fraction of routes crosses **lowsec pockets**
  (Forge/Lonetrek chain: Akora 0.32, Messoya 0.32, Uemon 0.20, ...) —
  that is the hunting ground. Highsec-only pilots keep min_security 0.45;
  convoy pilots run min_security 0.1 with lowsec-transit awareness.

## Why this is content, not just simulation

A freighter with 700k m3 of seeded goods is a piniata: hunting parties
(the user + friends) can scout lanes, tackle in lowsec, kill escorts,
destroy the transport, and loot the wreck. Escorts shooting back and
transports fleeing make it a fight, not a shooting gallery.

## Workstream A — kill/loot mechanics (lowsec content loop)

Validation-first: bot-vs-bot PvP probe in a lowsec pocket (attacker bot
+ escorted transport bot), because bots give deterministic repro before
the user live-tests.

- A1. PvP kill chain: attacker locks transport, applies damage, kill →
  wreck created → victim podded. (Server survey in progress; gaps get
  fixed like MKT-1/2/3.)
- A2. Loot: cargo drop into wreck, wreck opened + looted by attacker,
  item conservation audit (drops + destroys == cargo).
- A3. Lowsec rules: no CONCORD, sentry guns only at gates/stations,
  criminal/suspect flagging, sec-status hit. Verify or stub sanely.
- A4. Killmails for both sides.
- A5. Escape mechanics: warp-out under fire works unless scrambled
  (AttrWarpScrambleStatus already gates CmdWarpToStuff).

## Workstream B — convoy behavior (escorts + dispositions)

- B1. Convoy assembly: composition roller (class/escort dice per spec),
  fleet-up with FLEET-2-safe sequencing, fleet warps on every in-system
  hop, coordinated gate jumps (escorts jump first or with transport).
- B2. Threat detection: bots learn they are under attack from session
  notifications (OnDamageStateChange / damage messages already flow to
  clients; the combat bots proved lock+engage). Trigger: any convoy
  member targeted-by/damaged.
- B3. Dispositions: escorts FOLLOW→ENGAGE (lock aggressor, orbit,
  fire); transport ESCAPE (align out, warp when clear, re-route).
- B4. Freighter enablement: skills closure for group 513 (Advanced
  Spaceship Command + racial Freighter), hull staging, verify undock/
  warp/gate-jump with a 900M-kg hull (align times will stress DESTINY
  paths — expect findings).

## Workstream C — scale to thousands (architecture + validation ladder)

Current runtime: 1 OS thread + 1 blocking socket per pilot — fine for
tens, wrong for thousands.

- C1. **Async bot runtime**: port machoclient's session pump to asyncio
  (single process multiplexes hundreds of sessions; the protocol layer
  is already request/notification based). Target ≥200 sessions/process,
  N processes. A coordinator process (extends the DB-scan "brain")
  assigns roles, routes, and convoy rosters — the "NPCs on rails with a
  higher coordinator" model.
- C2. **Duty cycling**: a living world doesn't need every hauler in
  space at once. Population = provisioned chars (thousands, cheap DB
  rows); activity = rolling fraction undocked (target 10-20% in flight
  concurrently). Dormant docked sessions may even disconnect and
  re-login on schedule — a logged-off char costs the server nothing.
- C3. **Provisioning at scale**: batch generator over provision_fleet
  (accounts, chars via protocol doll creation, hulls/fits/skills via
  staged SQL) — 100 chars/batch, idempotent.
- C4. **Validation ladder** (each rung: server tick time, CPU, RSS,
  login-storm behavior, zero crashes for 30+ min; gdb-batch armed):
  10 → 50 → 200 → 500 → 1000 concurrent sessions.
  Rungs alternate mostly-docked and mostly-flying mixes.
- C5. Server headroom fixes as found (the scale survey will rank
  bottlenecks; candidates: connection polling model, per-tick costs for
  docked clients, bubble broadcast fan-out, login DB storms).

## Sequencing

1. A1-A2 kill/loot probe (content loop is the user-facing payoff) —
   with B4 freighter staging in parallel.
2. B1-B3 convoy dispositions (small transports first, freighters after
   B4).
3. C1 async runtime + C3 provisioning generator.
4. C4 ladder rungs interleaved with A/B soak content — the hunts ARE
   the load test.
5. M6 release rev 5 when the ladder holds 500+ and the content loop is
   user-certified.

## Validation findings (2026-07-10 source surveys)

### Kill/loot readiness (workstream A) — mostly READY
Already working for PvP, no changes needed: damage pipeline is
source-agnostic, players can lock/shoot players, wreck spawns on kill
with cargo/module drops (50% roll, rigs destroyed — Damage.cpp:515-547),
wreck looting works, killmails persist, victim pods eject.  Blockers:
- **A-1 warp scramble — FIXED + VALIDATED (TACKLE-1):** handlers live in
  `ActiveModule.cpp` (Warp_Scrambler group adds/clears
  `AttrWarpScrambleStatus`); bot-certified by `tools/simfleet/tackle_test.py`.
  NPC-EWAR-1 also applies rat points.  (This section was stale as of the
  2026-07-15 checkpoint.)
- **A-2 CrimeWatch is an uninstantiated stub** (CrimeWatch.cpp:39-41):
  no suspect/criminal flags, no kill rights, no loot rights.  Sec-status
  loss on aggression does work (Damage.cpp:457-470).
- **A-3 sentry guns never engage aggressors** (SentryAI.cpp:101-114
  commented out) and CONCORD is never spawned anywhere.  Acceptable
  short-term: lowsec hunts don't need either; implement lowsec gate
  sentries later for authenticity.
- A-4 loot drop chance hardcoded 50% (should respect config).

### Scale limits (workstream C) — thousands need staged approach
Server is a single-threaded game loop fed by **thread-per-connection**
IO (no pool, no cap, TCPConnection.cpp:56):
1. 1000 connected bots = 1000+ OS threads waking every 5ms + ~1MB stack
   each — the #1 wall.  Mitigation: reactor + worker pool (server work).
2. Login/SelectCharacter fully serializes on the main thread with
   synchronous DB and a global sItemFactory gate (Client.cpp:233-354) —
   login storms are pathological.  Mitigation now: coordinator staggers
   bot logins (free, bot-side).
3. O(N^2) per-bubble destiny broadcast (SystemBubble.cpp:1221) — dense
   grids blow up.  Mitigation: cap convoy/grid density via routing; later
   batch per-bubble updates.
4. All clients' packets unmarshal on the main thread at ~100Hz.
5. maxPlayers (250/500) is parsed but NEVER enforced; main-loop sleep
   has an arithmetic bug (sleeps `elapsed` instead of remainder,
   eve-server.cpp:923-925).
Profiling instrumentation exists (sConfig.debug.UseProfiling +
Profiler.h categories) — turn on for every ladder rung.

### Scale verdict
**Thousands of provisioned haulers: YES, now** — chars/hulls are cheap DB
rows; the coordinator duty-cycles a rolling fraction into space.
**Concurrent connected sessions: hundreds now, not thousands** — with
login staggering and convoy density caps the ladder should reach the
200-500 rung on current architecture; 1000+ concurrent requires the
reactor/pool + async-login + broadcast-batching server work (C5, now
scoped with file:line targets).  End-to-end "thousands of haulers" is
therefore achieved as ~2000-5000 provisioned with 10-20% duty cycle =
200-500 concurrently flying, which reads as a fully alive cluster.

## Open risks

- CRASH-1 (fleet-member dock segfault) will likely recur under convoy
  load — gdb-batch will catch it; fix before the 200 rung.
- Freighter physics (900M kg) untested — B4 may open DESTINY findings.
- Market depth: thousands of traders need Joe's replenishment rate
  scaled (orders/cycle, cycle time — MarketBot.xml) and possibly
  seed-refresh for hub walls; watch mktOrders growth (DB bloat) and
  add order-expiry sweeping.
- Wreck/loot litter: thousands of kills → wreck cleanup timers matter.

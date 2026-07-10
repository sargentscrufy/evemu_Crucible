# Phase 1 — Automated Commerce

**Goal:** bot player haulers that autonomously trade across the cluster —
scan the market, find arbitrage (buy low at A, haul, sell high at B),
travel multi-system through stargates, and run continuously as a living
economy. They double as a permanent load/regression fleet: every trader
cycle exercises login, market, inventory, undock, warp, gate jump, and
dock under concurrent multi-client load.

Phase 0 polish is folded in here (M0) — the two worst offenders (CAP-1,
DESTINY-4) directly multiply every trader cycle time, so they pay for
themselves immediately.

## What we build on (already proven)

| Piece | State |
|---|---|
| Market wire protocol | Server serves `GetOrders`, `GetRegionBest`, `PlaceCharOrder` (immediate + standing), `ModifyCharOrder`, `CancelCharOrder` (MarketProxyService.cpp). Bot-side market *buy* proven once (Aura's ship purchase). |
| Price terrain | Market seed v2: hub buy-walls + deliberate price gradients across Derelik / The Citadel / The Forge / Essence / Lonetrek — designed for hauling profit. |
| Travel | Undock → warp → dock proven at scale (hauler wing). `CmdStargateJump` observed in live captures, not yet exercised by a bot. |
| Pilots | 4 provisioned haulers (Badger, Badger Mk II, Iteron III, Wreathe) + 6 combat/industry pilots, accounts fleet01-10. |
| Runtime | machoclient protocol client, fleet_runner supervisor (staggered starts, restart caps), detached background execution, feedback log. |
| Replenishment lead | Stock `MarketBotMgr` exists in-tree (config-driven, processes old orders) — candidate for the market-maker role, state unknown. |

## Milestones

### M0 — Phase-0 polish that gates trader efficiency
- **CAP-1**: ships load with near-empty capacitor → every bot waits 60-100s
  after undock. Fix server-side (persist cap, or fill on load). Biggest
  single cycle-time win.
- **DESTINY-4**: dock-approach sublight crawl from far away → dock timeouts.
  Traders dock 2x per cycle; fix the approach/align catchall.
- **SPAWN-11**: stale unwatched belt waves suppress fresh spawns (kill or
  age-out orphan waves). Matters because traders warping past belts create
  bubbles and interact with spawn timers.
- **FLEET-1**: implement server-side fleet warp (flag already parsed at
  BeyonceService.cpp:378; iterate fleet members via sFltSvc, stagger member
  warps). Regression: rerun fleet_trio_test.py — members must warp on the
  leader's command, not the 75s fallback.
- Lower priority, do opportunistically: MUSIC-1 (combat music cue), UI-1
  (verify fitting-menu names post-GUN-1), MISSION-2 (profane agentSays.h).

### M1 — Market protocol layer (bot side)
- `market.py` in tools/simchars: wrappers for GetOrders (by type, by
  station/region), GetRegionBest, PlaceCharOrder buy/sell (immediate fill
  against existing orders first — simplest correct path), Cancel/Modify,
  wallet balance read.
- Capture-verify each call shape against the live client where possible
  (proxy captures), else derive from MarketProxyService argument lists.
- Expected server bug surface: order matching, escrow/refunds, broker fee
  and sales tax application, order-book cache invalidation
  (`Notify_OnOwnOrderChanged` etc.), quantity-partial fills. Every
  mismatch is a logged finding (MKT-n series in doc/bug-log.md).

### M2 — Travel layer: multi-system navigation
- Exercise `CmdStargateJump(fromGateID, destGateID, shipID)` with one bot;
  absorb the session change (new solarsystemid2, new beyonce bind).
- Route planner: load the jump graph from static data (mapJumps /
  mapSolarSystems) once; BFS shortest path, highsec-only filter.
- `travel.py`: goto(systemID) = loop of [warp to gate → jump → rebind] and
  goto(stationID) = goto(system) + warp + dock. Cap-aware pacing until
  CAP-1 lands, then remove the waits.
- Expected bug surface: session handoff between systems under concurrent
  load (the multi-client analogue of DESTINY-5/6), gate-to-gate warp
  distances, destiny state after jump. This is the richest untested area
  on the server.

### M3 — Cargo + trade execution
- Inventory wrappers: station hangar ↔ ship cargo moves (MoveItem /
  MultiMove via invbroker), cargo capacity check against volume.
- Trade primitive: `buy(typeID, qty, station)` → items land in hangar →
  load to cargo → travel → `sell(qty, station)` against the best buy
  order → wallet delta verified against expected price minus fees.
- Verify item conservation (no dupes / no vanishing stacks) after every
  leg — economy integrity is a hard requirement before scaling up.

### M4a — Escort wings (user requirement)
- Large / high-value haulers travel with destroyer escorts: hauler +
  escort form a fleet, **fleet-warp together** (this makes FLEET-1 a hard
  M0 requirement, not polish), jump gates together, and the escort
  engages any hostiles on the hauler's grid (belt rats aggressing at
  warp-in, lowsec gates later).
- Escort loop: follow fleet leader (the hauler); on grid arrival scan for
  hostiles targeting the fleet, lock and engage (reuse combat_loop_test
  lock/engage machinery on the Cormorant's civilian rails).
- Roster: Mira's Cormorant is escort #1; provision 1-2 more destroyer
  pilots when scaling so each large hauler (Iteron Mark III, Badger Mark
  II runs with expensive cargo) can have one. Cheap Wreathe/Badger runs
  fly solo.
- Escort adds cycle cost (two pilots per route) — the trader brain
  reserves escorts for routes above a cargo-value threshold.

### M4 — Trader brain
- Greedy arbitrage v1: from current station, scan seeded gradient
  commodities (the seed v2 hauling set), score candidate routes by
  **profit per m³ per jump** with a minimum-margin floor (covers fees),
  execute best route, repeat. Per-bot capital ledger; never spend below a
  reserve.
- Personality knobs per pilot (risk margin, preferred regions, max jumps,
  cargo discipline) so 4 haulers don't all converge on one route.
- Market replenishment — arbitrage consumes the gradient, so the economy
  needs a counterparty. Decide during M4 with data:
  (a) finish/enable the stock MarketBotMgr as NPC market maker, or
  (b) a periodic seed-refresher job (re-issue consumed walls/gradients,
  respecting live prices). Bias toward (a) if it's close to working —
  it's server-side and survives restarts.

### M5 — Scale + soak
- Run all 4 haulers as traders continuously (fleet_runner), then scale
  with additional provisioned pilots toward ~20 concurrent traders.
- Metrics per cycle to a light CSV/log: route, jumps, ISK profit, cycle
  seconds, failures. Watch for: DB growth (market history, wallet
  journal), server memory, main-loop tick health under N clients.
- 24h+ soak on dev. Exit criteria: zero server crashes, zero stuck
  traders, item/ISK conservation holds, DB growth linear and modest.

### M6 — Certify + release rev 5
- Full bot regression (smoke, warp round trip, combat loop, fleet warp,
  trader cycle) + user live session.
- Re-stage C:\Fileshare\Eve\Release (rev 5). TEMPORARY-test-account still
  ships until final release.

## Deferred / parallel track (not this phase)
- Security mission arc + encounter mission system (L1/L2 content): big
  content build, parallel to commerce when bandwidth allows — KB/ research
  is ready, mission_qa.py is the harness.
- Web GUI; 1000-bot coordinator architecture (commerce traders are the
  first "static role" population and will inform the coordinator design).

## Sequencing

M0 and M1 first (M0 server-side, M1 bot-side — independent, can
interleave). M2 next, M3 on top of M1+M2, M4 on top of M3, then M5→M6.
Each milestone lands as commits on a `phase-1-commerce` branch off master
(after PR #1 merges), certified by bot flights before moving on.

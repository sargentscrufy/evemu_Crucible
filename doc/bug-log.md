# Bug Log — Live Testing Findings

Observed defects from real-client testing sessions, with evidence. Tier
refers to [crucible-feature-matrix.md](crucible-feature-matrix.md).

## Open

### Session 2026-07-12 late — live client session (localhost)

- **DESTINY-10 (open): undock fling recurrence.** A bot Badger (target_hauler
  runner: DB-staged docked at Jita 4-4, Undock, then CmdSetSpeedFraction 1.0
  ~10 s later) was flung to the 1e16-m sentinel (~66,842 AU) on undock — the
  DESTINY-5/6 family has a surviving path. Deterministic-looking repro via
  tools/simfleet/target_hauler.py fresh-stage mode; hunt it with that.
- **VIS-1 (open): flung/off-grid ships are visible system-wide.** The player
  saw the flung Badger on his overview at 66,842 AU while not in a fleet with
  it. Ships outside the viewer's bubble must not be in their ballpark —
  sentinel-parked entities are apparently added as global (or the fling
  happened mid-bubble-add). Check BubbleManager global-ball handling for
  out-of-bubble positions; may resolve itself once DESTINY-10 is fixed, but
  verify visibility rules regardless.
- **Login-in-space placement offset (DESTINY-2 adjacent, data point):**
  resuming a char in space placed the ship ~0.5 AU from its DB-stored entity
  coordinates (bot relogin after teleport). Workaround: warp in-session.
- **DESTINY-11 (open): collision/smartbomb bump velocity unclamped — target
  punted off-grid.** Live repro: player Hurricane closed to smartbomb range
  of the bot Badger and fired; the blast/hull bump launched her out of the
  8000 km bubble within seconds (SetPosition spam → SystemBubble
  ProcessWander exit) — reads as "she disappeared, not destroyed" on the
  attacker's client while the server keeps her alive off-grid. Same
  unclamped-bounce physics family as DESTINY-2. Guns kept cycling at the
  out-of-range target with 100% misses (harmless but silly — consider
  breaking lock at extreme range).

- **MKT-6 — FIXED 2026-07-12 (05fef810): market appears completely empty when
  opened while undocked.** Live-diagnosed from proxy captures of the user's
  real session: `GetOrders` delivered full books (191 sells for the browsed
  type) while `GetStationAsks` answered an empty IndexRowset twice — an
  undocked client has stationID 0 and the query matched nothing, and the
  client keys the market browse tree's "available items" view off that
  result. Server now falls back to system-wide asks when the caller is in
  space. (Docked-at-orderless-station can still look sparse — that's the
  client's "show only available" filter working as designed.)

### Session 2026-07-12 — production feedback drop (feedback-20260712-180607.log, SARGENTSCRUFY live play)

First round-trip through the feedback-inbox workflow. 13 BUG lines from a
mining/travel/market shakedown in Todaki→Kakakela→Sobaseki. Triage:

- **MOD-1 — FIXED via ROID-1 root cause, bot-certified 2026-07-12.** The
  railgun "kept firing" because the asteroid never actually died server-side:
  asteroids had no HP/resonance attributes, so weapon damage zeroed out in
  the shield branch and the kill/deactivation chain never ran — the client
  loop was the visible symptom. With ROID-1 in place the full chain is
  probe-verified (tools/simfleet/target_killed_probe.py): target dies →
  `TargetManager::Destroyed` → `Deactivate(TargetDestroyed)` on the
  registered turret → zero gun cycles afterward → the stop effect
  (OnGodmaShipEffect start=0) reaches the client. Re-check with the real
  client on the next live session (turret animation is client-rendered).
- **DESTINY-8 — FIXED 2026-07-12 (b7c2a377), bot-certified.**
  `DestinyManager::EntityRemoved`/`IsTargetInvalid` slammed FOLLOW/ORBIT to
  a full Stop() when the target went away. New `KeepHeading()`: drop the
  orbit but keep flying the current heading at commanded speed (live-EVE),
  Stop() only when not moving. Probe: rat killed mid-orbit → server logs
  "Maintaining course", no CmdStop broadcast, ship keeps moving.
- **ROID-1 — FIXED 2026-07-12 (1eb25f3f), bot-certified.** Asteroids spawn
  with structure HP scaled by ore content (500 + qty×0.15 — destroyable by
  design, not one-shot) and unity resonances so damage flows
  shield→armor→hull; `MakeDamageState` reports the real structure fraction.
  Probe: 150mm rail applies real damage (41.74/volley, honest tracking
  misses/hits) and a 78k-unit Pyroxeres shrugs off a 35s volley.
- **ROID-2 (found during MOD-1 investigation) — FIXED 2026-07-12 (1eb25f3f).**
  `TargetManager::Depleted` blind-cast every module registered on the
  emptying rock to MiningLaser and deref'd it — a railgun/salvager on the
  same asteroid at depletion = guaranteed null-deref server crash. Non-mining
  modules are now deactivated instead. (Likely the crash path behind the
  user's exact mining+shooting play pattern.)
- **UI-2 (open, low, likely client): right-click menu dead for ~1 min after
  destroying an asteroid**, then self-recovered. Probably downstream of the
  pre-fix asteroid weirdness (client-side destruction rendering of an entity
  the server never removed). Re-observe after ROID-1 in live play before
  spending more on it.
- **UNDOCK-1 (new): undock is slow — long black screen before the ship
  appears outside the station.** Reported twice in one session ("definitely
  need to make undocking process faster"). Profile the deferred undock push
  (DESTINY-5/6 yields) and session-change timing for dead time we control.
- **DESTINY-9 — FIXED 2026-07-12 (b7c2a377), deployed (live-verify pending).**
  Gate warp-in point now lands 250 m shorter (BeyonceService gate branch), so
  the last stretch is flown on engines instead of bouncing off the gate
  model. Tuning per the user's exact request; confirm feel on the next real
  client session.
- **NAV-1 (new, feature): one-click jump.** Choosing Jump on a gate should
  chain warp→approach→jump automatically (stock EVE behavior); today the
  pilot has to re-click Jump after landing. Implement jump-on-arrival intent
  in the gate Jump command path.
- **NPC-4 (new, balance): belt rats too strong for highsec.** 0.8-sec rats
  fit for 0.4–0.6 space; user wants strength scaled by system security
  (weaker above 0.6, roughly current at 0.4–0.6). Self-corrected caveat: a
  rookie ship *should* struggle — but see CUE-1, they were being hit before
  they could tell they were under attack.
- **CUE-1 (new): missing aggression feedback — no cue when targeted, when
  hit, when shields drop.** May be the same client-heuristic family as
  MUSIC-1 (we already send weapon-FX/damage), but verify we emit the
  being-targeted notifications (OnTarget hostile/others) that drive client
  warning sounds.
- **MUSIC-1 (recurrence): still zero music the whole session** (ambient and
  combat), while gun/laser sounds confirmed working after the user found a
  volume-slider issue for effects. Previous reclassification covered combat
  music triggers; total music silence suggests the client jukebox never
  starts — worth one more look at what starts ambient music (client-side
  suspected, keep low priority).
- **MKT-4 + MKT-5 — FIXED 2026-07-12 (512c512b), bot-certified 15/15.**
  Reported as: simple-sell quotes a price then lists a sell order instead of
  matching (MKT-4), and selling into a visible buy order errors "No sell
  order found" (MKT-5). Proxy captures from 07-08 show the same immediate
  sell (2301 Tritanium @ 2.0) retried 3× and failing — broken since seed v2.
  Root causes, all in the fill path:
  - `FindBuyOrder`/`FindSellOrder` demanded an exact same-station order with
    `volRemaining >=` the full quantity. Seed-v2 buy walls are solar-system
    range at hub stations, so player sells could never match; the retry loop
    re-ran the identical query 1000×. Now range-aware (station / system /
    region tiers; jump ranges approximated as region) with partial fills.
  - `ExecuteBuyOrder` ignored the requested quantity — selling 500 from a
    2301 stack moved the whole stack — and paid the asked price instead of
    the order's price (leaked escrow on player orders, shortchanged sellers
    vs seeded walls). Now fills exactly min(requested, order, stack) at the
    ORDER's price and returns the quantity filled.
  - `ExecuteSellOrder` (immediate buys) charged the buyer's max bid and
    delivered at the buyer's station; now pays the order price and delivers
    at the ORDER's station (remote buys mean you travel, as in live EVE).
  - Standing orders never crossed the book: a sell listed below an open bid
    just sat (the MKT-4 report). Both order types now fill the overlap
    best-price-first and list only the remainder.
  Validation: tools/simfleet/market_fill_test.py — cross-station in-system
  fill, multi-order best-price walk with partial remainder, standing-sell
  crossing, clean no-match, and remote immediate buy: 15/15 PASS.
  Note: the "2.94 vs 1.91" quote discrepancy is the client pricing off the
  regional book; with range-aware fills the quoted regional price is now
  actually obtainable, so this resolves the report. Revisit only if the
  quote still looks wrong in live play.

Not actionable: "Just checking the bug tool" (FEEDBACK-3 confirmed working
in production), gun/laser sound report resolved by the user (volume slider).

### Session 2026-07-11 — combat campaign, weapons, industry, PI, hardening, sound

Fixed + validated this session (details in the commits / linked docs):
- **DESTINY-7** (mid-combat disconnect UAF, was Tier-1 OPEN below) — **FIXED**:
  `~Client()` now `RemoveEntity(pShipSE)` before free; 9-round hard-disconnect
  soak clean (restarts=0). See combat campaign commit.
- **Tackle** (warp scrambler/disruptor) — **FIXED + VALIDATED**: sets/clears
  target `AttrWarpScrambleStatus`, per-module idempotency guard; scrammed
  target gets `WarpScrambled`, release restores warp.
- **NPC-EWAR** (rats scram players) — **FIXED** (deployed).
- **SPAWN-13** (belt-rat scatter, OPEN below) — **FIXED**: `RoamSpawns` skips
  a belt as roam source if a pilot is within 200 km.
- **SMARTBOMB-1** — smart bombs were a no-op (empty AoE case); now damage all
  ships in EMP field range each cycle + exempt from the COMP-B target guard.
  Live PASS (dropped a nearby ship's shield).
- **PI-1** (Tier: node crash) — **FIXED**: `PlanetMgr::UpdateNetwork` asserted
  and SIGABRT'd on a non-tuple command; now `IsTuple()`-guarded. Malformed-input
  probe confirms InstallJob/CompleteJob/Reprocess/GetQuotes also reject cleanly.
- **MUSIC-1** — **RECLASSIFIED (not a server bug)**: combat music is a
  client-side heuristic keyed off weapon-FX/targeting/damage signals that are
  all sent. See doc/sound-cues-investigation.md.

Industry validated live (doc/industry-validation.md): reprocessing,
manufacturing (+consumption), ME/TE research, blueprint copy, PI command-center
deploy. Weapon audit (doc/weapon-implementation-audit.md): all turrets/missiles/
tractor implemented.

Tier-0 crash pass (2026-07-11, rev 6):
- **HARDEN-2 — FIXED + VALIDATED.** `ShipBound::Undock` now rejects cleanly
  when the pilot is not docked (undocking-while-in-space derefs stale
  station/ship state in `UndockFromStation`) and validates the `onlineModules`
  byname shape before casting. Malformed-input probe now passes all 7 cases
  with zero crashes; legitimate undock still works.
- **PI-2 — FIXED + VALIDATED.** `Colony::CreatePin`/`InstallProgram` null-guard
  the pin-item refs (`GetItemRef`/`SpawnItem`) and default the ECU extraction
  attribute when absent. Extractor batch runs with restarts=0, zero segfaults.

Still OPEN:
- **SPAWN-14 (root-caused, deferred):** belt spawns never arm for a pilot who
  warps to a belt. Diagnostics (a top-of-`SystemBubble::Process` probe logging
  every processed belt/gate bubble with a pilot within 300 km) fired **zero**
  times while a bot sat at the belt bubble's center — i.e. no *belt-flagged*
  bubble is near the pilot. The belt the pilot lands in is not being processed
  as a belt: on warp-in the belt entity ends up in a bubble that isn't flagged
  `m_belt` (a GRID-2 bubble-identity/flag-migration issue), so the arming code
  in `SystemBubble::Process` never runs for it. Fix belongs in bubble
  creation/flag assignment (the SPAWN-9/10/11 series is downstream of this).
  A Process-level proximity-arming tweak was tried and reverted (can't help a
  bubble that isn't processed). Blocks the belt-ratting loop and the live
  validation of SPAWN-13 / NPC-EWAR.
- **Invention** (blueprint activity 8) unimplemented server-side.

### SPAWN-11: stale unwatched belt waves — FIXED 2026-07-10, verified live
- **Fix:** belts arm a 5-minute unwatched timer when they hold rats and no
  players; on expiry the wave is despawned (deferred via
  SystemManager::QueueNpcDespawn, spawn bookkeeping dropped first) so the
  next visitor gets a fresh spawn cycle.
- **Verified:** live probe — wave of 4 spawned, pilot retreated, timer
  armed 12:04:57, rats WANDERED to a neighboring bubble (timer correctly
  re-armed there 12:09:27), all 4 despawned 12:14:29.  Note: roaming
  between bubbles resets the grace period, so cleanup can be delayed by
  wander frequency but not defeated.

### MKT-3: Trader Joe never placed an order — FIXED 2026-07-10, verified live
- **Observed:** the replenishment bot's GetEligibleSystems() pulled raw
  random systems (mostly wormholes / station-less), so every 15-min cycle
  no-opped: zero orders ever placed while bot traders drained the seeded
  spreads dry.
- **Fix:** reroll random picks until 5 station systems are collected.
- **Verified:** first post-fix cycle placed 13 buy + 13 sell orders across
  5 systems, owned by NPC corp 1000125 (large volumes, fresh Tritanium and
  commodity spreads) — tradeable via the MKT-2 NPC-corp execution path.
  Economy loop is closed: traders consume, Joe replenishes.

### DESTINY-7: use-after-free crash when a client disconnects mid-combat — FIXED 2026-07-11 (see session summary above)
- **Observed:** 2026-07-10, during bot-vs-bot tank battles. As the defender
  bot disconnected while under fire (destiny updates in flight), the server
  segfaulted. gdb backtrace: SIGSEGV in `SystemEntity::SystemMgr`
  (SystemEntity.h:221) dereferencing a dangling `mySE` inside
  `DestinyManager::SendDestinyUpdate` (DestinyManager.cpp:3405) <-
  SendSingleDestinyUpdate. The entity was freed but a destiny update for it
  still fired.
- **Impact:** any player logging off / disconnecting during combat (or an
  entity removed while its destiny is active) can crash the node. Recurs
  ~once per battle under combat + disconnect load. Production-critical.
- **Cause (suspected):** entity removal on logout/death races with / precedes
  destiny-update processing; SendDestinyUpdate is invoked on a DestinyManager
  whose owning SystemEntity has been freed. Ties to the thread-per-connection
  model (disconnect on the connection thread vs destiny on the main loop).
- **Fix direction:** stop/clear the entity's DestinyManager and dequeue its
  pending destiny updates before freeing the SystemEntity on removal; ensure
  no BubblecastDestiny / SendDestinyUpdate can reference a removed entity.
  Needs careful lifetime work. Harness mitigation: graceful combat teardown
  (stop firing + CmdStop + settle) before disconnecting.

### NETWORK-1: data race in StreamPacketizer segfaults on client disconnect — FIXED 2026-07-10
- **Observed:** gdb-batch caught a SIGSEGV in `StreamPacketizer::PopPacket`
  (StreamPacketizer.cpp:65) — `mPackets.front()` on a queue the code had
  just checked non-empty — inside `TCPConnection::DoDisconnect ->
  EVETCPConnection::ClearBuffers -> StreamPacketizer::ClearBuffers`.
- **Cause:** `mPackets` is pushed on the connection thread (`Process`, driven
  by socket recv) and popped on the main game-loop thread (`PopPacket` via
  `ProcessNet`); `ClearBuffers` also runs on the connection thread at
  disconnect. All unsynchronized — concurrent front()/pop()/push() corrupts
  the queue. Any client disconnecting could crash the node.
- **Fix:** a Mutex guards every mPackets access (push/pop/clear).
- **Likely also explains:** the recurring bot "ConnectionClosed" flakiness
  and quite possibly CRASH-1 below (that segfault fired as a fleet member
  disconnected on dock). Watch whether CRASH-1 recurs now.

### SPAWN-13: belt rats scatter 1000-5500km from spawn before they can be locked — FIXED 2026-07-11 (RoamSpawns pilot keep-out; see session summary above)
- **Observed:** with SPAWN-12, rats spawn 10km off the belt (good), but ~40s
  later the bubble is recreated and the rats are spread 1,000-5,500km apart
  (server BubbleTrace "Dist to center" 0..5.5M). A pilot warping to the belt
  then can't lock them (out of ~30km targeting range). This is the current
  blocker for combat trial T1 (first bot kill).
- **Suspicion:** NPC AI movement / bubble reassignment after the player
  arrives disperses the wave instead of having it approach/orbit the pilot.
  Needs the NPC belt-rat AI (approach-and-orbit-target) investigated.
- **Next:** trace NPCAIMgr movement after aggro; expect rats should close to
  orbit range on the pilot, not scatter.

### CRASH-1: segfault when escort docked after multi-system fleet run (Tier 1, OPEN)
- **Observed:** 2026-07-10 11:47.  Mira (escort, fleet member) docked at
  Jita 4-4 at the end of an escorted trade run; segfault immediately after
  her dock ItemChange.  Fleet leader (Ilsa) had logged off ~10 min earlier
  without disbanding; Mira had traveled multiple systems in the fleet.
- **Repro attempts:** minimal case (fleet of 2, leader logs out, member
  docks) does NOT reproduce — the travel/session history matters.
- **Instrumentation:** dev server now runs `gdb -batch -ex run -ex "bt
  full"` (start.sh, RUN_GDB env); next occurrence produces a full
  backtrace in docker logs.
- **Suspects:** fleet boost update on dock session-change touching stale
  member/leader state (RemoveMember has a booster-vs-role comparison bug
  at FleetService.cpp:1199 that only works because Booster::Fleet ==
  Role::FleetLeader == 1); or escort's target/follow state at dock.

### COMP-F: LoadAmmoToModules only loaded the first module — FIXED 2026-07-10
- **Observed:** loading ammo into a multi-gun weapon group left every gun
  but the first empty (activation errored "not loaded"); the handler used
  only `moduleIDs[0]`.
- **Fix:** iterate the whole module list; first gun consumes the passed
  charge, the rest pull matching charges from cargo (DogmaIMService.cpp).

### COMP-G: ammo turrets "can't load" — NOT A BUG (reload timer), RESOLVED 2026-07-10
- **Initial (wrong) hypothesis:** turrets lack AttrCapacity so LoadCharge
  no-ops. FALSE — the 150mm Railgun I has capacity 0.1 (from the invTypes
  column via ItemType attr map); a docked ammo-load diagnostic with injected
  traces showed `LOADING loadQty=40` — the load succeeds server-side.
- **Actual cause:** loading a charge *in space* starts a ~10s reload timer;
  `m_chargeLoaded` only flips true when it completes (ActiveModule::Process
  line 272-282) — correct EVE behavior. The bot fired 3-4s after loading,
  before the reload finished, so activation reported "not loaded".
- **Fix (bot-side):** wait the reload time (~13s) after loading before
  firing, or load ammo while docked (instant — the docked path skips the
  reload timer). No server change needed.

### SPAWN-11b: belts stuck "spawned" forever after a stale-wave despawn — FIXED 2026-07-10
- **Observed:** after SPAWN-11 despawned a stale unwatched wave, the belt
  never spawned again — a visiting pilot could loiter 10+ minutes with zero
  rats and no spawn-timer activity.
- **Cause:** the despawn removed the rats but left `m_spawned = true`, so
  `SystemBubble::Process()`'s `if (m_spawned) return;` fired before the
  SPAWN-9 self-heal that would re-arm the timer. Belt permanently
  "spawned" with CountNPCs()==0.
- **Fix:** clear `m_spawned` when despawning the stale wave so the belt
  re-arms for the next visitor. (Regression introduced by SPAWN-11; found
  while validating COMP-C combat.)

### COMP-A: salvager/analyzer with no target crashes the server — FIXED 2026-07-10
- **Observed:** activating a Salvager I (or Data Analyzer) with no locked
  target segfaulted the node — `Prospector::CanActivate()` dereferenced a
  null `m_targetSE` (Prospector.cpp:77). One packet from any client.
- **Fix:** null-target check throws `DeniedActivateNoTarget` first.

### COMP-B: missile launcher with no target crashes the server — FIXED 2026-07-10
- **Observed:** firing an online, loaded launcher with no locked target
  spawned a missile with a null target that crashed on impact
  (`Missile::HitTarget` deref, Missile.cpp:252). One packet from any client.
- **Fix:** `ActiveModule::Activate` rejects targetless activation of any
  offensive module; `Missile::HitTarget` null-target guard as backstop.

### COMP-C: bot gun activations were silent no-ops — FIXED 2026-07-10
- **Observed:** `dogmaIM.Activate` only matches a WString effect name; a
  plain Python str matched no overload, the server logged an error, and the
  call still returned SUCCESS. Every bot gun activation fired blanks — the
  real reason rats never died in the fleet trial (SPAWN-11 investigation
  was chasing a symptom).
- **Fix:** `MachoClient.activate_module()` wraps the effect name in WStr;
  combat_loop_test / fleet_trio_test / escort_trader routed through it.

### COMP-D: activating an offline module returns SUCCESS (OPEN, low)
- Only an OnRemoteMessage "ServerError 25164" reveals the failure; the
  Activate call itself succeeds. Confuses bots that trust the return.

### COMP-E: phantom post-undock "warping" state blocks module ops (OPEN, low)
- For ~15-40s after undock a ship reads as warping
  (`DeniedActivateInWarp`) and rejects all module activation. Bots work
  around it with a settle wait.

### MKT-1: PlaceCharOrder sell with no itemID aborts the server — FIXED 2026-07-10
- **Observed:** bot trader sold with `itemID=None`; server terminated with
  `std::bad_optional_access` (SIGABRT) inside `marketProxy::PlaceCharOrder()`.
  Any client sending a malformed sell could kill the whole server.
- **Fix:** guard the optional in MarketProxyService.cpp sell path; reject
  with "You must specify which item to sell."  Bots pass the hangar stack
  itemID (market.py).
- **Verified:** malformed call now errors cleanly; valid sell executes.

### MKT-2: sells to the seeded market could never execute — FIXED 2026-07-10
- **Observed:** every seed-v2 order is owned by an NPC corporation
  (1000xxx), but `MarketMgr::ExecuteBuyOrder` classified owners only as
  player/corp/station/TraderJoe/Trader — NPC corps fell through, the match
  loop spun 1000 times, and every sell to the seeded economy failed
  ("failed to find a matching market order").
- **Fix:** `IsNPCCorp(ownerID)` routes through the NPC-trader path: sold
  item sinks into the NPC economy, seller paid directly, journal recorded.
- **Verified:** live bot sale filled an NPC-corp buy order; wallet delta
  exactly sale price minus sales tax; item removed (conservation holds).

### FLEET-2: fleet invites to characters mid-login are dropped silently — FIXED 2026-07-10
- **Observed:** `FleetBound::Invite` returns None when the invited char
  isn't in world yet, and `AcceptInvite`'s "no outstanding invite" is a
  notify, not an error — so fleet formation raced and members silently
  ended up outside the fleet (this masqueraded as a FLEET-1 failure in the
  first trio run).
- **Fix:** inviter now gets "That pilot is not online." + FLEET__WARNING
  log.  Bot harnesses gate invites behind an all-in-world barrier.

### OPS-2: deploy traffic gate misses bot sessions (process discipline)
- **Observed:** the "no client traffic for 120s" gate greps GetTime/
  SelectCharacter keepalives which bot pilots don't emit; two deploys
  killed in-flight bot sorties.
- **Rule:** also require `SELECT COUNT(*) FROM chrCharacters WHERE
  online=1` == 0 before any dev deploy.

### DESTINY-1: Client crash during warp (Tier 1)
- **Observed:** 2026-07-07, Crucible client 360229, char warping back to
  station in Amsen (30001392). Client hard-crashed; server unaffected.
- **Evidence:** server logged `[DestinyError] Destiny::Turn() - turnTic:2,
  degRemain:6.190, turnPercent:1.81` at the time of the crash. Repeated
  `Destiny::Turn()` errors also appear during normal flight.
- **Suspicion:** destiny update stream sends the client something invalid
  around warp transitions. Same subsystem as upstream fixes #295
  (m_targetDistance) and #298 (ProcessWander segfault).
- **Next step:** raw captures (tools/debug-listener --capture-dir) of a
  warp cycle; diff destiny update sequences against expected client state
  machine. Reproduce with the smoke bot once it can warp.

### DESTINY-2: Login warp-in lands inside station geometry, collision
### response ejects ship at extreme velocity (Tier 1)
- **Observed:** 2026-07-07. Character logged out (crashed) mid-warp to a
  station; on relog, server `Client::WarpIn()` (login warp-in, upstream
  #294) dropped the ship at/inside the station model. Collision response
  bounced the ship away at thousands of m/s.
- **Suspicion:** two stacked defects — (a) login warp-in does not respect
  a minimum drop distance from large structures, (b) bump/collision
  response velocity is unclamped.
- **Next step:** inspect `DestinyManager` warp-in landing position logic
  and collision response; add velocity clamp; smoke-bot regression once
  bot can fly.

### DESTINY-3: Warp speed model — FIXED 2026-07-08, verified live
- **Fix:** speed-scaled CCP curve in DestinyManager (accelDist=v/3,
  decelDist=v, short-warp peak capping, absolute per-tick remaining,
  clamped cruise handoff, no +10km landing shove, uint16 phase times).
- **Verification:** 1Hz simulation (landing error 38-85m across
  150km..60AU cases) + live bot regression `tools/simchars/warp_test.py`:
  undock -> 2.75AU warp to Amsen IV -> warp back -> dock PASSED. Warp
  trace shows textbook decay (each tick e^-1 of the last) ending
  "Exit velocity 42.54 m/s with 42.54 m left to go" — speed == remaining
  exactly as the k=1 model requires, landing ~1km from station center.
- Original analysis follows for reference.

### (was) DESTINY-3: Warp speed model is dimensionally broken — discontinuous
### speed, arrival overshoot (Tier 1)
- **Observed:** 2026-07-07 live test — ship "blasted through the station"
  on warp arrival; earlier session crashed the client during warp
  (DESTINY-1); client exception showed `shipBall = None` after landing.
- **Analysis** (`DestinyManager.cpp` InitWarp/WarpAccel/WarpCruise/
  WarpDecel/WarpStop):
  1. For long warps, accel and decel distances are the constants
     `exp(21) ≈ 1.318e9 m` for **every ship**, though comments claim they
     scale with warp speed. In CCP's model (k=3 accel, k=1 decel, per the
     "Warp Drive Active" dev blog) those distances are `v_warp/3` and
     `v_warp/1` — for a 3 AU/s ship that's 1.5e11 m and 4.5e11 m, i.e.
     the real decel distance is ~340× what the code uses.
  2. Speed is discontinuous at phase boundaries: accel hands off at
     `3·exp(21) ≈ 4e9 m/s`, cruise runs at `v_warp ≈ 4.5e11 m/s` (3 AU/s
     ship) — an instant ~100× speed jump. Same cliff into decel.
  3. `WarpCruise` subtracts a full `warpSpeed` per tick without clamping
     to remaining distance; the decel handoff then **snaps** the ship
     from up to one cruise-tick away (≈3 AU!) to `decelDist` from the
     target in a single tick. The client interpolates that as absurd
     velocity — matches the observed fly-through.
  4. `WarpStop` shoves `m_targetPoint += warp_vector * 10000` (10 km
     forward past the intended landing point) before halting, moving the
     ship closer to the object warped to.
  5. `WarpStop`'s own TODO documents client/server desync after warp
     (`Halt()` while the client still shows drift) — consistent with the
     captured client exception (`AttributeError ... isCloaked`,
     `shipBall = None`) and DESTINY-2's bounce.
- **Proposed rework** (replace, not patch):
  - accelDist = v_warp/3, decelDist = v_warp (meters, v_warp in m/s);
    short warps cap peak speed at `v_peak = targetDist · 3/4` so phases
    stay continuous.
  - Continuous v(t): accel `v = v_peak·e^(3(t−t_a))`, cruise `v_peak`,
    decel `v = v_peak·e^(−(t−t_d))`; position = integral, no snapping;
    cruise tick clamped to remaining distance.
  - Exit warp at `max(100 m/s, v_max_sub/2)` per CCP behavior; land AT
    the computed warp-in point (remove the +10 km shove).
  - Trace-log arrival error; smoke-bot warp regression asserts arrival
    within tolerance and no post-warp velocity spike.
- **Risk note:** client runs its own warp visualization from the same
  parameters; server math matching the CCP curve is what keeps client
  and server in agreement. Test with capture diffs before/after.

### CHAR-1: CreateCharacterWithDoll segfaults on incomplete doll data (Tier 2)
- **Observed:** 2026-07-08, building the Aura NPC bot. Sending an empty
  `util.KeyVal` for characterInfo/portraitInfo crashes the server
  (connection dropped; docker restart policy recovered it, RestartCount 1).
- **Cause:** `CharacterAppearance::Build` / `CharacterPortrait::Build`
  (`character/Character.cpp`) dereference every doll field with no null
  check — e.g. `data->GetItemString("colors")->AsList()` on a missing key
  returns nullptr and is immediately dereferenced.
- **Also:** SpawnCharacter commits the chrCharacters row *before* the doll
  Build runs, so a crash there leaves a half-created character (name
  taken, but not selectable) — a consistency hazard.
- **Fix (not yet done):** null-check doll fields and return a UserError
  (the code already returns CharNameInvalidTaken cleanly, so the error
  path exists); make character creation transactional so a doll failure
  rolls back the chrCharacters row. Good validation-hardening target
  once the admin API / bot framework needs robust programmatic creation.
- **Note:** this is exactly why the Phase 0 docker restart policy matters —
  a client-triggerable server crash recovered automatically in seconds.

### SHIP-1: AssembleShip(PyInt) overload silently no-ops (Tier 2)
- **Observed:** 2026-07-08, simchar provisioning. Calling AssembleShip
  with a bare shipID returns success but assembles nothing.
- **Cause:** the PyInt overload wraps the ID in a PyList and delegates,
  but the delegate re-inspects the ORIGINAL `call.tuple` (still a bare
  int), falls through every branch, logs "end of conditional", returns
  nullptr (`ship/ShipService.cpp`). Only real-list calls work.
- **Workaround:** clients send a list (simchars does). Fix: make the
  delegate use the built list, not call.tuple.

### DESTINY-4: login warp-in wedges ships in a broken align state (Tier 1)
- **Observed:** 2026-07-08. Logging in with a ship in space triggers
  WarpIn(); destiny then loops `ProcessState() Error! ... warp
  align/speed is incorrect, but time > shipTimeToWarp` and the ship
  silently ignores dock requests until a CmdStop is sent (the real
  client happens to send one at login). Also: undock during login
  invulnerability logs "Invul Timer called but timer already enabled"
  with a full stack trace — noisy but harmless.
- **Relation:** same warp math family as DESTINY-1/3; the rework should
  clear it. Until then: CmdStop after in-space login (simchars does).

### SPAWN-1..8: Rat spawn system defects — FIXED 2026-07-08
Audit of SpawnMgr/SystemBubble/SystemManager found eight defects; all
fixed in one pass (commit: rat spawn rework):
1. **Respawn stamp comparison inverted** (`stamp < now` skipped entries
   whose time HAD come): belt rats respawned in ≤150s ignoring
   RespawnTimer, or never respawned if the group timer ticked late.
2. **SpawnEntry.stamp was uint16** vs uint32 GetStamp(): respawn times
   truncated after ~18h of server uptime — rats silently stop
   respawning on long-running servers.
3. **Roaming never happened**: m_ratTimer ("Main Spawn Timer") was
   started nowhere and checked nowhere. Now started in Init() and
   checked in Process(); new RoamSpawns() periodically warps an idle,
   unwatched spawn group to another belt — rats now arrive at belts
   where players are mining.
4. **StartRatTimer stored the interval in uint16 ms**: any RoamingTimer
   over 65s truncated (600s became ~10s).
5. **WarpOutSpawn iterator UB**: `m_spawns.erase(itr); ++itr;` —
   increment of an invalidated iterator (belt-crash class). Rewritten
   bubble-to-bubble with erase() return-value iteration.
6. **SpawnKilled belt-wipe UB**: `m_bubbles.erase(std::find(...))`
   without an end() check.
7. **GetRandBeltID out-of-range**: MakeRandomInt's upper bound is
   inclusive; indexing .at(m_beltCount) could throw (rare crash).
8. WarpOutSpawn signature took an unused NPC* (dead code path);
   replaced by the roaming implementation.

### CHAR-2: /giveskill hangs the entire server — FIXED 2026-07-08
- **Observed:** live. GM command `/giveskill me 22551 3` pinned the main
  loop at 100% CPU; server unresponsive (port still accepted TCP, so the
  docker healthcheck stayed green — liveness != progress).
- **Diagnosis:** gdb attach (`docker exec --privileged ... gdb -p`) on
  the spinning process: `Character::RemoveFromQueue` erase-loop only
  advanced its iterator when it erased a matching entry; any other entry
  in the character's skill queue spun forever.
- **Fix:** advance the iterator in the non-matching branch.
- **Lesson for the admin API (Phase 2):** the health endpoint must
  report main-loop tick progress, not just port liveness — this hang
  looked "healthy" to docker the whole time.

### PHYS-2: bubble thrash wipes belt contents from the client (Tier 1)
- **Observed:** asteroids (and launched drones) vanish client-side while
  mining, even after PHYS-1. Raw capture frame evidence: a single
  RemoveBalls listing all 22 belt asteroids + 5 drones; server bubble
  trace shows the ship removed from bubble 5 then bubble 6 twice within
  one second ("removing balls" each time) while orbiting a rock.
- **Mechanism:** the belt sits near a bubble boundary; orbit/approach
  motion bounces the ship between adjacent bubbles. Every exit sends the
  client RemoveBalls for the old bubble's contents, and re-entry does
  not re-send AddBalls for static entities (asteroids), so the belt
  never comes back visually. Session state is otherwise fine.
- **Fix direction:** (a) hysteresis on bubble reassignment (require
  leaving by a margin beyond BUBBLE_RADIUS before switching), and/or
  (b) on bubble entry always AddBalls the full bubble contents to the
  entering player. Needs care: (b) alone may double-add dynamics.
- **Repro:** orbit a belt asteroid while mining for several minutes.

### CHAR-4: mined ore invisible to the client (Tier 1 -> FIXED 4ae64bbc)
- **Observed:** mining works server-side but the client's hold never
  updates. Originally suspected a missing OnItemChange.
- **Root cause (from ITEM__CHANGE trace):** the notifications were sent
  all along -- but the ore was routed to flagOreHold (134) because the
  ship data (post-Crucible dump) gives barges AttrOreHoldCapacity. The
  Crucible client (360229) predates ore bays and has no UI for flag 134,
  so the ore was collected and stored invisibly.
- **Fix:** MiningLaser now always deposits to the cargo hold (Crucible
  behavior). Existing hidden stack (34,316 Scordite in the Hulk)
  migrated to flag 5 by DB update on 2026-07-08.

### DRONE-1: drone control not implemented (Tier 2 -> deployed, awaiting live verify)
- Drones launch and appear in space (CHAR-3 fixed launching) but engage
  commands return "drone control not implemented yet". DroneAIMgr
  exists (npc/DroneAI.cpp); the beyonce CmdEngage path needs wiring to
  it. User requested this feature build 2026-07-08.
- **Fix (d67736b7):** EntityBound::CmdEngage resolves the target and each
  drone (ownership-checked) and calls DroneAIMgr::Target(), which runs
  the full engage chain (lock -> CheckDistance -> orbit -> attack).
  CmdReturnHome/CmdReturnBay clear targets and call DroneAIMgr::Return()
  (follow home ship; Process() sets idle-orbit on arrival). Deployed
  2026-07-08 ~08:15 UTC. Remaining: auto-scoop on bay return, guard/
  assist/mine verbs still stubs.

### OPS-1: parallel-session deploys clobber live playtests (process bug)
- 2026-07-08 07:40 UTC: a second agent session (Grok) built and
  recreated the server container while the user was mining in space.
  The restart wiped in-space state (belt asteroids/drones respawn as
  bubbles reload) and was initially mis-read as PHYS-2 recurring.
- Rule: check `docker inspect server --format '{{.State.StartedAt}}'`
  before attributing state loss to a bug, and only deploy while the
  user's client is docked or logged out.

### Live-test batch fixed 2026-07-08 (deployed together)

- **SKILL-1 (d3fe5de9):** GenericModule::Online() never checked skills
  (the docked path skipped every check), so replica/imported fits could
  be onlined by unskilled pilots. Player-initiated onlining now runs
  Skill::FitModuleSkillCheck; login/undock restore exempt.
- **EFFECT-1 (5f0f6571):** ShipSE::MakeSlimItem sent the fitted-module
  list as (itemID, typeID) hi-slots-only; the client expects
  (typeID, itemID) for all modules (per CCP capture-derived
  ShipGetModuleList). The reversed pairs silently broke client turret
  mounting, so weapon/mining beams never rendered. Both slim builders
  now share ShipGetModuleList.
- **DRONE-2 (4ae64bbc):** DroneSE::StateChange only bubblecast, so a
  drone scooped off-grid never told its owner -- permanent ghost under
  "Drones in Distant Space". Owner now always receives the update;
  null bubble no longer drops it.
- **DRONE-3 (4ae64bbc):** CmdReturnBay now auto-scoops: drone flagged
  for bay recall; on arrival DroneAIMgr queues a scoop that
  SystemManager processes after the entity tic loop (scooping deletes
  the SE, so it cannot run inside the drone's own Process). Bay-full
  falls back to idle orbit with a notify.
- **SPAWN-9 (b2fac126):** the bubble spawn timer permanently disabled
  itself if it expired while the bubble momentarily read empty
  (bubble churn), and nothing re-armed it -- belts could silently never
  spawn rats. Bubbles now re-arm whenever players are present with no
  spawn, and the timer hit is logged.
- **GATE-1 (6794134d):** StargateSE::LoadExtras passed 'true' as the
  gateID when marking its bubble, registering gate itemID 1 and
  breaking bubble->gate lookups.

### GUARD-1: empire police gate patrols (feature, 6794134d)
- Gates in >0.90 sec systems spawn faction police (Caldari/Gallente
  police lieutenants, Amarr Police Frigates, CONCORD fallback) 10-30s
  after the first pilot enters the gate bubble. Guards idle-orbit the
  gate at 15km (NPCAIMgr guard-post anchor), never initiate attacks,
  resume patrol after fights, and are excluded from roam/respawn
  bookkeeping. First step toward simulated CONCORD/faction-navy
  response.
- **Validated 2026-07-08 09:36 UTC** by bot flight (Aura -> Ekura gate,
  Amsen 1.0): spawn timer hit, three Caldari Police Lieutenants spawned
  guarding the gate with live patrol movement. The same run proved the
  SPAWN-9 timer self-heal and the GATE-1 bubble->gate lookup end to end.

### DESTINY-5: deferred undock push stomped active warps (FIXED e9cd928f)
- **Found by:** GUARD-1 validation flight 1 -- Aura warped from Amsen
  station to 9.8e15 m (65,000 AU) instead of the Ekura gate.
- **Cause:** Client applies the undock ejection via a state timer.  A
  warp commanded in the gap had m_targetPoint overwritten with
  (undock vector * 1e16); InitWarp logged the mismatch and flew there
  anyway. Likely behind earlier player strandings/mis-warps right
  after undock.
- **Fix:** DestinyManager::Undock() leaves an in-progress warp untouched.
  Verified: flight 2 target-vs-calculated error dropped from 1e16 m to
  1,157 m.

### CAP-1: ships load with a near-empty capacitor (open)
- Ships appear to start sessions/undock with almost no capacitor charge
  (no persisted AttrCapacitorCharge), so early warps get cap-clipped
  far short of the target -- a Badger managed only 0.5 AU of a 1.9 AU
  warp. Also explains player "warp stopped early / couldn't warp"
  reports right after undock or heavy module use (Hulk post-mining
  10 AU warp failure on 2026-07-08 07:52).
- Direction: persist/restore cap charge, or initialize to full at ship
  load; also consider cap regen while docked.

### MISSION arc findings (2026-07-09, QA pilot Sera Auvinen @ Spacelane Patrol L1)

- **MISSION-1 (minor):** AgentBound::GetInfoServiceDetails always embeds
  the standings-denial string ("must be -2.0 or higher") even when the
  char qualifies; verify whether the live client displays it.
- **MISSION-2 (content):** placeholder agent dialogue is profane ("Why
  the fuck am I looking at you again") -- agentSays.h needs a civil
  rewrite before friends-facing production.
- **MISSION-3 (core gap):** Security-division agents deal COURIER
  missions. MissionDataMgr has no encounter loader (the boot line
  "0(0) Encounter Mission Data Sets" is a hardcoded string;
  EncounterServer.cpp is pasted research notes). Client protocol
  supports dungeon-objective missions (briefing keywords carry
  dungeonSolarSystemID/dungeonLocationID). Plan: qstEncounter +
  qstEncounterWaves tables authored from KB/missions/caldari/security
  exact tables (L1: Eliminate a Pirate Nuisance, The Hidden Stash,
  Corporate Records, Guristas Spies; L2 scaled variants), loader in
  MissionDataMgr, agent offer routing by division, runtime spawn via
  SpawnMgr/DungeonMgr, completion on wave cleared.

### FLEET trial findings (2026-07-09, trio: Cormorant FC + Merlin + Rifter)

- **WORKS: fleet formation over the wire.** CreateFleet -> bind(fleetID)
  -> Invite(charID) -> AcceptInvite all function; fleet 950000000 formed
  with 3 members across 3 concurrent sessions; composition query OK;
  fleet survived undock/warp/dock cycles at 3 belts; all pilots returned
  and docked.
- **FLEET-1: fleet warp is a server-side no-op.** CmdWarpToStuff parses
  the fleet=True byname and drops it; warp-to-member ('char' type) is
  an explicit "not implemented" stub. Server logs prove members never
  moved on the FC's warp (their warps initiated only when they issued
  their own, 75s later). Implementable: BeyonceService has the flag,
  FleetService has the member list -- on fleet=True, WarpTo each
  on-grid member to the same destination (staggered a few hundred ms).
- **Formation-flight precision note:** members warping to the same belt
  land within meters of each other (exit points differ by <400m) --
  visual formation will look good once fleet warp exists.
- **SPAWN-11 (minor, new):** unwatched leftover rat waves never despawn;
  they park in belt bubbles indefinitely, and via the SPAWN-10 CountNPCs
  guard they suppress fresh waves there (trio found 3 belts occupied by
  stale suite-era spawns, no new spawns offered). Need a stale-wave
  despawn/warp-out pass when a bubble has had no players for N minutes.

## Fixed

### Combat campaign (2026-07-11) — fix all combat-validation gaps except consequence

- **DESTINY-7 (Tier 1 crash) — FIXED + VALIDATED.** A client that
  disconnected mid-combat UAF-crashed the node: `~Client()` freed the
  ship SystemEntity while it was still on the system tic list / in its
  bubble, and the next tic dereferenced the dangling entity. Fix:
  `Client.cpp` now calls `SystemManager::RemoveEntity(pShipSE)` in the
  destructor before the ship is freed. Validated with
  `tools/simfleet/destiny7_repro.py` — 4 rounds of hard mid-combat socket
  drops, container RestartCount stayed 0, zero crash markers.
- **TACKLE-1 (warp scrambler/disruptor) — FIXED + VALIDATED.** The module
  handler was commented out; scram/point never set the target's
  `AttrWarpScrambleStatus`, so nothing could be held. Fix: `ActiveModule.cpp`
  Warp_Scrambler group case adds the module's warp-scramble strength on
  activate and removes it on deactivate, with a per-module idempotency
  guard (`m_scrambleApplied`/`m_scrambleStr`/`m_scrambleTgtID` in
  `ActiveModule.h`) so the status can't stack or leak. Validated with
  `tools/simfleet/tackle_test.py`: scrammed target gets `WarpScrambled`
  on `CmdWarpToStuff`; releasing the point restores warp (status -> 0).
  Stasis web already worked (`WebbedMe`).
- **NPC-EWAR-1 (rats scram players) — FIXED (deployed).** `NPCAI.cpp`
  `AttackTarget` now applies a warp scramble to a piloted target in range
  (guarded by `m_scramTargetID`), and releases it on `ClearTarget` / rat
  death (`~NPCAIMgr`, `ReleaseScramble`). Uses the same
  `SetAttribute(AttrWarpScrambleStatus)` path validated for TACKLE-1.
  Live belt integration not yet exercised (blocked by SPAWN-14).
- **SPAWN-13 (belt-rat scatter) — FIXED (deployed).** `RoamSpawns` could
  yank a fresh belt spawn out from under an arriving pilot when GRID-2
  bubble recreation briefly left them in different sub-bubbles
  (`HasPlayers()` read false), warping the rats away strung across the
  grid. Fix: `SpawnMgr.cpp` skips a belt as a roam source if any pilot is
  physically within 200 km, independent of bubble bookkeeping. Original
  scatter race not reproduced live (blocked by SPAWN-14).
- **COMP-H (test-infra / protocol note):** a bot must online a fitted
  module by activating the **"online" effect** (`activate_module(dogma,
  mod, "online", None, 0)` -> effectID 16 -> `GenericModule::Online`), not
  `dogmaIM.SetModuleOnline`, which returned success but never reached
  `MM::Online` (module stayed Offline, later `Activate` no-op'd at the
  online gate). Earlier tests that onlined only via `SetModuleOnline`
  (e.g. pvp_battle tank onlining) may have measured OFFLINE modules —
  re-verify.

### STAND-1 (faction standing loss on kill) — FIXED (deployed 2026-07-12)

- **Gap:** the reputation loop only had its *earn* half. Completing agent
  missions raised standing (`Agent::UpdateStandings` -> `OnStandingsModified`),
  but killing a faction's ships never lowered the killer's standing with that
  faction, so `repStandings` held only the 395 seeded faction-vs-faction rows
  and never a single character row.
- **Fix (`NPC.cpp` `NPC::Killed`, in the `pClient != nullptr` block):** on a
  player kill of a faction NPC (`IsFaction(m_warID)`, excluding
  `factionRogueDrones`), apply a −0.01 standing delta via
  `sStandingMgr.UpdateStandings(m_warID, killerID, Standings::UpdateStanding,
  -loss, "Ship kill")` and push an `OnStandingsModified` notification carrying
  the new total so the standings UI updates live. Same write/notify path the
  mission-earn side uses; delta accumulates from a 0 base and is floored at −10.
- **Validated end-to-end** (`tools/simfleet/standings_kill.py`): Keva
  `/spawn`s a faction rat (region rat faction, here Serpentis 500020),
  smart-bombs it, and the kill produces `repStandings(500020 -> 90000004) =
  -0.01` plus a `repStandingChanges` row `delta=-0.0100 eventTypeID=45
  msg='Ship kill'`. Read path proven separately
  (`standings_test.py --readonly`): `standing2.GetCharStandings` returns exactly
  the rows in `repStandings` (0/1/3-row correlation).
- **Harness notes worth keeping:** GM `/spawn <typeID>` (needs DEV/SPAWN role,
  which the fleet test accounts have) drops a killable region-rat-faction NPC
  point-blank — the reliable way to get a faction kill while SPAWN-14 blocks
  belt rats. Two gotchas cost real time: (1) the spawned rat must co-locate
  with a **stationary** ship — spawn while mid-warp and rat/ship land in
  different bubbles and can never interact; (2) `empWave` (and any weapon) is
  denied for ~25 s post-undock while the ship is in the warp-safe/align state,
  so the smart bomb silently no-ops unless you settle first. Civilian Gatling
  Railguns (typeID 3638) have no charge group and deal **0** damage in EVEmu —
  don't use them as a test weapon; a smart bomb (23864, 140 EM AoE) one-shots a
  150-EHP rat with no lock/tracking.

### STAND-2 (effective standing math) — FIXED (deployed 2026-07-12)

- **Gap:** `Character::GetStandingModified` (the effective-standing formula:
  Diplomacy lifts negative standings toward 0, Connections raises positive
  ones) already existed but was dead code (`@todo`, unused) and applied
  **Connections to every faction**, ignoring that pirate factions use Criminal
  Connections (skill 3361).
- **Fix (`Character.cpp`):** positive standings now pick Criminal Connections
  for the five pirate factions (Guristas/Angel/Blood/Sansha/Serpentis) and
  Connections for everyone else, via a file-scope `IsPirateFaction()`. And it is
  now actually *consumed* — STAND-3's faction-police gate reads it, so effective
  standing finally drives behaviour.
- **Validated** (`standings_police.py`): base Gallente standing −6 + Diplomacy 5
  → server computes and logs effective **−5.20** = −6 + (10+−6)·0.04·5, the exact
  CCP formula. (Harness note: `db.grant_skill` leaves the skillLevel dogma attr
  280 unset for some skills, so `GetSkillLevel` reads 0 — set attr 280 explicitly
  or the lift silently won't apply; this bit the first validation run.)

### STAND-3 (faction police / consequence layer) — FIXED (deployed 2026-07-12)

- **Feature:** the standing-gated consequence layer. When a pilot jumps into an
  empire's space while **effective** standing to that empire is ≤ −5.0 (the EVE
  faction-police threshold), the empire's navy is dispatched to hunt them.
- **Implementation:**
  - `SpawnMgr::SpawnFactionResponse(factionID, pos, target, count)` — spawns
    `count` navy ships (reusing the GUARD-1 police type table, owned by the
    faction corp) 8–15 km off the offender and calls `AIMgr->Target(offender)`
    so their normal AI locks and engages (unlike passive gate guards).
  - `SystemManager::CheckFactionPolice(pClient)`, called from `AddClient` on
    stargate arrival (`jump==true`, so once per entry in space, not a hot path).
    Gates on the four empire factions (500001–500004), pilot in space, and
    effective standing ≤ −5.0. Squad size scales 2→5 with hostility.
- **Validated** (`standings_police.py`): Keva, hostile to Gallente, jumps
  Iyen-Oursta → Faurent (Gallente 0.54); on arrival 2 Gallente Police (Sergeant
  + Master Sergeant) spawn and are dispatched to hunt her Cormorant. Server
  stable through repeated spawns (no crash). Only triggers on gate arrival, so
  undocking into your own hostile home space doesn't (yet) summon police —
  acceptable v1; a presence/patrol sweep could extend it later.

### Quick-wins batch (2026-07-12)

Small, self-contained fixes found by a code sweep + the local-chat change the
user asked for. All one-to-few lines, deployed together.

- **FEEDBACK-3 (`LSCChannel.cpp`):** the local-chat dev-feedback log + auto-ack
  now only fire when a line carries the uppercase token **"BUG"** (case-
  sensitive `std::string::find`). Ordinary local chatter no longer fills
  `feedback.log` or trips the Deep Space Monitoring auto-ack, so the report
  pipeline stays signal. Validated by `feedback_probe.py` (plain line ignored,
  BUG line logged+acked, second BUG line throttled).
- **LOOP-1 (`eve-server.cpp:923`):** the main loop slept for the *elapsed*
  frame time (`start`) instead of the *remaining* budget. Now sleeps
  `m_sleepTime - elapsed`, so a fast frame no longer spins hot and a slow frame
  no longer oversleeps -- correct ~100 Hz pacing.
- **STATION-1 (`Station.cpp:141`):** `GetOfficeID()` used `=` instead of `==`
  in its office-match condition, so it returned the *first* office in the map
  for **any** corp. Fixed to `==`.
- **PLAYER-1 (`SystemManager.cpp:1014`):** the per-system player counter
  (`m_players`, `uint16`) had a dead `if (m_players < 0)` clamp after
  `--m_players`; unsigned underflow wrapped 0 -> 65535 and the guard never
  fired. Now checks `== 0` **before** decrementing.
- **MISSION-DEST-1 (`MapData.cpp:156`):** `Agent::GetMissionDestination()` could
  underflow `sysList.size()-1` and throw from `sysList.at()` (uncaught -> node
  crash) if the candidate list emptied. Added an empty-list guard that returns
  like the existing no-station path.
- **FMT-1/2 (`AlertService.cpp:90`, `LSCService.cpp:379`):** `%u` fed a
  `size_t`; cast to `(uint32)` to match the format specifier.

### SPAWN-14 (OPEN) — belt spawn never arms when pilot lands in a non-belt sub-bubble

- **Found 2026-07-11** while validating SPAWN-13. A bot warps to belt
  40168291, lands cleanly ("Warp complete", added to belt bubble), and
  sits 2m40s, but `SystemBubble::Process()` never arms the spawn
  (`spawn timer hit` / `Spawning NPC` never logged) even with
  `SpawnTest=true` (5 s timer). The arming condition needs `!m_players.empty()`
  for the belt bubble and `!m_spawned`; the landing sub-bubble either
  isn't counting the pilot in `m_players` or is stuck `m_spawned=true`
  with zero rats (early-return at `SystemBubble.cpp:154`). This currently
  blocks the belt-ratting loop end-to-end and is the prerequisite for
  live-validating SPAWN-13 and NPC-EWAR-1. Distinct from the roam fix;
  needs its own focused pass (the GRID-2 belt-bubble-vs-landing-bubble
  identity, like the SPAWN-9/10/11 series).

### CORE-1: XMLParser::ElementParser missing virtual destructor (UB)
- **Found by:** first ASan CI run (build-sanitized job), 2026-07-07.
- **Symptom:** `new-delete-type-mismatch` abort in eve-xmlpktgen during
  build; same parser machinery (XMLParserEx) also used by the server for
  config loading.
- **Fix:** virtual dtor on the base class, `src/eve-core/utils/XMLParser.h`.

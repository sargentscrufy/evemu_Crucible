# Bug Log — Live Testing Findings

Observed defects from real-client testing sessions, with evidence. Tier
refers to [crucible-feature-matrix.md](crucible-feature-matrix.md).

## Open

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

### CORE-1: XMLParser::ElementParser missing virtual destructor (UB)
- **Found by:** first ASan CI run (build-sanitized job), 2026-07-07.
- **Symptom:** `new-delete-type-mismatch` abort in eve-xmlpktgen during
  build; same parser machinery (XMLParserEx) also used by the server for
  config loading.
- **Fix:** virtual dtor on the base class, `src/eve-core/utils/XMLParser.h`.

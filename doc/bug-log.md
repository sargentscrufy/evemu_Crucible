# Bug Log — Live Testing Findings

Observed defects from real-client testing sessions, with evidence. Tier
refers to [crucible-feature-matrix.md](crucible-feature-matrix.md).

## Open

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

### DESTINY-3: Warp speed model is dimensionally broken — discontinuous
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

## Fixed

### CORE-1: XMLParser::ElementParser missing virtual destructor (UB)
- **Found by:** first ASan CI run (build-sanitized job), 2026-07-07.
- **Symptom:** `new-delete-type-mismatch` abort in eve-xmlpktgen during
  build; same parser machinery (XMLParserEx) also used by the server for
  config loading.
- **Fix:** virtual dtor on the base class, `src/eve-core/utils/XMLParser.h`.

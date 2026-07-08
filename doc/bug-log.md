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

## Fixed

### CORE-1: XMLParser::ElementParser missing virtual destructor (UB)
- **Found by:** first ASan CI run (build-sanitized job), 2026-07-07.
- **Symptom:** `new-delete-type-mismatch` abort in eve-xmlpktgen during
  build; same parser machinery (XMLParserEx) also used by the server for
  config loading.
- **Fix:** virtual dtor on the base class, `src/eve-core/utils/XMLParser.h`.

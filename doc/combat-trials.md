# Combat Mechanics Trials

Structured trials to validate and harden combat mechanics with sim bots.
Each trial: a bot exercises the mechanic, server logs are the ground
truth, findings logged (COMP-n / DESTINY-n / SPAWN-n). Server runs under
gdb-batch so any crash yields a backtrace.

## Status legend
- [x] done  [~] in progress  [ ] queued

## Trials

- [x] T1. **Turret kill** — pilot with real turrets (ammo, reload wait,
  orbit-at-range) destroys a belt rat. First confirmed bot kill.
  Blocked earlier by COMP-C/D/F, SPAWN-11b/12, reload-timing; all resolved.
- [ ] T2. **Wreck + loot** — after T1, confirm a wreck spawns with the
  rat's loot; a second pilot opens and loots it (WS-A precursor).
- [ ] T3. **Drone combat** — Retriever/drone-boat launches drones,
  engages a rat, drones deal damage and return. (DRONE-1 built; validate
  end-to-end kill.)
- [ ] T4. **Missile combat** — launcher boat loads missiles (reload wait),
  fires on a rat, missiles apply damage to a kill. (COMP-B guard in place.)
- [ ] T5. **Active tank under fire** — pilot orbits a rat with a shield
  booster / armor repper running; verify reps offset incoming damage and
  the pilot survives longer (module effects while taking damage).
- [ ] T6. **Warp scramble / tackle** — does any module set
  AttrWarpScrambleStatus? (Survey said scram handlers are commented out.)
  Trial: fit a warp scrambler, activate on a target, confirm the target
  can't warp. Gates the lowsec hunt loop (WS-A A-1).
- [ ] T7. **Multi-target / target switching** — lock several rats, kill
  one, switch fire to the next automatically (combat AI groundwork).
- [ ] T8. **Ship destruction (PvP)** — bot-vs-bot: attacker destroys a
  target bot's ship in lowsec, victim pods out, wreck + loot drop
  (WS-A core; needs T6 to force the kill if the victim flees).

## Findings
(appended as trials run)

- T1: see combat-validation-findings.md. Damage pipeline proven; the chase
  fixed COMP-A/B (crashes), COMP-C/D/F (module activation/ammo),
  SPAWN-11b/12 (spawn placement/respawn). COMP-G was a reload-timer
  misdiagnosis (not a bug). First kill pending the reload-wait rerun.

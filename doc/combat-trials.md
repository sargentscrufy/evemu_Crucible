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

- **T1 (first bot kill) — server side fully validated; kill blocked by
  gameplay/AI layers, not server bugs.** Confirmed working along the way:
  warp-to-rat lands in lock range, target lock, gun online, ammo load
  (server-side, incl. reload timer), damage pipeline (bidirectional, via
  trace). Remaining blockers are NOT server correctness:
  - **SPAWN-13** (open): belt rats scatter 1000-5500 km from spawn before
    they can be locked — NPC belt-rat AI should approach/orbit the pilot,
    not disperse. This is the primary combat-content blocker; needs the
    NPCAI wander/aggro path fixed.
  - Belt spawn-timer variance / occasional stuck belt (a fresh visit
    sometimes sees no spawn for 600s) — investigate whether SPAWN-11b
    fully covers the stuck-belt case.
  - Turret reload/online timing: modules are only Process()'d while
    AttrOnline (ModuleManager.cpp:191), so an idle loaded turret's reload
    timer may not advance to `m_chargeLoaded` reliably — load ammo docked
    (instant path) or ensure the gun is ticked. Civilian ammoless guns
    avoid this entirely (proven to fire + deal damage).
  - Fit vs rat balance: a civilian-gun Cormorant is out-tanked by a
    Serpentis "Chief Guard" wave and gets podded — expected; use a real
    combat fit and target weaker rats.
  Conclusion: the combat SYSTEM is validated. A reliable bot kill is
  combat-AI + fit work for WS-A/WS-B (where SPAWN-13 gets fixed properly).
- **NETWORK-1 (fixed):** the gdb-batch trap caught a data-race segfault in
  StreamPacketizer on client disconnect during T1 runs — any client
  disconnect could crash the node. Fixed with a mutex. The single most
  valuable find of the combat-trial work. See bug-log.md.

See combat-validation-findings.md for the full damage-pipeline evidence
and the COMP-A/B/C/D/F + SPAWN-11b/12 fixes.

# Combat Behavior Validation vs Gameplay Descriptions (2026-07-10)

Current combat behavior reviewed against the described Crucible-era
gameplay (KB/gameplay-loops/asteroid-belt-rats.md, nullsec-ratting.md)
and general EVE combat expectations. Status from this session's live bot
validation, code review, and the 50-battle tank suite.

Legend: **OK** works as described · **PARTIAL** works with caveats ·
**BROKEN** implemented but non-functional · **MISSING** not implemented ·
**CRASH** stability defect.

## A. Core combat mechanics (general EVE) — mostly OK

| Mechanic | Expected | Status | Evidence |
|---|---|---|---|
| Target locking | lock in range, denied while warping | PARTIAL | works; range/warp-in edge cases (SPAWN-13) |
| Turret to-hit | tracking / transversal / optimal / falloff / sig | **OK** | server GetToHit trace matches the formula |
| Damage layering | shield -> armor -> hull, in order | **OK** | Incursus driven shield->armor->hull in tank suite |
| Resistances | resonance reduces effective damage | **OK** | resist/DC fits held measurably better |
| Buffer tank | extenders/plates add EHP | **OK** | onlined shield buffer held best (95%) |
| Active tank | reps/boosters offset incoming | **OK** | Incursus armor rep held armor at ~67% |
| Module activate/online | online then activate | **OK** | after COMP-C (WStr) + COMP-D fixes |
| Ammo / charges / reload | load, ~10s in-space reload timer | **OK** | reload timer + docked instant-load verified |
| Capacitor | drains on warp/modules, regen | **OK** | after CAP-1 fix |
| Ship destruction | ship dies, pilot ejects to pod | **OK** | bots podded repeatedly |
| Wreck + loot drop | wreck spawns, cargo/mods drop | **OK** | survey-confirmed; ~50% item survival roll |
| Looting a wreck | open + take | PARTIAL | works, but NO loot-rights/ownership enforcement |
| Killmails | generated for kills | **OK** | LogKill -> SaveKillOrLoss |
| Missiles | launcher fires, missile applies dmg | PARTIAL | fires (COMP-B guard); missile-to-kill not yet validated |
| Drones | launch, engage, return | PARTIAL | DRONE-1 controls work; drone kill not validated |

## B. Belt-rat spawn mechanics (vs asteroid-belt-rats.md) — PARTIAL

| Element | Described | Status | Notes |
|---|---|---|---|
| Entry-triggered spawn | rats spawn on warp-in/presence | **OK** | belt arms when a player is present |
| Spawn placement | rats appear near the belt | PARTIAL | SPAWN-12 fixed 1000km->10-15km; **SPAWN-13** rats then scatter 1000-5500km (OPEN) |
| Faction by region | Guristas in Caldari, etc. | **OK** | spawn faction from region |
| Mix of ship sizes | frig/cruiser/BC/BS by truesec | PARTIAL | random spawn class; truesec scaling coarse |
| Respawn / chaining | belt repopulates; clearing chains | **OK** | after SPAWN-9/10/11/11b fixes |
| Stale-wave cleanup | old waves don't block belts | **OK** | SPAWN-11 despawn (belts-only) |
| Rare spawns (faction/hauler/officer) | the "lottery" | PARTIAL | hauler + rogue-drone chance in code; officer/faction-rare drops not verified |

## C. NPC combat AI (vs KB behavior) — PARTIAL / gaps

| Behavior | Described | Status | Notes |
|---|---|---|---|
| Aggro on warp-in/proximity | rats aggress arriving players | **OK** | rats damage & pod players |
| Orbit at range + apply damage | close to weapon range, orbit, fire | PARTIAL | AI orbits, but SPAWN-13 scatter breaks clean engagement; damage application OK |
| Damage types match faction | Guristas kin/therm | PARTIAL | damage types applied (trace); per-faction correctness unverified |
| Drone aggro priority | rats prioritize drones | UNVALIDATED | not tested |
| EWAR: webs / scrams | Pithi frigs web/scram | **BROKEN** | NPC reads scram attrs but never sets AttrWarpScrambleStatus on target; no web application |
| EWAR: jams | some cruisers/BS jam | MISSING | not implemented |
| Waves / reinforcements | packs, some trigger waves | PARTIAL | chain-respawn on kill; no scripted wave triggers |
| Warp-out / call for help | rare rat warp-out | MISSING | not implemented |

## D. Tackle / escape / consequence (lowsec-hunt gameplay) — major gaps

| Mechanic | Expected | Status | Notes |
|---|---|---|---|
| Warp scrambler / disruptor (player) | pin a target so it can't warp | **BROKEN** | module handler commented out (ActiveModule.cpp:814-821) |
| Stasis webifier | slow a target | **BROKEN**/MISSING | not applied |
| Warp-out escape | flee if not scrambled | **OK** | AttrWarpScrambleStatus gate works — but nothing ever sets it |
| Gate/station sentry guns | punish aggressors in lowsec | MISSING | SentryAI target-acquisition commented out |
| CONCORD (highsec) | respond to aggression | MISSING | never spawned |
| Crime/suspect flagging | kill rights, loot rights, safe-to-shoot | MISSING | CrimeWatch is an uninstantiated stub |
| Sec-status penalty | aggressor loses sec status | PARTIAL | computed for truesec>0; no flags/timers |

**Consequence of the tackle gap:** with no working scram/web, no target can
be held — every ship (rat or player) simply warps off when threatened.
This is the #1 blocker for the lowsec convoy-hunt content design; it also
means belt rats can't tackle players as the KB describes.

## E. Audio / feedback (vs music-cue description) — one gap

| Cue | Described | Status |
|---|---|---|
| Weapon / hit visual FX | turret beams, impacts render | **OK** (EFFECT-1) |
| Combat music switch | ambient -> combat track on combat start | **BROKEN** (MUSIC-1, open all session) |
| Targeting beeps / death sounds | client-side audio | likely OK (client) |

## F. Stability under combat — two fixed, one critical open

| Crash | Trigger | Status |
|---|---|---|
| COMP-A / COMP-B | targetless salvager / missile launcher | FIXED |
| NETWORK-1 | any client disconnect (packet-queue race) | FIXED |
| **DESTINY-7** | client disconnect **mid-combat** (destiny UAF) | **OPEN — Tier 1** |

## Verdict

The **combat resolution core is sound and matches EVE**: to-hit,
damage-type/resist math, shield/armor/hull layering, buffer & active
tanks, capacitor, ship death + pod + wreck + loot + killmail all behave as
described (validated live and via the tank suite). The gaps are in the
**combat *content* layer**, ranked:

1. **DESTINY-7** (critical stability) — mid-combat disconnect crashes the
   node. Fix before any real PvP.
2. **Tackle (scram/web) is non-functional** — the biggest gameplay gap;
   blocks lowsec hunts and rat EWAR. Uncomment/implement the module
   handlers + NPC EWAR application.
3. **SPAWN-13 rat scatter** — belt rats disperse thousands of km after
   spawn instead of engaging; breaks the belt-ratting loop.
4. **Consequence layer missing** (sentries, CONCORD, crime/flagging) —
   needed for authentic lowsec/highsec rules.
5. **MUSIC-1** — combat music never switches.
6. Polish: per-faction damage/EWAR flavor, drone/missile kill validation,
   loot-rights, rare-spawn lottery.

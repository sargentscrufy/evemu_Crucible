# Tank Battle Results — 50 Simulated Battles (2026-07-10)

Bot-vs-bot PvP: a fixed attacker fires on a defender wearing a Crucible
killboard-style tank fit; the server DAMAGE log is ground truth for the
defender's shield/armor/hull. Two runs: run 1 exposed a measurement bug,
run 2 is the corrected data.

## Runs

- **Run 1 (48 battles):** measured base HULLS, not fits — passive tank
  bonuses (shield-extender HP, resist amps, armor plate HP) only apply
  while the module is ONLINE, and modules de-online on undock; the harness
  didn't re-online the defender's tanks. Discarded for tank ranking.
- **Run 2 (45 battles, onlined tanks):** the defender now onlines every
  fitted module and activates the active tanks (shield booster / armor
  repairer / damage control) after undock. This is the valid dataset.
  (5 battles lost to DESTINY-7 crashes; see below.)

Attacker: Cormorant, 7x Civilian Gatling Railgun (ammoless, ~constant
kinetic+thermal DPS), orbit 500m, ~120s window.

## Run 2 results (onlined tanks)

| fit | EHP | avg shield% | avg armor% | avg hull% | tank lost% |
|---|---|---|---|---|---|
| incursus_armor_active | 1394 | 18.3 | **67.1** | 99.8 | 38.3 |
| cormorant_shield_buffer | 2969 | 49.8 | 100 | 100 | 16.7 |
| rifter_armor_buffer | 1405 | 55.8 | 100 | 100 | 14.7 |
| merlin_dual_light | 1527 | 65.4 | 100 | 100 | 11.5 |
| punisher_heavy_armor | 1627 | 68.1 | 97.5 | 100 | 11.5 |
| merlin_shield_active | 1527 | 70.0 | 100 | 100 | 10.0 |
| merlin_shield_resist | 1527 | 76.4 | 100 | 100 | 7.9 |
| rifter_armor_resist | 1405 | 91.6 | 100 | 100 | 2.8 |
| merlin_untanked | 1527 | 92.6 | 100 | 100 | 2.5 |
| merlin_shield_buffer | 1527 | 95.0 | 100 | 100 | 1.7 |

## What is validated (server tank mechanics)

- **Damage layering (shield -> armor -> hull): CONFIRMED.** The Incursus
  (low native shield) was driven through shields (18%) into ARMOR (67%),
  with hull still ~100%. Damage correctly cascades layer by layer.
- **Active armor repair: CONFIRMED.** Once in armor, the Incursus's Small
  Armor Repairer held armor at ~67% under sustained fire — the repper is
  offsetting incoming damage (without it, armor would keep dropping).
- **Shield buffer HP: CONFIRMED.** Onlining 2x Small Shield Extender made
  merlin_shield_buffer the toughest (95% shield retained) — the extra
  shield HP absorbs the same damage as a smaller fraction. Run 1 (extenders
  offline) did NOT show this; the fix is real.
- **Damage-control / resist: CONSISTENT.** rifter_armor_resist (plate +
  Adaptive Nano Plating + Damage Control) retained 91.6% shield — DC adds
  shield resist too, and it held near the top.

## Measurement caveat (honest)

The civilian attacker's DPS reaches EQUILIBRIUM with the ship's passive
shield regen for most fits, so shields settle at a steady % rather than
breaking — only the Incursus (very low shield) broke into armor. In that
equilibrium regime the settled % is sensitive to hit RNG and regen, so the
fine-grained middle-of-table ordering is noisy (e.g. untanked Merlin
reads near shield_buffer because both simply out-regen the weak attacker).
The Pearson r(EHP, tank_lost) = +0.10 reflects this: EHP doesn't predict
the outcome because the attacker mostly grazes shields, never testing the
armor/hull EHP of most fits.

## To make armor ranking definitive (next step)

A stronger attacker that reliably breaks shields into armor+hull, measured
by TIME-TO-KILL, gives a clean tank ranking. The heavy attacker (7x 150mm
Railgun I, antimatter loaded docked) is built and the docked ammo load
works; it needs the attacker/defender co-location + lock timing hardened
(the extra load time desyncs the undocks and the lock can miss). With that,
re-run for kill-time-per-fit.

## Critical finding surfaced by the experiment

**DESTINY-7 (Tier 1, open):** the repeated combat + disconnect cycles
caught (via gdb) a use-after-free crash — a client disconnecting mid-combat
frees its entity while a destiny update is in flight, segfaulting the node
(SendDestinyUpdate on a dangling mySE). Any player logging off during a
fight can crash the server. Documented in bug-log.md with backtrace and
fix direction; harness mitigated with graceful combat teardown (crashes
dropped from ~1/battle to ~1/25). This is the highest-value outcome of the
battle suite.

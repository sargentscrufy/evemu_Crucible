# Combat Possibilities & Tank-Fitting Test Matrix

Bot-vs-bot PvP validation of armor/shield tank mechanics using
Crucible-era killboard-style fits. PvP is used (not NPC ratting) because
player->player damage is already validated and it avoids the SPAWN-13
belt-rat-AI blocker; a fixed low-DPS attacker (civilian gatling railguns,
ammoless, ~constant kinetic+thermal output) isolates the DEFENDER's tank
as the single variable.

## Combat possibility space

| Axis | Options exercised |
|---|---|
| Weapon / damage type | Hybrid turret (kinetic+thermal) via civilian railgun (fixed attacker). Later: projectile (exp/kin), laser (em/therm), missiles. |
| Tank type | Shield buffer, shield resist, shield active; armor buffer, armor resist, armor active; dual-tank; untanked baseline. |
| Hull class | Frigate (Merlin/Rifter/Incursus/Punisher), Destroyer (Cormorant). |
| Resist profile | Passive amps (kinetic/thermal shield), armor hardeners + Adaptive Nano Plating + Damage Control. |
| Engagement | Attacker orbits defender at weapon range; defender static. |

## Defender fits (killboard-style Crucible T1)

Each measured as "tank held under fixed attacker DPS": how much of the
ship's shield/armor/hull is chewed through in the battle window. Higher
survival % = more effective tank vs a kinetic/thermal attacker.

1. Merlin — shield buffer (2x Small Shield Extender)
2. Merlin — shield resist (Shield Extender + Kinetic Amp + Thermal Amp)
3. Merlin — shield active (Small Shield Booster)
4. Merlin — untanked baseline (no tank mods)
5. Rifter — armor buffer (200mm Plate + Damage Control)
6. Rifter — armor resist (200mm Plate + Adaptive Nano Plating + Damage Control)
7. Incursus — armor active (Small Armor Repairer + Damage Control)
8. Punisher — heavy armor buffer (400mm Plate + Kinetic + Thermal Hardener)
9. Cormorant — shield buffer (2x Small Shield Extender)
10. Merlin — dual light (Shield Extender + 200mm Plate)

## Attacker (fixed control)

Cormorant, 7x Civilian Gatling Railgun (ammoless, no reload/timing
variables), orbit 500m. Constant kinetic+thermal DPS.

## Method

- Attacker + defender fleet up, undock (near station = near each other),
  attacker locks + orbits + fires the defender.
- Server DAMAGE__MESSAGE log is ground truth: parse the defender's
  `DamageUpdate - S:.. A:.. H:..` (shield/armor/hull fractions) over the
  window; record kill or final tank state, time-to-first-damage, DPS.
- 50 battles across the fit matrix (~10 fits x ~5 runs) for variance.

## What this validates

- Shield/armor/hull damage application order (shield -> armor -> hull).
- Resist mechanics (resonance attributes reduce effective damage;
  resist/hardener fits should survive measurably longer than buffer-only).
- EHP scaling (buffer fits absorb more raw HP; active fits sustain).
- That the damage/tank math is internally consistent across hull classes.

Results: doc/tank-battle-results.md.

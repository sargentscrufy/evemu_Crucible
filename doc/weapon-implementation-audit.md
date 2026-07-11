# Weapon & Module Implementation Audit (2026-07-11)

Authoritative source: `ModuleFactory.h` (what constructs) +
`ActiveModule::ProcessActiveCycle()` switch (what actually *applies an
effect* each cycle). A module can construct and cycle yet do nothing if
its group falls in an empty `{ } break;` case.

## Weapons — IMPLEMENTED (deal effect)

| Weapon family | invGroup | Class | Effect path | Status |
|---|---|---|---|---|
| **Lasers** (pulse/beam) | Energy_Weapon | TurretModule | `ApplyDamage()` | **OK** |
| **Autocannons / Artillery** | Projectile_Weapon | TurretModule | `ApplyDamage()` | **OK** |
| **Railguns / Blasters** | Hybrid_Weapon | TurretModule | `ApplyDamage()` | **OK** |
| **Rockets** | Missile_Launcher_Rocket | ActiveModule | `LaunchMissile()` -> `Missile::ApplyDamage` | **OK** |
| **Standard/Light missiles** | Missile_Launcher_Standard | ActiveModule | `LaunchMissile()` | **OK** |
| **Assault missiles** | Missile_Launcher_Assault | ActiveModule | `LaunchMissile()` | **OK** |
| **Heavy missiles** | Missile_Launcher_Heavy | ActiveModule | `LaunchMissile()` | **OK** |
| **Heavy Assault (HAM)** | Missile_Launcher_Heavy_Assault | ActiveModule | `LaunchMissile()` | **OK** |
| **Cruise missiles** | Missile_Launcher_Cruise | ActiveModule | `LaunchMissile()` | **OK** |
| **Torpedoes / Siege** | Missile_Launcher_Siege | ActiveModule | `LaunchMissile()` | **OK** |
| **Citadel torpedoes** | Missile_Launcher_Citadel | ActiveModule | `LaunchMissile()` | **OK** |
| **Bomb launcher** | Missile_Launcher_Bomb | ActiveModule | `LaunchMissile()` | **OK** |
| **Snowball launcher** | Missile_Launcher_Snowball | ActiveModule | `LaunchSnowBall()` | **OK** |
| **Smart bombs** | Smart_Bomb | ActiveModule | `ProcessActiveCycle` AoE (SMARTBOMB-1) | **OK (this change)** |
| **Nosferatu** | Energy_Vampire | ActiveModule | cap drain (`UpdateCharge`) | **OK** |
| **Energy Neutralizer** | Energy_Destabilizer | ActiveModule | cap drain | **OK** |

Turret to-hit (tracking/transversal/optimal/falloff/sig), damage-type/resist
math, and shield->armor->hull layering were validated live in the 50-battle
tank suite. Missiles fire and apply damage on impact (`Missile.cpp:279`).

## Utility / EWAR weapons — IMPLEMENTED

| Module | invGroup | Effect | Status |
|---|---|---|---|
| **Tractor beam** | Tractor_Beam | `TractorBeamStart` reels in wrecks/containers | **OK** |
| **Warp scrambler / disruptor** | Warp_Scrambler | sets target WarpScrambleStatus | **OK** (this session) |
| **Stasis webifier** | Stasis_Web | `WebbedMe` slows target | **OK** |
| **Salvager** | Salvager | salvage roll | **OK** |
| **Target painter** | Target_Painter | sig bonus | **OK** |
| Remote reps / cap transfer / shield transporter | various | apply per cycle | **OK** |

## NOT IMPLEMENTED (constructs + cycles, but effect is an empty case)

These activate and consume cap but apply **no effect** — empty
`{ } break;` in `ProcessActiveCycle` (or handler stubbed):

| Module | invGroup | Note |
|---|---|---|
| **Super weapon (doomsday)** | Super_Weapon | no damage |
| **Interdiction sphere launcher** | Interdiction_Sphere_Launcher | no warp bubble |
| **Warp disrupt field gen (HIC bubble)** | Warp_Disrupt_Field_Generator | no bubble |
| **ECM / ECM burst / remote ECM** | ECM, ECM_Burst, Remote_ECM_Burst | no jam applied |
| **Defender missiles / countermeasures** | Missile_Launcher_Defender | no launch |
| **Cyno / covert cyno** | Cynosural_Field_Generator | no field |
| **Jump portal generator** | Jump_Portal_Generator | no portal |
| **Siege module** | Siege_Module | no siege bonuses |
| **Gang / fleet boost links** | Gang_Coordinator | no gang bonus |

## Live test results (2026-07-11)

- **Tractor beam** (`tools/simfleet/tractor_beam_test.py`): **PASS**. Bot
  jettisoned a Tritanium stack, spawning a Jettisoned Cargo Container;
  activated the Small Tractor Beam on it; the server streamed continuous
  `Destiny::SetPosition()` on the container (it was reeled toward the ship).
- **Smart bomb** (`tools/simfleet/smartbomb_test.py`): **PASS** after two
  fixes — SMARTBOMB-1 (AoE damage in `ProcessActiveCycle`) plus exempting
  smartbombs from the COMP-B "offensive module needs a target" guard (they
  are offensive *and* targetless). EMP smartbomb now damages every ship in
  its field range each cycle.
- Turrets: validated (tank suite, bots kill rats). Missiles: fire + apply
  damage (`Missile.cpp:279`); missile-to-kill live test pending (blocked by
  SPAWN-14 for rat targets; a PvP-target test is viable).

# Combat System Validation — Findings (2026-07-10)

What began as "does a bot actually kill a rat?" became a full validation
of the combat pipeline. The server-side combat systems are proven sound;
the chase surfaced seven real bugs (two production-critical) plus one
open static-data gap.

## Damage pipeline: PROVEN working (both directions)

Server damage trace (DAMAGE__MESSAGE/TRACE) during a live bot engagement,
Mira's Cormorant vs a Serpentis belt wave:
- **NPC -> player:** `Mira Okonen's Cormorant: Initializing 81.00 damage
  from NPC Guardian Chief Guard ... S/A/H update` — the rat damaged and
  ultimately podded Mira.
- **player -> NPC:** `Guardian Chief Guard: Initializing 2.88 damage from
  Mira Okonen's Cormorant using (140001277) ... DamageUpdate S:0.979...`
  — her guns applied damage on hits; shield/armor/hull tracked correctly.
- **Misses were correct gunnery mechanics, not bugs:**
  `Turret::GetToHit - distance:6504, range:1443, falloff:3500 ... Miss`
  — firing 5 km into falloff with a 1.4 km-optimal gun mostly misses.

The pipeline, damage formula, turret to-hit (tracking/transversal/range
falloff/sig), shield/armor/hull, and pod ejection all work.

## Bugs found and FIXED (deployed)

| # | Bug | Severity | Fix |
|---|---|---|---|
| COMP-A | Salvager/analyzer with no target null-derefs -> **server segfault** (one packet) | CRITICAL | null-target guard, Prospector.cpp |
| COMP-B | Missile launcher with no target -> crash-on-impact missile -> **server segfault** | CRITICAL | reject targetless offensive activation + HitTarget guard |
| COMP-C | dogma Activate with plain-str effect name = silent no-op (SUCCESS) -> guns fired blanks | HIGH | MachoClient.activate_module wraps WStr |
| COMP-D | Activating an offline module returns SUCCESS silently (modules de-online on undock) | HIGH | bot onlines guns after undock |
| COMP-F | LoadAmmoToModules loaded only the first gun in the list | HIGH | iterate all modules, DogmaIMService.cpp |
| SPAWN-11b | Belts stuck "spawned" forever after a stale-wave despawn (never respawn) | HIGH | reset m_spawned on despawn |
| SPAWN-12 | Belt rats spawned 1000-1500 km off the belt (unlockable) | HIGH | spawn 10-15 km off, drop flaky warp-in |

COMP-A/B are one-packet client-triggered node crashes — critical hardening
for the public production server independent of the bots.

SPAWN-12 is the root of the very first bug report of the project ("rats
show up in overview but 218 km away and aggroed").

## Open

- **COMP-G (real gameplay bug):** ammo turrets cannot load charges —
  `ModuleManager::LoadCharge` gates on AttrCapacity (cargohold, attr 38),
  which turret types lack, so the load silently no-ops. Only ammoless
  (civilian) turrets and launchers work. Real players fitting ammo turrets
  are affected. Needs turret clip-capacity design, not a one-liner. See
  bug-log.md.
- **COMP-D / COMP-E** (offline-activate returns SUCCESS; phantom post-undock
  "warping" state) remain open, low severity.

## The scripted "first bot kill"

Achievable now with **ammoless civilian guns** (which fire and deal damage
— proven) plus range control (orbit at optimal) and survivability, OR once
COMP-G lets real turrets load ammo. This is combat-AI / fit tuning that
belongs to the WS-A/WS-B convoy-combat work, not to server validation —
the server itself is validated. combat_loop_test.py now has the pieces
(online, all-guns, orbit-to-range, ammo-load, live-NPC detection) for that
work to build on.

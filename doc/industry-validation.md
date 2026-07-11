# Industry & Production Validation (2026-07-11)

Bot-driven validation of the industry subsystems for test players, matching
the combat validation approach. Harnesses live in `tools/simfleet/`.

## Results

| Loop | Test | Status | Evidence |
|---|---|---|---|
| **Reprocessing** | `reprocess_test.py` | **PASS** | 3330 Veldspar → 8312 Tritanium (~83% w/ skills), ore consumed |
| **Manufacturing** | `manufacture_test.py` | **PASS** | Antimatter Charge S BPO → job → 100 charges delivered |
| **Material consumption** | `industry_chain_test.py` | **PASS** | reprocessed Tritanium consumed by a Harvester Mining Drone job |
| **Processing→Manufacturing chain** | `industry_chain_test.py` | **PASS** | Veldspar → Tritanium → 1 drone built |
| **ME research** | `research_test.py` | **PASS** | BPO mLevel 0 → 3 |
| **TE research** | `research_test.py` | **PASS** | BPO pLevel 0 → 2 |
| **Blueprint copy** | `research_test.py` | **PASS** | 1 BPC (copy=1) produced with N runs |
| **Invention** | — | **NOT IMPLEMENTED** | `CompleteJob` activity 8 is a comment stub |
| **PI: bind + command center** | `pi_colony_test.py` | **PASS** | planetMgr bind boots the planet system; CC deployed to a lava planet (piCCPin row), 90k ISK charged, no crash |
| **PI: extractor + program** | — | **BLOCKED (PI-2 crash)** | upgrade-CC + add-ECU + install-program batch crashes the node |

## PI (Planetary Interaction)

Enabled and data-loaded (40 planet data groups, 69 schematics). Validated so
far: the `planetMgr` bound service boots a planet's system and
`UserUpdateNetwork([(CreatePin,(pinID,typeID,lat,long))])` deploys a command
center (colony row in `piCCPin`, customs office created, 90k ISK charged).

- **Protocol note:** each command element must be a **PyTuple**
  `(command, command_data)` with a tuple `command_data`; a list-shaped command
  is rejected (after PI-1) or, before the fix, crashed the node.
- **PI-1 (FIXED):** `PlanetMgr::UpdateNetwork` called `AsTuple()` on each
  command with no type check — a malformed command tripped an assert and
  SIGABRT'd the whole node. Now guarded with `IsTuple()`.
- **PI-2 (OPEN):** the extractor path — upgrade command center + add an
  Extractor Control Unit (standard pin) + install an extractor program — still
  crashes the node (likely a null `ccPin`/pins-map deref in
  `Colony::CreatePin`/`UpgradeCommandCenter`). Needs gdb tracing; the full
  extract → route → cycle → launch loop depends on it.

Lava planet raw resources (for extractor programs): Base Metals (2267), Heavy
Metals (2272), Non-CS Crystals (2306), Felsic Magma (2307), Suspended Plasma
(2308). Station 60000988-style research aside, PI has no per-station gating.

## What works (server paths confirmed live)

- **Refining** (`reprocessingSvc.Reprocess`): yield = batches × efficiency ×
  (1 − tax) from `invTypeMaterials`; ore consumed, minerals spawned to hangar.
- **Manufacturing** (`ramProxy.InstallJob` → `CompleteJob`): assembly-line
  selection, Industry-skill gate (`RamNeedSkillForJob` 3380), bill-of-materials
  from `invTypeMaterials`+`ramTypeRequirements` via the blueprint→product map,
  material consumption, ME-reduced quantities, product delivery.
- **Research** ME (`UpdateMLevel`) and TE (`UpdatePLevel`), **copy** (spawns
  BPCs with the BPO's ME/PE and licensed runs).

## Notes & gaps

- **Activity enum (EVEmu-specific):** Manufacturing=1, **ResearchTime(PE)=3**,
  **ResearchMaterial(ME)=4**, Copying=5, Invention=8. (3/4 are the reverse of
  what one might guess.)
- **Research/copy stations:** only ~538 of 2174 NPC stations carry research/
  copy/invention assembly lines (activities 3/4/5/8); Iyen-Oursta and Jita 4-4
  are manufacturing-only. Station 60000988 has all lines and is used for the
  research test.
- **Test-staging caveat:** DB-inserted material stacks are NOT in the runtime
  inventory that `GetBOMItems()` enumerates, so a manufacturing job over
  DB-staged minerals reads as "not consumed." Materials sourced through the
  game (reprocessing output, market buys) ARE consumed — proven in the chain
  test. Real players are unaffected; only pure-DB staging needs care.
- **Invention (activity 8) is unimplemented** — the handler is explanatory
  comments only (datacores, chance rolls, T2 BPC output). A dedicated
  implementation task.
- **PI (Planetary Interaction)** is enabled and data-loaded but not yet
  loop-validated (see IND-5); its colony command-list protocol is the most
  involved and is the next industry target.

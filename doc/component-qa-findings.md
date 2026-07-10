# Component (Module) QA — Findings

Date: 2026-07-10 · Branch: phase-1-commerce · Harness: `tools/simfleet/component_qa.py`
Pilot: Tal Rethis (fleet04 / 90000007), Drake `140000914`, Jita 4-4 (60003760 / 30000142)

Eight module types were DB-staged onto the Drake (mid flags 20-23, low 12-13,
hi 31-32, ammo in cargo flag 5; skills closure-granted with attribute-row
verification per the known `grant_skill` bug) and exercised through the real
client protocol: online docked, online in space, activate/deactivate, ammo
load, passive toggle, and deliberate no-target activations.

## Result matrix (final run)

| Module | Online (docked) | Online (space) | Activate/cycle | Notes |
|---|---|---|---|---|
| 1MN Afterburner I | PASS | PASS | PASS (OnSpecialFX/OnGodmaShipEffect confirmed) | self, no target |
| Small Shield Booster I | PASS | PASS | PASS (effect confirmed) | self |
| Ballistic Deflection Field I | PASS | PASS | PASS (effect confirmed) | active kinetic hardener toggle |
| Survey Scanner I | PASS | PASS | PASS (effect confirmed) | self/none target |
| Small Armor Repairer I | PASS | PASS | PASS (effect confirmed) | low slot |
| Shield Power Relay I | PASS | PASS | PASS offline/online toggle | passive; no activation path |
| Salvager I | PASS | PASS | **CRITICAL — server segfault** on no-target activate | COMP-A below |
| XR-3200 Heavy Missile Bay | PASS | PASS | LoadAmmoToModules PASS; **CRITICAL — server segfault** on no-target activate | COMP-B below |

`LoadAmmoToModules(shipID, [moduleID], chargeTypeID, chargeItemID, shipID)`
correctly split 35 units (launcher capacity) off the 1000-unit cargo stack
into the launcher slot and did not double-load on re-runs.

## CRITICAL findings (reproduced server crashes)

### COMP-A: Salvager activated with no target segfaults the server
`Activate(salvagerID, WStr("salvaging"), None, 1)` on an **online** Salvager I
with no target crashes eve-server (`start.sh: line 35: 33 Segmentation fault
(core dumped) ./eve-server`, 19:50Z). Root cause, `src/eve-server/ship/modules/Prospector.cpp:74-84`:

```cpp
bool Prospector::CanActivate()
{
    if (m_salvager)
        if (m_targetSE->IsWreckSE())   // m_targetSE is nullptr when no target given
            return ActiveModule::CanActivate();
```

`ActiveModule::Activate()` only assigns `m_targetSE` when `IsValidTarget(targetID)`
(ActiveModule.cpp:339); with target 0/None it stays null and the virtual call
dereferences it. Neither `DogmaIMBound::Activate` nor `ModuleManager::Activate`
validates that a target-required effect actually has a target.
Fix suggestion: null-check `m_targetSE` in `Prospector::CanActivate()` (throw
`DeniedActivateTargetModuleDisallowed`), and/or reject target-less activation
of targeted effects in `MM::Activate`.

### COMP-B: Missile launcher activated with no target segfaults the server
`Activate(launcherID, WStr("useMissiles"), None, 1)` on an **online, loaded**
XR-3200 crashes eve-server (second segfault, 19:53Z). The launch is accepted,
a missile entity is actually spawned (`II::C'tor - Created Generic Item ...
Scourge Heavy Missile (1000000001)` immediately before the crash), then the
missile's processing dereferences its null target: `src/eve-server/ship/Missile.cpp`
uses `m_targetSE` unchecked (ctor arg, lines 252/258/271 — `GetAttribute`,
`GetVelocity`, `ApplyDamage`). Any client can crash the node this way with one
packet. Same fix family as COMP-A: validate target before launch.

No gdb backtrace appeared in docker logs (the in-container wrapper reports the
shell-level `Segmentation fault (core dumped)` and respawns eve-server); the
crash sites above were pinned by code inspection plus the log timeline.

## HIGH findings (silent failure modes that invalidate naive QA)

### COMP-C: Unmatched bound-call signatures are silently dropped — client sees SUCCESS
`Activate`/`Deactivate` on the dogma bound object require the effect name as
**PyWString** (`WStr`), per the overload registrations in
`src/eve-server/dogmaim/DogmaIMService.cpp:86-89`. Sending a plain `str`
(PyString) matches no overload; the server logs
`Client::CallReq: Unable to find method to handle call to: ::Activate`
(empty candidate list) **and returns a normal success response**. The client
has no way to know the call did nothing.
Consequence for existing tools: `fleet_trio_test.py:166` and
`escort_trader.py:167` pass plain-str effect names — their weapon activations
have been silent no-ops all along (explains "rats not dying" symptoms in the
fleet trial). Recommend: error response on unmatched overloads, and sweep the
sim tools for str→WStr effect names.

### COMP-D: Activating an OFFLINE module returns SUCCESS
`ModuleManager::Activate` (ModuleManager.cpp:707) catches the offline case
with `SendErrorMsg("You cannot activate an offline module. Ref: ServerError
25164")` — an OnRemoteMessage notification — and returns normally, so the
call itself succeeds. Any bot/QA that trusts the call response records false
PASSes. The harness now verdicts from captured notifications
(OnGodmaShipEffect / OnModuleAttributeChange / OnRemoteMessage) instead.

### COMP-E: Phantom "warping" destiny state after undock blocks module ops
For tens of seconds after `Undock` (observed 15-40s, nondeterministic even
after `CmdStop`), module calls are rejected with `UserError
DeniedActivateInWarp` and `SetModuleOnline` with the OnRemoteMessage
"You can't do this while warping". Interacts with the known DESTINY-6 family
(warp-align state surviving undock pushes). The harness waits 45s after
undock; with that settle, all onlining/activation succeeded. Related destiny
noise seen while stopped near the station: repeated
`Destiny::MoveObject(): ... move checks are not set right. Acc:False,
Dec:False, Turn:False, Tic:0 ...` errors.

## MEDIUM / notes

- **Docked online state does not carry into space deterministically**: after
  onlining all modules docked, the first undocked run showed every module
  offline in space (all activations hit COMP-D silently); modules had
  `isOnline=0` in entity_attributes after logout. Onlining again in space
  works and is confirmed by `OnModuleAttributeChange` (attr 2 → 1, with CPU
  (49) and powergrid (15) load updates). The harness onlines both docked
  (path test) and in space (before activation).
- DB-staged modules (direct `entity` inserts while the char is offline) load
  fine on next login without a server restart — `ItemGetInfo` served all 8,
  `Created ModuleItem` in logs. No item-cache blocker for module staging.
- `SetModuleOnline`/`TakeModuleOffline` signature is `(shipID, moduleID)`;
  passive modules (Shield Power Relay I) toggle cleanly in space.
- Effect names came from `dgmTypeEffects` (attributeID 10 rows are absent in
  this dump; `isDefault` is unreliable — the working names used:
  `speedBoostMassAddition`, `shieldBoosting`,
  `modifyActiveShieldResonanceAndNullifyPassiveResonance`, `surveyScan`,
  `armorRepair`, `salvaging`, `useMissiles`).
- "Kinetic Deflection Field I" does not exist in Crucible data; the kinetic
  active shield hardener is **Ballistic Deflection Field I** (typeID 2291).
- Crash cleanup: both segfaults stranded Tal in space; recovery = offline DB
  update (ship+capsule locationID → station, flag 4; chrCharacters.stationID).
  A transient missile entity (1000000001) was in-memory only — no DB orphan.

## Reproduction

```
# stage (char offline): modules + ammo + skills, see harness header
python tools/simfleet/component_qa.py            # safe matrix (25 checks)
python tools/simfleet/component_qa.py --crash-probe   # ALSO fires COMP-A/B (WILL segfault)
```

Final safe-matrix run: 25 results — 23 PASS, 2 CRITICAL (the skipped known
crashers, reproduced earlier the same day).

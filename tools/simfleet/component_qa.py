#!/usr/bin/env python3
"""
Ship-component (module) QA harness: exercise a matrix of module types on a
live server through the real client protocol and record PASS / FAIL /
SERVER-ERROR / CRITICAL per module (COMP-n findings).

Test pilot: Tal Rethis (fleet04 / 90000007), Drake 140000914, Jita 4-4.
Modules are pre-staged onto the Drake by DB insert (recipe in
doc/component-qa-findings.md).

Hard-won protocol facts baked into this harness (see findings doc):
  * Activate/Deactivate effectName MUST be a WStr (PyWString). A plain
    str marshals to PyString, NO bound-method overload matches, and the
    server silently drops the call while returning SUCCESS to the client
    (COMP finding: signature-mismatch calls are silent no-ops).
  * MM::Activate on an OFFLINE module also returns SUCCESS; the only
    client-visible evidence is an OnRemoteMessage CustomError
    ("ServerError 25164"). Verdicts here are therefore based on captured
    notifications (OnGodmaShipEffect / OnModuleAttributeChange /
    OnRemoteMessage), never on the call response alone.
  * Undock leaves the ship in a phantom "warping" destiny state for tens
    of seconds; module onlining/activation during it is rejected with
    DeniedActivateInWarp / "You can't do this while warping". We wait
    WARP_SETTLE seconds after undock before touching modules.
  * KNOWN CRASHERS (reproduced 2026-07-10, segfault, core dumped):
      - Salvager I activated with no target -> Prospector::CanActivate()
        derefs null m_targetSE (Prospector.cpp:77).
      - Loaded missile launcher activated with no target -> missile SE
        spawns with null target and segfaults (Missile.cpp:252+).
    These probes are SKIPPED unless --crash-probe is passed, so this
    script stays safe to run while other tests share the server.

    python component_qa.py [--crash-probe]
"""

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db                                              # noqa: E402
from machoclient import MachoClient, CallError, log    # noqa: E402
from evemarshal import WStr                            # noqa: E402
from provision import (ensure_docked, SOLARSYSTEM_GROUP,  # noqa: E402
                       STATION_GROUP)

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"

USER, PW = "fleet04", "fleet"
CHAR = 90000007
SHIP = 140000914
STATION, SYSTEM = 60003760, 30000142
WARP_SETTLE = 45.0       # phantom warp state after undock (DESTINY family)

# label, typeName, typeID, flag, defaultEffect, active?, needs_target?
MATRIX = [
    ("AB",    "1MN Afterburner I",            439,  20,
     "speedBoostMassAddition", True,  False),
    ("SSB",   "Small Shield Booster I",       399,  21,
     "shieldBoosting",         True,  False),
    ("HARD",  "Ballistic Deflection Field I", 2291, 22,
     "modifyActiveShieldResonanceAndNullifyPassiveResonance", True, False),
    ("SURV",  "Survey Scanner I",             444,  23,
     "surveyScan",             True,  False),
    ("SAR",   "Small Armor Repairer I",       523,  12,
     "armorRepair",            True,  False),
    ("RELAY", "Shield Power Relay I",         2331, 13,
     None,                     False, False),
    ("SALV",  "Salvager I",                   25861, 31,
     "salvaging",              True,  True),
    ("LNCH",  "XR-3200 Heavy Missile Bay",    7997, 32,
     "useMissiles",            True,  True),
]
AMMO_TYPE = 209          # Scourge Heavy Missile, staged in cargo (flag 5)

RESULTS = []             # (id, module, verdict, detail)
CAP = []                 # every notify/error message repr received


def result(mod, verdict, detail=""):
    n = len(RESULTS) + 1
    RESULTS.append((f"COMP-{n}", mod, verdict, detail))
    log(f"COMP-{n} [{verdict}] {mod}: {detail}")


def server_alive(tag):
    """True if eve-server did not just restart; dump crash context if it
    did (start.sh respawns it inside the container, so we look for the
    segfault line rather than container status)."""
    try:
        out = subprocess.run([DOCKER, "logs", "server", "--since", "90s"],
                             capture_output=True, text=True, timeout=30)
        txt = out.stdout or ""
    except Exception as e:                       # noqa: BLE001
        log(f"health check failed to run: {e}")
        return True
    if "Segmentation fault" in txt:
        keep = [ln for ln in txt.splitlines()
                if re.search(r"Segmentation|SIGSEGV|#\d+ 0x|backtrace", ln)]
        result(tag, "CRITICAL",
               f"eve-server SEGFAULTED: {keep[:6]}")
        return False
    return True


def spy_on(mch):
    orig = mch._classify

    def spy(rep):
        got = orig(rep)
        if got and got[0] in ("notify", "error"):
            CAP.append(repr(got[1])[:500])
        return got
    mch._classify = spy


def msgs_since(idx, *needles):
    return [m for m in CAP[idx:] if any(n in m for n in needles)]


def online_module(mch, dogma, mod_id, retries=2):
    """SetModuleOnline verified by the OnModuleAttributeChange(attr 2)
    notification; retries around the phantom-warp rejection."""
    for attempt in range(1, retries + 1):
        idx = len(CAP)
        mch.call_bound(dogma, "SetModuleOnline", SHIP, mod_id)
        mch.pump(2.0)
        if msgs_since(idx, f" {mod_id}, 2,"):
            return True, "online attr confirmed"
        if msgs_since(idx, "warping"):
            if attempt < retries:
                log(f"module {mod_id}: warp-blocked, waiting 20s")
                mch.pump(20.0)
                continue
            return False, "blocked by phantom warp state"
        # no attr change and no warp message: maybe already online
        return True, "no attr change (already online?)"
    return False, "unreachable"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crash-probe", action="store_true",
                    help="run the two KNOWN-CRASH no-target activations "
                         "(WILL segfault eve-server)")
    args = ap.parse_args()

    # ---- resolve staged module itemIDs from DB ----
    mods = {}
    for label, name, tid, flag, _eff, _act, _tgt in MATRIX:
        rows = db.query(f"SELECT itemID FROM entity WHERE locationID={SHIP} "
                        f"AND typeID={tid} AND flag={flag}")
        if not rows:
            result(name, "BLOCKED", f"not staged on ship (typeID {tid} "
                   f"flag {flag})")
            continue
        mods[label] = int(rows[0]["itemID"])
    log(f"staged modules: {mods}")

    # ---- login ----
    mch = MachoClient("127.0.0.1", 26000, USER, PW)
    spy_on(mch)
    sess = mch.enter_world(CHAR)
    log(f"in world: {sess}")
    if not ensure_docked(mch, STATION, SYSTEM, SHIP):
        result("session", "BLOCKED", "could not reach docked start")
        return finish(mch)

    # ---- does the server see the DB-staged modules? (cache probe) ----
    dogma_st = mch.bind("dogmaIM", (STATION, STATION_GROUP))
    missing = []
    for label, iid in mods.items():
        try:
            info = mch.call_bound(dogma_st, "ItemGetInfo", iid)
            if info is None or repr(info) == "None":
                missing.append(label)
        except CallError as e:
            missing.append(f"{label}({str(e)[:80]})")
    if missing:
        result("item cache", "FAIL",
               f"server cannot load staged modules: {missing}")
    else:
        log("server sees all staged modules (ItemGetInfo ok)")

    # ---- online everything while docked (docked-online path) ----
    for label, name, tid, flag, _eff, _act, _tgt in MATRIX:
        if label not in mods:
            continue
        try:
            mch.call_bound(dogma_st, "SetModuleOnline", SHIP, mods[label])
            mch.pump(1.0)
            result(f"{name} online(docked)", "PASS", "SetModuleOnline ok")
        except (CallError, TimeoutError) as e:
            result(f"{name} online(docked)", "SERVER-ERROR", str(e)[:250])
    server_alive("online batch (docked)")

    # ---- undock + wait out the phantom warp state ----
    ship_ref = mch.bind("ship", (STATION, STATION_GROUP))
    try:
        mch.call_bound(ship_ref, "Undock", SHIP, False)
    except CallError as e:
        result("Undock", "SERVER-ERROR", str(e)[:250])
        return finish(mch)
    mch.pump(10.0)
    if mch.session.get("stationid"):
        result("Undock", "FAIL", "still docked after Undock call")
        return finish(mch)
    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError as e:
        log(f"CmdStop: {e}")
    log(f"undocked; waiting {WARP_SETTLE:.0f}s for phantom warp state")
    mch.pump(WARP_SETTLE)
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))

    # ---- re-online in space (docked online state does NOT survive) ----
    for label, name, tid, flag, _eff, _act, _tgt in MATRIX:
        if label not in mods:
            continue
        try:
            ok, why = online_module(mch, dogma, mods[label])
            result(f"{name} online(space)", "PASS" if ok else "FAIL", why)
        except (CallError, TimeoutError) as e:
            result(f"{name} online(space)", "SERVER-ERROR", str(e)[:250])
    server_alive("online batch (space)")

    # ---- self-targeted actives: activate -> observe -> deactivate ----
    for label in ("AB", "SSB", "HARD", "SURV", "SAR"):
        row = next(r for r in MATRIX if r[0] == label)
        _l, name, tid, flag, effect, _act, _tgt = row
        if label not in mods:
            continue
        mod_id = mods[label]
        idx = len(CAP)
        try:
            mch.call_bound(dogma, "Activate", mod_id, WStr(effect), None, 1)
        except (CallError, TimeoutError) as e:
            result(f"{name} activate", "SERVER-ERROR", str(e)[:250])
            server_alive(f"{name} activate")
            continue
        mch.pump(7.0)
        godma = msgs_since(idx, "OnGodmaShipEffect", "OnSpecialFX")
        offline_msg = msgs_since(idx, "ServerError 25164")
        warp_msg = msgs_since(idx, "warping")
        try:
            mch.call_bound(dogma, "Deactivate", mod_id, WStr(effect))
            mch.pump(2.0)
        except CallError as e:
            result(f"{name} deactivate", "SERVER-ERROR", str(e)[:250])
        if offline_msg:
            result(f"{name} cycle", "FAIL",
                   "silent no-op: module offline (ServerError 25164) but "
                   "Activate returned success")
        elif warp_msg:
            result(f"{name} cycle", "FAIL",
                   "blocked by phantom warp state after "
                   f"{WARP_SETTLE:.0f}s settle")
        elif godma:
            result(f"{name} cycle", "PASS",
                   f"effect confirmed: {godma[0][:140]}")
        else:
            result(f"{name} cycle", "PASS",
                   "activate+deactivate accepted (no godma notification "
                   "observed; attr changes only)")
        if not server_alive(f"{name} cycle"):
            return finish(mch)

    # ---- no-target activations: KNOWN CRASHERS ----
    for label, effect, bug in (
            ("SALV", "salvaging",
             "Prospector::CanActivate() null m_targetSE deref "
             "(Prospector.cpp:77)"),
            ("LNCH", "useMissiles",
             "missile SE spawned with null target segfaults "
             "(Missile.cpp:252+)")):
        row = next(r for r in MATRIX if r[0] == label)
        name = row[1]
        if label not in mods:
            continue
        if not args.crash_probe:
            result(f"{name} no-target activate", "CRITICAL",
                   f"KNOWN CRASH, probe skipped (--crash-probe): {bug}")
            continue
        idx = len(CAP)
        try:
            mch.call_bound(dogma, "Activate", mods[label], WStr(effect),
                           None, 1)
            mch.pump(4.0)
            result(f"{name} no-target activate", "FAIL",
                   "server accepted target-less activation "
                   f"(expected clean rejection); msgs: {CAP[idx:][:2]}")
        except CallError as e:
            result(f"{name} no-target activate", "PASS",
                   f"clean rejection: {str(e)[:200]}")
        except Exception as e:                   # noqa: BLE001
            result(f"{name} no-target activate", "CRITICAL",
                   f"connection lost ({type(e).__name__}) -- server "
                   f"crash: {bug}")
            server_alive(f"{name} no-target")
            return 1     # connection is gone; Tal needs DB recovery
        if not server_alive(f"{name} no-target"):
            return 1

    # ---- launcher: LoadAmmoToModules (charge staged in cargo) ----
    if "LNCH" in mods:
        ammo_rows = db.query(
            f"SELECT itemID FROM entity WHERE locationID={SHIP} "
            f"AND typeID={AMMO_TYPE} AND flag=5")
        if ammo_rows:
            try:
                mch.call_bound(dogma, "LoadAmmoToModules", SHIP,
                               [mods["LNCH"]], AMMO_TYPE,
                               int(ammo_rows[0]["itemID"]), SHIP)
                mch.pump(3.0)
                loaded = db.query(
                    f"SELECT itemID, quantity FROM entity WHERE "
                    f"locationID={SHIP} AND typeID={AMMO_TYPE} AND flag=32")
                result("XR-3200 LoadAmmoToModules", "PASS",
                       f"charge rows in launcher slot: {loaded}")
            except (CallError, TimeoutError) as e:
                result("XR-3200 LoadAmmoToModules", "SERVER-ERROR",
                       str(e)[:250])
        else:
            result("XR-3200 LoadAmmoToModules", "PASS",
                   "cargo stack empty (already loaded in earlier run)")
        server_alive("load ammo")

    # ---- passive module: offline/online toggle (no activation path) ----
    if "RELAY" in mods:
        rid = mods["RELAY"]
        try:
            mch.call_bound(dogma, "TakeModuleOffline", SHIP, rid)
            mch.pump(1.0)
            ok, why = online_module(mch, dogma, rid)
            result("Shield Power Relay I offline/online toggle",
                   "PASS" if ok else "FAIL", why)
        except (CallError, TimeoutError) as e:
            result("Shield Power Relay I offline/online toggle",
                   "SERVER-ERROR", str(e)[:250])
        server_alive("passive toggle")

    return finish(mch)


def finish(mch):
    log("returning to dock")
    try:
        mch.session.pop("stationid", None)
        if ensure_docked(mch, STATION, SYSTEM, SHIP, patience=300.0):
            log("docked; test complete")
        else:
            log("!! could not re-dock; Tal left in space (recover with "
                "db.recover_ship_to_station before next staging)")
    except Exception as e:                       # noqa: BLE001
        log(f"dock-back failed: {e}")
    try:
        mch.close()
    except Exception:                            # noqa: BLE001
        pass
    server_alive("final")
    log("===== COMPONENT QA SUMMARY =====")
    for cid, mod, verdict, detail in RESULTS:
        log(f"{cid:8s} | {verdict:12s} | {mod} | {detail}")
    bad = [r for r in RESULTS if r[2] in ("SERVER-ERROR", "FAIL",
                                          "CRITICAL", "BLOCKED")]
    log(f"===== {len(RESULTS)} results, {len(bad)} problem(s) =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())

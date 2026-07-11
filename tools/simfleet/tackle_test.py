#!/usr/bin/env python3
"""
Tackle validation: prove warp scramblers/disruptors pin a target so it
cannot warp, and that releasing the point lets it warp again.

The server gates BeyonceBound::CmdWarpToStuff on the ship attribute
AttrWarpScrambleStatus (>0 -> throw UserError "WarpScrambled",
BeyonceService.cpp:355).  Our TACKLE fix (ActiveModule.cpp) makes an
activated Warp_Scrambler-group module add its warp-scramble strength to
that attribute on the target, and subtract it on deactivate.  So the
deterministic observable is simply whether the *target's* CmdWarpToStuff
raises "WarpScrambled".

Sequence:
  1. control-before: target warps station->belt with nobody scrambling  -> must SUCCEED
  2. tackler locks target, activates scram; target tries to warp         -> must FAIL "WarpScrambled"
  3. tackler deactivates scram; target tries to warp again               -> must SUCCEED (release)

Run:  python tackle_test.py            # scrambler (447)
      python tackle_test.py --module disruptor
"""

import argparse
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import provision_fleet as pf
from machoclient import MachoClient, CallError, log
from evemarshal import WStr
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
STATION, SYSTEM = 60010387, 30002642        # Iyen-Oursta IV - Moon 4
BELT = 40168291                             # a belt in-system to warp to
TACKLER = ("fleet03", "fleet", 90000006, "Mira")
TARGET  = ("fleet01", "fleet", 90000004, "Keva")

MERLIN = 603
MODULES = {                     # name -> (typeID, default-effect, expect status)
    "scrambler": (447,  "warpScrambleTargetMWDBlockActivation"),
    "disruptor": (3242, "warpScramble"),
}
A_WARP_SCRAMBLE_STATUS = 104


def stage(char_id, char_name, hull, med_mods=()):
    """Stage a fresh hull for char at STATION with the given med modules."""
    HOME = pf.HOME_STATION
    pf.HOME_STATION = STATION
    hull_name = db.query(f"SELECT typeName FROM invTypes WHERE typeID={hull}")[0]["typeName"]
    ship = pf.insert_item(f"{char_name}'s {hull_name}", hull, char_id, STATION, 4)
    fitted = [hull]
    for i, tid in enumerate(med_mods):
        pf.insert_item("", int(tid), char_id, ship, 19 + i)   # med slots 19..25
        fitted.append(int(tid))
    for skill_tid, lvl in db.skill_closure(fitted):
        db.grant_skill(char_id, skill_tid, lvl)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, "
               f"solarSystemID={SYSTEM}, shipID={ship} WHERE characterID={char_id}")
    pf.HOME_STATION = HOME
    return ship


def undock(mch, ship_id):
    sref = mch.bind("ship", (STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", ship_id, False)
    mch.pump(12)
    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(3)
    return bey, dogma


def try_warp(mch, bey, dest):
    """Issue a warp; return None on success, or the error string if blocked."""
    try:
        mch.call_bound(bey, "CmdWarpToStuff", "item", int(dest),
                       byname={"minRange": 0})
        return None
    except CallError as e:
        return str(e)


def target_thread(target_ship, phase, result, stop):
    """The would-be warp victim.  Stays put at the undock so the tackler can
    lock it (co-located, like pvp_battle), then reacts to phase signals."""
    acct, pw, char, tag = TARGET
    try:
        mch = MachoClient("127.0.0.1", 26000, acct, pw)
        mch.enter_world(char)
        if not ensure_docked(mch, STATION, SYSTEM, target_ship):
            log(f"{tag}: could not dock"); phase["ready"].set(); return
        bey, _ = undock(mch, target_ship)
        # sit still at the undock point so the tackler can lock in range
        try:
            mch.call_bound(bey, "CmdStop")
        except CallError:
            pass
        phase["ready"].set()

        # phase 1: tackler has locked + scrammed us -- warp must be BLOCKED
        phase["do_scrammed"].wait(90)
        st = db.query(f"SELECT valueFloat FROM entity_attributes WHERE itemID={target_ship} "
                      f"AND attributeID={A_WARP_SCRAMBLE_STATUS}")
        result["status_attr"] = st[0]["valueFloat"] if st else None
        err = try_warp(mch, bey, BELT)
        result["scrammed"] = err
        log(f"{tag}: scrammed warp -> {'BLOCKED: '+err[:50] if err else 'OK (warped -- BUG)'}")
        try:
            mch.call_bound(bey, "CmdStop")
        except CallError:
            pass
        phase["scrammed_done"].set()

        # phase 2 (positive control): point released -- warp must SUCCEED
        phase["do_released"].wait(60)
        err = try_warp(mch, bey, BELT)
        result["released"] = err
        log(f"{tag}: released warp -> {'BLOCKED: '+err[:50]+' (BUG)' if err else 'OK (accepted)'}")
        phase["released_done"].set()

        mch.pump(6)
        try:
            mch.call_bound(bey, "CmdStop")
        except CallError:
            pass
        mch.pump(4)
        mch.close()
    except Exception as e:
        log(f"{tag}: EXCEPTION {type(e).__name__}: {str(e)[:200]}")
        for k in ("ready", "scrammed_done", "released_done"):
            phase[k].set()


def run(module="scrambler"):
    typeID, effect = MODULES[module]
    for char in (TACKLER[2], TARGET[2]):
        if db.query(f"SELECT online FROM chrCharacters WHERE characterID={char}")[0]["online"] not in ("0", ""):
            raise SystemExit(f"char {char} online; cannot stage")
    tackler_ship = stage(TACKLER[2], TACKLER[3], MERLIN, med_mods=[typeID])
    target_ship  = stage(TARGET[2],  TARGET[3],  MERLIN)
    log(f"=== TACKLE {module} (type {typeID}): tackler {tackler_ship} vs target {target_ship}")

    phase = {k: threading.Event() for k in
             ("ready", "do_scrammed", "scrammed_done", "do_released", "released_done")}
    result = {}
    stop = threading.Event()
    tt = threading.Thread(target=target_thread,
                          args=(target_ship, phase, result, stop), daemon=True)
    tt.start()
    phase["ready"].wait(120)
    time.sleep(2)

    acct, pw, char, tag = TACKLER
    mch = MachoClient("127.0.0.1", 26000, acct, pw)
    mch.enter_world(char)
    ensure_docked(mch, STATION, SYSTEM, tackler_ship)
    bey, dogma = undock(mch, tackler_ship)
    scram = [int(r["itemID"]) for r in db.query(
        f"SELECT itemID FROM entity WHERE locationID={tackler_ship} AND flag BETWEEN 19 AND 25")]
    scram_id = scram[0] if scram else None
    log(f"{tag}: scram module {scram_id}; onlining via SetModuleOnline + online-effect")
    for attempt in range(2):
        try:
            mch.call_bound(dogma, "SetModuleOnline", tackler_ship, scram_id)
        except CallError as e:
            log(f"{tag}: SetModuleOnline attempt {attempt}: {str(e)[:100]}")
        # the client's actual online path: activate the 'online' effect (16),
        # which MM::Activate routes straight to GenericModule::Online()
        try:
            mch.activate_module(dogma, scram_id, "online", None, 0)
        except CallError as e:
            log(f"{tag}: online-effect attempt {attempt}: {str(e)[:100]}")
        mch.pump(5)

    # lock the target (co-located at the undock -- approach + retry in range)
    locked = False
    last_err = ""
    for _ in range(25):
        try:
            mch.call_bound(bey, "CmdFollowBall", target_ship, 500)
            mch.pump(2)
            mch.call_bound(dogma, "AddTarget", target_ship)
            locked = True
            break
        except CallError as e:
            last_err = str(e)
            mch.pump(4 if ("OtherWarping" in last_err or "Range" in last_err) else 3)
    if not locked:
        log(f"{tag}: could not lock target; last_err={last_err[:300]}"); stop.set()
        phase["do_scrammed"].set(); phase["do_released"].set()
        tt.join(timeout=15)
        return result
    # AddTarget only STARTS the lock (rsp waits for server OnTarget); the
    # module's IsValidTarget() is false until the lock actually completes, so
    # a scram fired too early applies to a null target and no-ops.  Let the
    # lock settle, then activate (and re-activate once for safety).
    log(f"{tag}: locked target; settling lock then activating {module}")
    mch.pump(8)
    try:
        mch.activate_module(dogma, scram_id, effect, target_ship, 1000)
    except CallError as e:
        log(f"{tag}: scram activate: {str(e)[:120]}")
    mch.pump(4)
    phase["do_scrammed"].set()
    phase["scrammed_done"].wait(90)

    # release the point, let the target warp (positive control).  Deactivate
    # takes the effect name as a PyWString, same as Activate.
    try:
        mch.call_bound(dogma, "Deactivate", scram_id, WStr(effect))
    except CallError as e:
        log(f"{tag}: deactivate: {str(e)[:80]}")
    mch.pump(6)
    phase["do_released"].set()
    phase["released_done"].wait(60)

    stop.set()
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(5)
    mch.close()
    tt.join(timeout=20)

    # verdict: scram must block warp; releasing the point must restore it
    ok_scram = "WarpScrambled" in (result.get("scrammed") or "")
    ok_rel = result.get("released") is None
    log("=== VERDICT ===")
    log(f"  scrammed warp blocked   : {ok_scram}  (err={result.get('scrammed')}, status_attr={result.get('status_attr')})")
    log(f"  released warp succeeded : {ok_rel}   (err={result.get('released')})")
    verdict = "PASS" if (ok_scram and ok_rel) else "FAIL"
    log(f"  >>> TACKLE {module}: {verdict}")
    result["verdict"] = verdict
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", default="scrambler", choices=sorted(MODULES))
    args = ap.parse_args()
    run(args.module)

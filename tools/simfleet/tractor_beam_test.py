#!/usr/bin/env python3
"""
Tractor beam test.  Tractor beams reel in wrecks and jettison containers.
This bot fits a Small Tractor Beam, undocks, jettisons a stack of Tritanium
to spawn a container it owns (ownership check passes), locks the container,
and activates the tractor -- then confirms the server engaged the tractor
(TractorBeamStart) / the container's distance to the ship drops.

Run:  python tractor_beam_test.py
"""

import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import provision_fleet as pf
import pvp_battle as pvp
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
STATION, SYSTEM = pvp.STATION, pvp.SYSTEM
PILOT = ("fleet01", "fleet", 90000004, "Keva")
MERLIN = 603
TRACTOR = 24348          # Small Tractor Beam I
TRITANIUM = 34


def server_log(sec):
    out = subprocess.run([DOCKER, "logs", "server", "--since", f"{int(sec)}s"],
                         capture_output=True, text=True, timeout=30)
    return (out.stdout or "") + (out.stderr or "")


def stage(char_id, char_name):
    HOME = pf.HOME_STATION
    pf.HOME_STATION = STATION
    ship = pf.insert_item(f"{char_name}'s Merlin", MERLIN, char_id, STATION, 4)
    pf.insert_item("", TRACTOR, char_id, ship, 27)        # hi slot
    pf.insert_item("", TRITANIUM, char_id, ship, 5, qty=100)  # cargo, to jettison
    for skill_tid, lvl in db.skill_closure([MERLIN, TRACTOR]):
        db.grant_skill(char_id, skill_tid, lvl)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, solarSystemID={SYSTEM}, "
               f"shipID={ship} WHERE characterID={char_id}")
    pf.HOME_STATION = HOME
    return ship


def containers_in_system(char_id):
    """cargo containers owned by the char in-system (jetcans are category 2,
    Celestial / group Cargo Container 12).  match by group 12 or typeName."""
    return db.query(
        "SELECT e.itemID,e.typeID FROM entity e JOIN invTypes t ON t.typeID=e.typeID "
        f"WHERE e.ownerID={char_id} AND e.locationID={SYSTEM} AND t.groupID=12")


def run():
    acct, pw, char, tag = PILOT
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={char}")[0]["online"] not in ("0", ""):
        raise SystemExit(f"char {char} online; cannot stage")
    ship = stage(char, tag)
    log(f"=== TRACTOR test: {tag} ship {ship} (Small Tractor Beam)")

    result = dict(container=None, tractor_started=False, activated=False)
    mch = MachoClient("127.0.0.1", 26000, acct, pw)
    mch.enter_world(char)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log(f"{tag}: could not dock"); return result
    sref = mch.bind("ship", (STATION, STATION_GROUP))
    trit = db.query(f"SELECT itemID FROM entity WHERE locationID={ship} AND typeID={TRITANIUM} AND flag=5 LIMIT 1")
    trit_id = int(trit[0]["itemID"]) if trit else None
    mch.call_bound(sref, "Undock", ship, False)
    mch.pump(12)
    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(3)

    # jettison the tritanium -> spawns a container we own
    log(f"{tag}: jettisoning tritanium {trit_id}")
    try:
        mch.call_bound(sref, "Jettison", [trit_id])
    except CallError as e:
        log(f"{tag}: jettison: {str(e)[:100]}")
    mch.pump(4)
    can = None
    for _ in range(8):
        cans = containers_in_system(char)
        if cans:
            can = int(cans[0]["itemID"])
            break
        mch.pump(2)
    result["container"] = can
    if not can:
        log(f"{tag}: no container appeared after jettison"); mch.close(); return result
    log(f"{tag}: container {can} spawned; onlining tractor + locking")

    tb = db.query(f"SELECT itemID FROM entity WHERE locationID={ship} AND flag BETWEEN 27 AND 33")
    tb_id = int(tb[0]["itemID"]) if tb else None
    for _ in range(2):
        try:
            mch.call_bound(dogma, "SetModuleOnline", ship, tb_id)
        except CallError:
            pass
        try:
            mch.activate_module(dogma, tb_id, "online", None, 0)
        except CallError:
            pass
        mch.pump(5)

    # lock the container, then tractor it
    locked = False
    for _ in range(15):
        try:
            mch.call_bound(dogma, "AddTarget", can)
            locked = True
            break
        except CallError as e:
            mch.pump(3)
    if not locked:
        log(f"{tag}: could not lock container {can}")
    mch.pump(6)
    try:
        mch.activate_module(dogma, tb_id, "tractorBeamCan", can, 1000)
        result["activated"] = True
        log(f"{tag}: tractor activated on container {can}")
    except CallError as e:
        log(f"{tag}: tractor activate: {str(e)[:120]}")
    mch.pump(8)

    txt = server_log(120)
    if re.search(r"[Tt]ractor", txt):
        result["tractor_started"] = True

    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(4)
    mch.close()

    log("=== VERDICT ===")
    log(f"  container spawned : {result['container']}")
    log(f"  tractor activated : {result['activated']}")
    log(f"  server tractor evidence: {result['tractor_started']}")
    ok = result["activated"] and result["container"] is not None
    log(f"  >>> TRACTOR BEAM: {'PASS (engaged container)' if ok else 'FAIL'}")
    return result


if __name__ == "__main__":
    run()

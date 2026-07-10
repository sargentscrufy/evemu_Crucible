#!/usr/bin/env python3
"""
COMP-G diagnostic: Mira, DOCKED, boards her railgun Cormorant, onlines a
gun, loads ammo, and tries to read the loaded state.  No combat -- pure
ammo-loading isolation.  Server MODULE trace shows the LoadCharge path.

    python ammo_load_diag.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, STATION_GROUP, SOLARSYSTEM_GROUP

ACCOUNT, PW, CHAR = "fleet03", "fleet", 90000006
STATION, SYSTEM = 60010387, 30002642


def main():
    ship = int(db.query(
        f"SELECT shipID FROM chrCharacters WHERE characterID={CHAR}")[0]["shipID"])
    guns = [int(r["itemID"]) for r in db.query(
        f"SELECT itemID FROM entity WHERE locationID={ship} AND flag BETWEEN 27 AND 34")]
    charge = db.query(
        f"SELECT itemID, typeID FROM entity WHERE locationID={ship} AND flag=5 LIMIT 1")
    log(f"ship={ship} guns={guns} charge={charge}")
    if not guns or not charge:
        log("DIAG: missing guns or charge in cargo; aborting")
        return 1
    cid, ctype = int(charge[0]["itemID"]), int(charge[0]["typeID"])

    mch = MachoClient("127.0.0.1", 26000, ACCOUNT, PW)
    mch.enter_world(CHAR)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log("DIAG: not docked; aborting")
        return 1
    log("docked; dogma bind")
    dogma = mch.bind("dogmaIM", (STATION, STATION_GROUP))

    g = guns[0]
    try:
        mch.call_bound(dogma, "SetModuleOnline", ship, g)
        mch.pump(3)
        log(f"onlined gun {g}")
    except CallError as e:
        log(f"DIAG: online failed: {e}")

    try:
        mch.call_bound(dogma, "LoadAmmoToModules", ship, [g], ctype, cid, ship)
        mch.pump(4)
        log(f"LoadAmmoToModules returned OK for gun {g}, charge type {ctype}")
    except CallError as e:
        log(f"DIAG: load failed: {e}")

    # ground truth: did a charge item land in the gun's slot flag?
    gflag = db.query(f"SELECT flag FROM entity WHERE itemID={g}")[0]["flag"]
    incharge = db.query(
        f"SELECT itemID, typeID, quantity, flag FROM entity "
        f"WHERE locationID={ship} AND flag={gflag} AND typeID={ctype}")
    log(f"gun flag={gflag}; charge now in that slot: {incharge}")

    # try activating (docked activation will fail for a gun, but the error
    # tells us loaded-vs-not: 'not loaded' vs 'cannot activate docked')
    mch.close()
    log("DIAG complete -- inspect server MODULE trace for LoadCharge path")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
IND-5: Planetary Interaction colony validation loop.

Builds a colony on a planet via the `planetMgr` bound service and its
UserUpdateNetwork(commandList) batch RPC, then confirms server state.

Command tuples (UUNCommand = (commandInt, commandData)):
  CreatePin(1)          command center: (pinID, typeID, lat, long)
                        standard pin:   ((ccPinID, pinID), typeID, lat, long)
  UpgradeCommandCenter(9)  (pinID, level)
  InstallProgram(13)    (ecuPinID, resourceTypeID, headRadius)

Milestone 1 (this test): deploy a command center on a lava planet and verify
the colony row (piCCPin).  Deploying a CC charges 90k ISK and creates the
colony + a customs office; it does not consume a cargo item.  Extractor /
program / route / launch steps are layered on once the base works.

Run:  python pi_colony_test.py
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import provision_fleet as pf
from machoclient import MachoClient, CallError, log
from provision import ensure_docked

STATION, SYSTEM = 60010387, 30002642      # Iyen-Oursta (has lava planet 40168289)
PLANET = 40168289                          # Iyen-Oursta I (Lava)
CC_TYPE = 2145                             # Standard Lava Command Center
ECU_TYPE = 3062                            # Lava Extractor Control Unit
PILOT = ("fleet01", "fleet", 90000004, "Keva")

# PI command ids
CMD_CREATE_PIN = 1
CMD_UPGRADE_CC = 9
CMD_INSTALL_PROGRAM = 13


def stage(char_id, char_name):
    HOME = pf.HOME_STATION
    pf.HOME_STATION = STATION
    ship = pf.insert_item(f"{char_name}'s Ibis", 601, char_id, STATION, 4)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, solarSystemID={SYSTEM}, "
               f"shipID={ship}, balance=GREATEST(balance,1000000) WHERE characterID={char_id}")
    # clear any prior colony on this planet for a clean run
    db.execute(f"DELETE FROM piCCPin WHERE charID={char_id} AND planetID={PLANET}")
    db.execute(f"DELETE FROM piPlanets WHERE charID={char_id} AND planetID={PLANET}")
    pf.HOME_STATION = HOME
    return ship


def colony_rows(char_id):
    cc = db.query(f"SELECT pinID,typeID FROM piCCPin WHERE charID={char_id} AND planetID={PLANET}")
    return cc


def run():
    acct, pw, char, tag = PILOT
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={char}")[0]["online"] not in ("0", ""):
        raise SystemExit(f"char {char} online; cannot stage")
    ship = stage(char, tag)
    # a unique pinID for the command center (use a fresh entity id space)
    cc_pin = pf.insert_item("PI Command Center", CC_TYPE, char, STATION, 5)  # placeholder id
    log(f"=== IND-5 PI: {tag} deploy command center (pin {cc_pin}) on planet {PLANET}")

    result = dict(cc_created=False, cc_pin=cc_pin)
    mch = MachoClient("127.0.0.1", 26000, acct, pw)
    mch.enter_world(char)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log(f"{tag}: could not dock"); return result

    try:
        pm = mch.bind("planetMgr", PLANET)
        log(f"{tag}: bound planetMgr for planet {PLANET}")
    except CallError as e:
        log(f"{tag}: planetMgr bind FAILED: {str(e)[:160]}"); mch.close(); return result

    # command center: CreatePin (pinID, typeID, latitude, longitude).
    # Each command element must be a TUPLE (command, command_data) and the
    # command_data a TUPLE -- Python lists marshal as PyList and are rejected.
    cmd = (CMD_CREATE_PIN, (cc_pin, CC_TYPE, 1.5, 3.0))
    try:
        mch.call_bound(pm, "UserUpdateNetwork", [cmd])
        log(f"{tag}: UserUpdateNetwork(create CC) returned")
    except CallError as e:
        log(f"{tag}: UserUpdateNetwork FAILED: {str(e)[:200]}")
    mch.pump(2)
    mch.close()

    cc = colony_rows(char)
    result["cc_created"] = len(cc) > 0
    log("=== VERDICT ===")
    log(f"  command center row (piCCPin): {cc}")
    log(f"  >>> PI COMMAND CENTER: {'PASS' if result['cc_created'] else 'FAIL'}")
    return result


if __name__ == "__main__":
    run()

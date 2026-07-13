#!/usr/bin/env python3
"""
Live-fire target: an UNARMED industrial undocks from a station and flies
straight at normal speed until somebody destroys it.  Cargo is staged so
the wreck drops loot worth shooting.

Default: Enna Solis (fleet10) in a fresh Badger named 'Target Hauler',
cargo full of Nuclear M (300k rounds), undocking from Jita 4-4 Caldari
Navy Assembly Plant.  The bot holds course and never fights back; when the
ship dies the script logs the kill and leaves the wreck/pod alone.

    python target_hauler.py [--minutes 45]
"""

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import provision_fleet as pf
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

PORT = int(os.environ.get("EVE_PORT", "26010"))
# override with EVE_PILOT="acct:pw:charID:tag" -- pick a char the server
# hasn't cached since its last restart, or the docked staging won't stick
_p = os.environ.get("EVE_PILOT", "fleet10:fleet:90000013:Enna").split(":")
ACCT, PW, CHAR, TAG = _p[0], _p[1], int(_p[2]), _p[3]
STATION, SYSTEM = 60003760, 30000142          # Jita 4-4 CNAP
BADGER = 648
NUCLEAR_M = 187
CARGO_QTY = 300000                            # ~ full Badger hold


def ship_alive(item_id):
    return bool(db.query(f"SELECT itemID FROM entity WHERE itemID={item_id}"))


def stage():
    ship = pf.insert_item("Target Hauler", BADGER, CHAR, STATION, 4, qty=1, singleton=1)
    pf.insert_item("", NUCLEAR_M, CHAR, ship, 5, qty=CARGO_QTY, singleton=0)
    for skill_tid, lvl in db.skill_closure([BADGER]):
        db.grant_skill(CHAR, skill_tid, lvl)
    # locationID must be the STATION for a docked login -- the server keys
    # docked-vs-in-space off locationID, not stationID (staging only
    # stationID caused in-space logins warping to the fresh ship's 0,0,0)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, locationID={STATION}, "
               f"solarSystemID={SYSTEM}, shipID={ship} WHERE characterID={CHAR}")
    return ship


def run(minutes, resume=0):
    online = db.query(f"SELECT online FROM chrCharacters WHERE characterID={CHAR}")[0]["online"]
    if online not in ("0", "", 0):
        raise SystemExit(f"{TAG} ({CHAR}) is online; cannot stage")

    if resume:
        # ship already staged and sitting in space; log in, warp to the
        # target station's dock perimeter, then hold course from there
        ship = resume
        log(f"=== {TAG}: resuming as flying target in ship {ship} ===")
        mch = MachoClient("127.0.0.1", PORT, ACCT, PW)
        mch.enter_world(CHAR)
        mch.pump(12)
        bey0 = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
        try:
            mch.call_bound(bey0, "CmdStop")
        except CallError:
            pass
        mch.pump(3)
        try:
            mch.call_bound(bey0, "CmdWarpToStuff", "item", STATION, byname={"minRange": 0})
            log(f"{TAG}: warping to station {STATION}")
        except CallError as e:
            log(f"warp to station: {str(e)[:100]}")
        mch.pump(45)   # let the warp land
    else:
        ship = stage()
        log(f"=== {TAG}: 'Target Hauler' Badger {ship}, {CARGO_QTY} Nuclear M in cargo ===")
        staged = db.query(f"SELECT stationID, locationID FROM chrCharacters "
                          f"WHERE characterID={CHAR}")[0]
        log(f"{TAG}: pre-login DB state: {staged}")

        mch = MachoClient("127.0.0.1", PORT, ACCT, PW)
        mch.enter_world(CHAR)
        post = db.query(f"SELECT stationID, locationID FROM chrCharacters "
                        f"WHERE characterID={CHAR}")[0]
        log(f"{TAG}: post-login DB state: {post}")
        if not ensure_docked(mch, STATION, SYSTEM, ship):
            log("could not stage docked"); return

        sref = mch.bind("ship", (STATION, STATION_GROUP))
        mch.call_bound(sref, "Undock", ship, False)
        log(f"{TAG}: undocking from Jita 4-4 -- target is live")
        mch.pump(10)

    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    # a real heading (like a player double-clicking in space) -- speed alone
    # leaves destiny with a null target point after the undock push yields
    try:
        mch.call_bound(bey, "CmdGotoDirection", 0.577, 0.408, 0.707)
    except CallError as e:
        log(f"heading set: {str(e)[:80]}")
    try:
        mch.call_bound(bey, "CmdSetSpeedFraction", 1.0)
    except CallError as e:
        log(f"speed set: {str(e)[:80]}")

    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        try:
            mch.pump(8)
        except Exception as e:
            log(f"session hiccup ({str(e)[:60]}); checking hull")
        if not ship_alive(ship):
            log(f"=== {TAG}: Target Hauler DESTROYED -- good hunting. "
                f"Wreck and loot are yours. ===")
            try:
                mch.pump(10)
            except Exception:
                pass
            break
        # hold course: re-assert heading + speed occasionally in case
        # anything (bump, session change) zeroed them
        try:
            mch.call_bound(bey, "CmdGotoDirection", 0.577, 0.408, 0.707)
            mch.call_bound(bey, "CmdSetSpeedFraction", 1.0)
        except (CallError, Exception):
            pass
    else:
        log(f"{TAG}: nobody shot me in {minutes} min; going home")

    try:
        mch.close()
    except Exception:
        pass
    db.execute(f"UPDATE chrCharacters SET online=0 WHERE characterID={CHAR}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=45)
    ap.add_argument("--resume", type=int, default=0,
                    help="shipID already staged in space: skip stage/undock")
    args = ap.parse_args()
    run(args.minutes, args.resume)

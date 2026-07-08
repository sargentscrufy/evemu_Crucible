#!/usr/bin/env python3
"""
Hauler mission loop (sim-player): from the home station --

    undock -> fly ~clear_m at normal speed to clear the station
    -> warp to another station in the system -> dock -> dwell
    -> undock -> clear -> warp home -> dock -> dwell -> repeat

Every protocol rejection or unexpected state is logged with KINK: for
fleet monitoring. Exits nonzero on session loss so a supervisor can
restart it.

    python hauler_loop.py --account fleet07 --char-name "Ilsa Vayne" \
        [--cycles 0]   # 0 = run forever
"""

import argparse
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP


def kink(msg):
    log(f"KINK: {msg}")


def pump_for(mch, seconds):
    end = time.time() + seconds
    while time.time() < end:
        mch.pump(2.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--password", default="fleet")
    ap.add_argument("--char-name", required=True)
    ap.add_argument("--home-station", type=int, default=60003760)
    ap.add_argument("--system", type=int, default=30000142)
    ap.add_argument("--clear-m", type=int, default=3000)
    ap.add_argument("--dwell-s", type=int, default=30)
    ap.add_argument("--cycles", type=int, default=0)
    args = ap.parse_args()

    char = int(db.query(
        "SELECT characterID FROM chrCharacters WHERE characterName = "
        f"'{args.char_name}'")[0]["characterID"])
    stations = [int(r["stationID"]) for r in db.query(
        f"SELECT stationID FROM staStations WHERE solarSystemID = {args.system}")]
    others = [s for s in stations if s != args.home_station]

    mch = MachoClient("127.0.0.1", 26000, args.account, args.password)
    sess = mch.enter_world(char)
    ship = int(mch.session.get("shipid") or 0) or int(db.query(
        f"SELECT shipID FROM chrCharacters WHERE characterID = {char}")[0]["shipID"])
    log(f"{args.char_name}: in world, ship {ship}")

    if not ensure_docked(mch, args.home_station, args.system, ship):
        kink("could not reach docked start at home station")
        return 1

    # estimate clear time from hauler cruise speed (~110 m/s)
    clear_s = max(10, int(args.clear_m / 110) + 3)

    cycle = 0
    while args.cycles == 0 or cycle < args.cycles:
        cycle += 1
        dest = random.choice(others)
        t0 = time.time()
        log(f"cycle {cycle}: {args.home_station} -> {dest}")

        for leg_dest in (dest, args.home_station):
            # undock
            ship_ref = mch.bind("ship",
                                (int(mch.session.get("stationid") or args.home_station),
                                 STATION_GROUP))
            try:
                mch.call_bound(ship_ref, "Undock", ship, False)
            except CallError as e:
                kink(f"Undock rejected: {e}")
                return 1
            mch.pump(8.0)
            if mch.session.get("stationid"):
                kink("still docked after Undock")
                return 1

            # clear the station at normal speed (the undock push carries
            # us forward; just ride it for ~clear_m)
            pump_for(mch, clear_s)

            # warp to destination station
            bey = mch.bind("beyonce", (args.system, SOLARSYSTEM_GROUP))
            try:
                mch.call_bound(bey, "CmdWarpToStuff", "item", leg_dest,
                               byname={"minRange": 0})
            except CallError as e:
                kink(f"warp to {leg_dest} rejected: {e}")
            pump_for(mch, 95)

            # dock
            mch.session.pop("stationid", None)
            if not ensure_docked(mch, leg_dest, args.system, ship,
                                 patience=240.0):
                kink(f"failed to dock at {leg_dest}")
                return 1
            log(f"docked at {leg_dest}")
            pump_for(mch, args.dwell_s)

        log(f"cycle {cycle} complete in {time.time()-t0:.0f}s")

    mch.close()
    log(f"{args.char_name}: mission loop finished ({cycle} cycles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

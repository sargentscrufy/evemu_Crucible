#!/usr/bin/env python3
"""
SPAWN-11 live verification: trigger a belt wave, abandon it, wait out the
5-minute unwatched grace, and confirm the server despawns the stale wave
(watch docker logs for 'despawning stale wave'), then revisit to confirm
a fresh spawn cycle arms.

Sera flies her Merlin from Nomaa to Iyen-Oursta (0.8 sec, proven rat
country), pokes belt 40168291, retreats to the local station, and waits.

    python spawn11_probe.py
"""

import sys
import time

import travel
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

CHAR, SHIP = 90000014, 140001104
HOME_STATION, HOME_SYSTEM = 60004231, 30000131
RAT_SYSTEM, RAT_STATION, BELT = 30002642, 60010387, 40168291


def undock(mch, station, ship):
    sref = mch.bind("ship", (station, STATION_GROUP))
    mch.call_bound(sref, "Undock", ship, False)
    mch.pump(12)
    bey = travel.bind_beyonce(mch)
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(8)
    return bey


def main():
    mch = MachoClient("127.0.0.1", 26000, "qatest", "fleet")
    mch.enter_world(CHAR)
    if not ensure_docked(mch, HOME_STATION, HOME_SYSTEM, SHIP):
        log("SPAWN11: cannot reach docked start")
        return 1

    undock(mch, HOME_STATION, SHIP)
    log("flying to rat country...")
    if not travel.goto_station(mch, SHIP, RAT_STATION, min_security=0.45):
        log("SPAWN11: travel to rat system failed")
        return 1
    log("at rat station; poking the belt")

    bey = undock(mch, RAT_STATION, SHIP)
    mch.call_bound(bey, "CmdWarpToStuff", "item", BELT, byname={"minRange": 0})
    mch.pump(75)            # ride warp, linger so the wave spawns
    log("belt poked; retreating to station")
    mch.call_bound(bey, "CmdWarpToStuff", "item", RAT_STATION,
                   byname={"minRange": 0})
    mch.pump(70)
    mch.session.pop("stationid", None)
    if not ensure_docked(mch, RAT_STATION, RAT_SYSTEM, SHIP, patience=200.0):
        log("SPAWN11: failed to dock after poke")
        return 1
    log(f"docked at {time.strftime('%H:%M:%S')}; belt now unwatched. "
        "waiting 7 min for stale-wave despawn...")
    end = time.time() + 420
    while time.time() < end:
        mch.pump(5)

    # revisit: fresh spawn cycle should arm
    bey = undock(mch, RAT_STATION, SHIP)
    mch.call_bound(bey, "CmdWarpToStuff", "item", BELT, byname={"minRange": 0})
    mch.pump(75)
    log("revisited belt; retreating home for good")
    mch.call_bound(bey, "CmdWarpToStuff", "item", RAT_STATION,
                   byname={"minRange": 0})
    mch.pump(70)
    mch.session.pop("stationid", None)
    ensure_docked(mch, RAT_STATION, RAT_SYSTEM, SHIP, patience=200.0)
    mch.close()
    log("SPAWN11 PROBE COMPLETE -- check server logs for "
        "'despawning stale wave' + fresh 'Spawning NPC' on revisit")
    return 0


if __name__ == "__main__":
    sys.exit(main())

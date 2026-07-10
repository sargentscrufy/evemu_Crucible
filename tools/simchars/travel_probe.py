#!/usr/bin/env python3
"""
M2 live probe: Sera (QA pilot, Merlin at Nomaa) undocks, jumps to a
neighboring system, docks at a station there, then comes home.  First
bot stargate jump ever -- every anomaly is a TRAVEL finding.

    python travel_probe.py
"""

import sys
import time

import db
import travel
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

CHAR, SHIP = 90000014, 140001104
HOME_STATION, HOME_SYSTEM = 60004231, 30000131


def main():
    # pick a highsec neighbor with a station
    hops = travel.route(HOME_SYSTEM, 0)  # force load
    neigh = [h[2] for h in travel._GRAPH[HOME_SYSTEM]]
    log(f"neighbors of {HOME_SYSTEM}: {[(n, travel.security(n)) for n in neigh]}")
    target = None
    for n in neigh:
        if travel.security(n) < 0.45:
            continue
        st = db.query(f"SELECT stationID FROM staStations WHERE solarSystemID = {n} LIMIT 1")
        if st:
            target = (n, int(st[0]["stationID"]))
            break
    if not target:
        log("TRAVEL-KINK: no dockable highsec neighbor; aborting")
        return 1
    dest_sys, dest_station = target
    log(f"target: system {dest_sys}, station {dest_station}")

    mch = MachoClient("127.0.0.1", 26000, "qatest", "fleet")
    mch.enter_world(CHAR)
    if not ensure_docked(mch, HOME_STATION, HOME_SYSTEM, SHIP):
        log("TRAVEL-KINK: cannot reach docked start")
        return 1

    sref = mch.bind("ship", (HOME_STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", SHIP, False)
    mch.pump(12)
    if mch.session.get("stationid"):
        log("TRAVEL-KINK: still docked after Undock")
        return 1
    bey = travel.bind_beyonce(mch)
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(10)

    t0 = time.time()
    ok = travel.goto_station(mch, SHIP, dest_station)
    log(f"OUTBOUND {'DOCKED' if ok else 'FAILED'} at {dest_station} in {time.time()-t0:.0f}s")
    if not ok:
        return 1

    # home leg
    sref = mch.bind("ship", (dest_station, STATION_GROUP))
    mch.call_bound(sref, "Undock", SHIP, False)
    mch.pump(12)
    bey = travel.bind_beyonce(mch)
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(10)
    t0 = time.time()
    ok = travel.goto_station(mch, SHIP, HOME_STATION)
    log(f"RETURN {'DOCKED' if ok else 'FAILED'} at {HOME_STATION} in {time.time()-t0:.0f}s")
    mch.close()
    log("TRAVEL PROBE COMPLETE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

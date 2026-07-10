#!/usr/bin/env python3
"""
B4 freighter physics shakedown: Suvi Aalto boards her Charon (960M kg)
at Jita 4-4, undocks, warps to a gate, jumps, comes back, docks.  Every
anomaly (align wedges, warp math, dock behavior at freighter mass) is a
FRT finding.

    python freighter_shakedown.py
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import travel
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, STATION_GROUP

ACCOUNT, PW, CHAR, SHIP = "fleet05", "fleet", 90000008, 140001304
HOME_STATION, HOME_SYSTEM = 60003760, 30000142
NEIGHBOR = 30000144     # Perimeter (1 jump)


def main():
    mch = MachoClient("127.0.0.1", 26000, ACCOUNT, PW)
    mch.enter_world(CHAR)
    if not ensure_docked(mch, HOME_STATION, HOME_SYSTEM, SHIP):
        log("FRT: cannot reach docked start (boarding failed?)")
        return 1
    log("docked in Charon; undocking...")

    sref = mch.bind("ship", (HOME_STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", SHIP, False)
    mch.pump(15)
    if mch.session.get("stationid"):
        log("FRT: still docked after Undock")
        return 1
    bey = travel.bind_beyonce(mch)
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(10)

    t0 = time.time()
    log("gate hop to Perimeter and back...")
    bey2 = travel.goto_system(mch, SHIP, NEIGHBOR, warp_wait=200.0)
    if bey2 is None:
        log("FRT: outbound hop failed")
        return 1
    log(f"in Perimeter after {time.time()-t0:.0f}s; returning")
    t1 = time.time()
    ok = travel.goto_station(mch, SHIP, HOME_STATION)
    log(f"return+dock={'OK' if ok else 'FAILED'} in {time.time()-t1:.0f}s "
        f"(round trip {time.time()-t0:.0f}s)")
    mch.close()
    log("FREIGHTER SHAKEDOWN COMPLETE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

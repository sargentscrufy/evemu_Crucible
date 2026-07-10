#!/usr/bin/env python3
"""
FLEET-1 focused probe: two pilots form a fleet, undock, leader issues one
fleet-warp to a belt.  Diagnosis comes from server logs (FLEET__MESSAGE /
FLEET__WARNING now enabled): FleetWarp lines vs 'not in a fleet' vs
'Only the fleet commander'.

    python fleet_warp_probe.py
"""

import os
import queue
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

STATION, SYSTEM = 60010387, 30002642
BELT = 40168291
PILOTS = [
    ("fleet06", "fleet", 90000006, 140000891, "Mira(FC)"),
    ("fleet04", "fleet", 90000004, 140000843, "Keva"),
    ("fleet05", "fleet", 90000005, 140000866, "Jorn"),
]
fleet_q = {p[2]: queue.Queue() for p in PILOTS[1:]}   # per-member release
barrier = threading.Barrier(len(PILOTS), timeout=420)


def pump_for(mch, s):
    end = time.time() + s
    while time.time() < end:
        mch.pump(2.0)


def pilot(user, pw, char, ship, tag, lead):
    try:
        mch = MachoClient("127.0.0.1", 26000, user, pw)
        mch.enter_world(char)
        if not ensure_docked(mch, STATION, SYSTEM, ship):
            log(f"{tag}: FAIL cannot dock")
            return
        # everyone must be in world before ANY invite goes out: the server
        # silently drops invites to chars that are not logged in yet
        barrier.wait()
        if lead:
            rsp = mch.call("fleetObjectHandler", "CreateFleet")
            import re
            ids = [int(x) for x in re.findall(r"\b(\d{8,})\b", repr(rsp))]
            fleet_id = ids[0]
            fref = mch.bind("fleetObjectHandler", fleet_id)
            pump_for(mch, 3)
            for _, _, mchar, _, mtag in PILOTS[1:]:
                mch.call_bound(fref, "Invite", mchar, None, None, None)
                log(f"{tag}: fleet {fleet_id}, invited {mtag}")
                fleet_q[mchar].put(fleet_id)   # release member only after their invite exists
                pump_for(mch, 3)
            pump_for(mch, 12)   # let accepts land
        else:
            fleet_id = fleet_q[char].get(timeout=120)
            pump_for(mch, 3)
            fref = mch.bind("fleetObjectHandler", fleet_id)
            mch.call_bound(fref, "AcceptInvite", None)
            pump_for(mch, 5)
            log(f"{tag}: joined fleet {fleet_id}")
        log(f"{tag}: session fleetid={mch.session.get('fleetid')} "
            f"fleetrole={mch.session.get('fleetrole')}")
        barrier.wait()

        sref = mch.bind("ship", (STATION, STATION_GROUP))
        mch.call_bound(sref, "Undock", ship, False)
        pump_for(mch, 12)
        bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
        try:
            mch.call_bound(bey, "CmdStop")
        except CallError:
            pass
        pump_for(mch, 20)   # CAP-1 fixed: no long cap wait needed
        barrier.wait()

        if lead:
            log(f"{tag}: FLEET-WARP to belt {BELT} NOW ({time.strftime('%H:%M:%S')})")
            mch.call_bound(bey, "CmdWarpToStuff", "item", BELT,
                           byname={"minRange": 0, "fleet": True})
        pump_for(mch, 60)
        barrier.wait()

        # home
        try:
            mch.call_bound(bey, "CmdWarpToStuff", "item", STATION,
                           byname={"minRange": 0})
        except CallError:
            pass
        pump_for(mch, 75)
        mch.session.pop("stationid", None)
        docked = ensure_docked(mch, STATION, SYSTEM, ship, patience=200.0)
        log(f"{tag}: home docked={docked}")
        mch.close()
    except Exception as e:
        log(f"{tag}: EXCEPTION {type(e).__name__}: {str(e)[:250]}")


def main():
    ts = []
    for i, (u, p, c, s, t) in enumerate(PILOTS):
        th = threading.Thread(target=pilot, args=(u, p, c, s, t, i == 0),
                              daemon=True)
        ts.append(th)
        th.start()
        time.sleep(12)
    for th in ts:
        th.join(timeout=900)
    log("PROBE COMPLETE")


if __name__ == "__main__":
    main()

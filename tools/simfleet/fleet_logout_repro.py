#!/usr/bin/env python3
"""
Crash repro: fleet of two, LEADER logs out without disbanding, remaining
member then docks (session change fires fleet boost updates).  The live
crash happened exactly here (segfault as Mira's dock ItemChange landed).

    python fleet_logout_repro.py
"""

import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import travel
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, STATION_GROUP

LEADER = ("fleet07", "fleet", 90000010, 140001001, "Ilsa(lead)")
MEMBER = ("fleet03", "fleet", 90000006, 140001273, "Mira(member)")
STATION, SYSTEM = 60003760, 30000142


def main():
    # leader in world first
    lm = MachoClient("127.0.0.1", 26000, *LEADER[:2])
    lm.enter_world(LEADER[2])
    assert ensure_docked(lm, STATION, SYSTEM, LEADER[3])

    mm = MachoClient("127.0.0.1", 26000, *MEMBER[:2])
    mm.enter_world(MEMBER[2])
    assert ensure_docked(mm, STATION, SYSTEM, MEMBER[3])

    rsp = lm.call("fleetObjectHandler", "CreateFleet")
    fleet_id = [int(x) for x in re.findall(r"\b(\d{8,})\b", repr(rsp))][0]
    fref = lm.bind("fleetObjectHandler", fleet_id)
    lm.pump(3)
    lm.call_bound(fref, "Invite", MEMBER[2], None, None, None)
    lm.pump(5)
    mref = mm.bind("fleetObjectHandler", fleet_id)
    mm.call_bound(mref, "AcceptInvite", None)
    mm.pump(5)
    log(f"fleet {fleet_id} formed (member session fleetid="
        f"{mm.session.get('fleetid')})")

    # member undocks so a later dock is a real session change
    sref = mm.bind("ship", (STATION, STATION_GROUP))
    mm.call_bound(sref, "Undock", MEMBER[3], False)
    mm.pump(12)
    bey = travel.bind_beyonce(mm)
    try:
        mm.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mm.pump(8)

    log("LEADER LOGGING OUT (no disband)...")
    lm.close()
    time.sleep(8)
    mm.pump(5)

    log("member requesting dock (the crash point)...")
    mm.session.pop("stationid", None)
    ok = ensure_docked(mm, STATION, SYSTEM, MEMBER[3], patience=120.0)
    log(f"member docked={ok} -- SERVER SURVIVED" if ok else
        "member dock failed -- check server state")
    mm.pump(10)
    mm.close()
    log("REPRO COMPLETE")


if __name__ == "__main__":
    main()

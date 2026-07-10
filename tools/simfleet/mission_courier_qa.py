#!/usr/bin/env python3
"""
Courier mission QA: Sera requests a mission from her station agent,
accepts it, hauls the package to the destination with travel.py, and
tries to complete (remotely first, then in person).  Every response is
dumped; every rejection is a MISSION finding.

Dialog buttons (EVE_Agent.h): ViewMission=1 RequestMission=2 Accept=3
Complete=6 CompleteRemotely=7 Decline=9 Quit=11.

    python mission_courier_qa.py [--agent 3016942]
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import cargo
import db
import travel
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, STATION_GROUP

CHAR, SHIP = 90000014, 140001104
HOME_STATION, HOME_SYSTEM = 60004231, 30000131


def show(tag, rsp, cap=900):
    log(f"--- {tag}: {repr(rsp)[:cap]}")


def act(mch, ref, action, tag):
    try:
        rsp = mch.call_bound(ref, "DoAction", action)
        show(f"DoAction({action}) [{tag}]", rsp)
        return rsp
    except CallError as e:
        log(f"MISSION-FINDING: DoAction({action}) [{tag}] failed: {str(e)[:250]}")
        return None


def ints_in(rsp):
    return [int(x) for x in re.findall(r"\b(\d{5,})\b", repr(rsp))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", type=int, default=3016942)
    args = ap.parse_args()

    mch = MachoClient("127.0.0.1", 26000, "qatest", "fleet")
    mch.enter_world(CHAR)
    if not ensure_docked(mch, HOME_STATION, HOME_SYSTEM, SHIP):
        log("MISSION-FINDING: no docked start")
        return 1

    ref = mch.bind("agentMgr", args.agent)
    act(mch, ref, None, "open")
    act(mch, ref, 2, "request-mission")

    try:
        brief = mch.call_bound(ref, "GetMissionBriefingInfo")
        show("GetMissionBriefingInfo", brief, 1400)
    except CallError as e:
        log(f"MISSION-FINDING: briefing failed: {str(e)[:250]}")

    act(mch, ref, 3, "accept")

    try:
        obj = mch.call_bound(ref, "GetMissionObjectiveInfo")
        show("GetMissionObjectiveInfo", obj, 1600)
    except CallError as e:
        log(f"MISSION-FINDING: objectives failed: {str(e)[:250]}")
        obj = None

    # find dropoff station + cargo from objectives / journal / hangar diff
    dropoff = None
    if obj is not None:
        # objective dicts carry destinationID / stationID style keys
        m = re.search(r"'(?:destination|station)ID', (\d{8})", repr(obj))
        if m:
            dropoff = int(m.group(1))
        else:
            cands = [i for i in ints_in(obj) if 60000000 <= i < 64000000]
            dropoff = cands[0] if cands else None
    log(f"dropoff station: {dropoff}")

    # mission cargo: newest items in home hangar (courier package)
    pkg = db.query(
        f"SELECT itemID, typeID, quantity FROM entity WHERE ownerID = {CHAR}"
        f" AND locationID = {HOME_STATION} AND flag = 4"
        f" ORDER BY itemID DESC LIMIT 3")
    log(f"hangar newest: {pkg}")

    if dropoff is None:
        log("MISSION-FINDING: no destination resolved from objectives; "
            "stopping after protocol walk")
        mch.close()
        return 1

    inv = cargo.station_invbroker(mch, HOME_STATION)
    moved = 0
    for row in pkg:
        moved += cargo.load_cargo(mch, inv, CHAR, HOME_STATION, SHIP,
                                  int(row["typeID"]), int(row["quantity"]))
    log(f"loaded {moved} package units; departing")

    sref = mch.bind("ship", (HOME_STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", SHIP, False)
    mch.pump(12)
    bey = travel.bind_beyonce(mch)
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(8)

    if not travel.goto_station(mch, SHIP, dropoff):
        log("MISSION-FINDING: travel to dropoff failed")
        mch.close()
        return 1
    log("at dropoff; unloading package")
    inv = cargo.station_invbroker(mch, dropoff)
    cargo.unload_cargo(mch, inv, CHAR, dropoff, SHIP)

    # complete: remotely from here, else in person back home
    ref2 = mch.bind("agentMgr", args.agent)
    rsp = act(mch, ref2, 7, "complete-remotely")
    if rsp is None:
        log("returning to agent for in-person completion")
        sref = mch.bind("ship", (dropoff, STATION_GROUP))
        mch.call_bound(sref, "Undock", SHIP, False)
        mch.pump(12)
        bey = travel.bind_beyonce(mch)
        try:
            mch.call_bound(bey, "CmdStop")
        except CallError:
            pass
        mch.pump(8)
        travel.goto_station(mch, SHIP, HOME_STATION)
        ref3 = mch.bind("agentMgr", args.agent)
        act(mch, ref3, 6, "complete-in-person")

    try:
        journal = mch.call_bound(ref2, "GetMyJournalDetails")
        show("GetMyJournalDetails", journal, 1000)
    except CallError as e:
        log(f"MISSION-FINDING: journal failed: {str(e)[:200]}")

    bal = db.query(f"SELECT balance FROM chrCharacters WHERE characterID = {CHAR}")
    log(f"wallet after: {bal}")
    mch.close()
    log("COURIER QA COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())

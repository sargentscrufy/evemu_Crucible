#!/usr/bin/env python3
"""
Security-mission QA probe (M1/M2): request work, accept, dump briefing
and journal bookmarks.  Verifies string briefings + site bookmarks after accept.

    python mission_qa.py [--agent 3016942] [--accept]
"""

import argparse
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

from machoclient import MachoClient, CallError, log

CHAR = 90000014


def show(label, rsp, cap=1200):
    log(f"--- {label}:")
    log(repr(rsp)[:cap])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", type=int, default=3016942)
    ap.add_argument("--accept", action="store_true", help="accept the offered mission")
    ap.add_argument("--port", type=int, default=26010, help="server port (26010=direct, 26000=proxy)")
    args = ap.parse_args()

    mch = MachoClient("127.0.0.1", args.port, "qatest", "fleet")
    sess = mch.enter_world(CHAR)
    log(f"in world: station={sess.get('stationid')}")

    agent_ref = mch.bind("agentMgr", args.agent)
    log(f"bound agent {args.agent}")

    try:
        rsp = mch.call_bound(agent_ref, "DoAction", None)
        show("DoAction(None)", rsp, 1500)
        txt = repr(rsp)
        actions = sorted(set(int(a) for a in re.findall(r"\((\d+), '", txt)))
        log(f"dialogue action ids: {actions}")
    except CallError as e:
        log(f"FINDING: DoAction(None) failed: {e}")
        mch.close()
        return 1

    # RequestMission is usually action 2
    try:
        rsp = mch.call_bound(agent_ref, "DoAction", 2)
        show("DoAction(RequestMission=2)", rsp, 2000)
        rtxt = repr(rsp)
        if "Retrieve the Reports" in rtxt or "Pirate Ambush" in rtxt or "Guristas" in rtxt:
            log("PASS: string title or briefing prose present in RequestMission response")
        if "130400" in rtxt and "Guristas" not in rtxt:
            log("NOTE: still seeing retail briefingID 130400 (string briefing may be elsewhere)")
    except CallError as e:
        log(f"FINDING: DoAction(2) failed: {e}")

    try:
        rsp = mch.call_bound(agent_ref, "GetMissionBriefingInfo")
        show("GetMissionBriefingInfo", rsp, 2000)
        rtxt = repr(rsp)
        if "Guristas" in rtxt or "freighter" in rtxt or "Combat Site" in rtxt:
            log("PASS: custom briefing string in GetMissionBriefingInfo")
        else:
            log("CHECK: custom briefing string not obvious in briefing info dump")
    except CallError as e:
        log(f"FINDING: GetMissionBriefingInfo failed: {e}")

    if args.accept:
        try:
            rsp = mch.call_bound(agent_ref, "DoAction", 3)  # Accept
            show("DoAction(Accept=3)", rsp, 1500)
            time.sleep(1)
        except CallError as e:
            log(f"FINDING: Accept failed: {e}")

        try:
            # journal via agent moniker
            rsp = mch.call_bound(agent_ref, "GetMyJournalDetails")
            show("GetMyJournalDetails (agent)", rsp, 2500)
            rtxt = repr(rsp)
            if "objective.source" in rtxt or "Combat Site" in rtxt:
                log("PASS: encounter bookmarks present after accept")
            else:
                log("FINDING: no objective.source / Combat Site bookmark after accept")
            if "util.KeyVal" in rtxt or "KeyVal" in rtxt:
                log("PASS: KeyVal bookmark objects in journal list")
        except CallError as e:
            log(f"FINDING: GetMyJournalDetails failed: {e}")

        try:
            rsp = mch.call_bound(agent_ref, "GetMissionJournalInfo", CHAR, CHAR)
            show("GetMissionJournalInfo", rsp, 2000)
            rtxt = repr(rsp)
            if "Guristas" in rtxt or "freighter" in rtxt:
                log("PASS: string briefing in journal info")
        except CallError as e:
            log(f"FINDING: GetMissionJournalInfo failed: {e}")

    mch.close()
    log("probe complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())

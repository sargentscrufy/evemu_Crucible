#!/usr/bin/env python3
"""
Security-mission QA probe: log in the QA pilot, bind the station's L1
security agent, walk the agent conversation (DoAction tree), request
work, and dump everything the server returns.  Baseline for the
encounter-mission build; every rejection/exception is a finding.

    python mission_qa.py [--agent 3016942]
"""

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
from machoclient import MachoClient, CallError, log

CHAR = 90000014
STATION = 60004231
SYSTEM = 30000131


def show(label, rsp, cap=700):
    log(f"--- {label}:")
    log(repr(rsp)[:cap])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", type=int, default=3016942)
    args = ap.parse_args()

    mch = MachoClient("127.0.0.1", 26000, "qatest", "fleet")
    sess = mch.enter_world(CHAR)
    log(f"in world: station={sess.get('stationid')}")

    agent_ref = mch.bind("agentMgr", args.agent)
    log(f"bound agent {args.agent}")

    try:
        rsp = mch.call_bound(agent_ref, "GetInfoServiceDetails")
        show("GetInfoServiceDetails", rsp)
    except CallError as e:
        log(f"FINDING: GetInfoServiceDetails failed: {e}")

    # first DoAction with no args opens the conversation
    try:
        rsp = mch.call_bound(agent_ref, "DoAction", None)
        show("DoAction(None)", rsp, 1500)
        # response carries (agentSays, dialogue options); walk every
        # option once, dumping what each returns
        # dialogue format: (info, [(actionID, text, ...), ...]) roughly
        import re
        txt = repr(rsp)
        actions = sorted(set(int(a) for a in re.findall(r"\((\d+), '", txt)))
        log(f"dialogue action ids: {actions}")
        for act in actions[:6]:
            try:
                r2 = mch.call_bound(agent_ref, "DoAction", act)
                show(f"DoAction({act})", r2, 1200)
                time.sleep(1)
            except CallError as e:
                log(f"FINDING: DoAction({act}) failed: {e}")
    except CallError as e:
        log(f"FINDING: DoAction(None) failed: {e}")

    try:
        rsp = mch.call_bound(agent_ref, "GetMissionBriefingInfo")
        show("GetMissionBriefingInfo", rsp, 1200)
    except CallError as e:
        log(f"FINDING: GetMissionBriefingInfo failed: {e}")

    mch.close()
    log("probe complete")


if __name__ == "__main__":
    sys.exit(main())

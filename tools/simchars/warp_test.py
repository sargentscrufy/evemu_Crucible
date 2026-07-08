#!/usr/bin/env python3
"""
Warp regression test (DESTINY-3 rework): undock -> warp to a celestial
-> warp back to the station -> dock.

The final dock is the assertion: docking only succeeds if the return
warp landed inside the station's docking perimeter, which is precisely
the failure mode of the old warp math (fly-through / bounce).

    python warp_test.py --user aura --password aura --char-id 90000002 \
        [--station 60004450] [--celestial 40088642] [--port 26000]

Exit 0 = round trip completed and docked. Exit 1 = any stage failed.
"""

import argparse
import sys
import time

import db
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP


def warp_to(mch, bey_ref, target_id, min_range=0):
    mch.call_bound(bey_ref, "CmdWarpToStuff", "item", int(target_id),
                   byname={"minRange": int(min_range)})


def wait_out_warp(mch, seconds):
    """Pump for the expected warp duration, keeping the session alive."""
    log(f"waiting out warp (~{seconds:.0f}s)")
    deadline = time.time() + seconds
    while time.time() < deadline:
        mch.pump(2.0)


def main():
    ap = argparse.ArgumentParser(description="simchar warp regression test")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=26000)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--char-id", type=int, required=True)
    ap.add_argument("--station", type=int, default=60004450)
    ap.add_argument("--celestial", type=int, default=40088642,
                    help="warp target itemID (default: Amsen IV)")
    ap.add_argument("--warp-wait", type=float, default=75.0,
                    help="seconds to allow per warp leg")
    args = ap.parse_args()

    mch = MachoClient(args.host, args.port, args.user, args.password)
    sess = mch.enter_world(args.char_id)
    system_id = sess["solarsystemid2"]
    ship_item = int(mch.session.get("shipid") or 0)
    log(f"in world: station={sess['stationid']} system={system_id} "
        f"ship={ship_item}")

    if not ensure_docked(mch, args.station, system_id, ship_item):
        log("FAIL: could not reach docked starting state")
        return 1

    ship_ref = mch.bind("ship", (args.station, STATION_GROUP))
    log("undocking")
    mch.call_bound(ship_ref, "Undock", ship_item, False)
    mch.pump(12.0)
    if mch.session.get("stationid"):
        log("FAIL: still docked after Undock")
        return 1
    log("in space")

    bey_ref = mch.bind("beyonce", (system_id, SOLARSYSTEM_GROUP))
    try:
        mch.call_bound(bey_ref, "CmdStop")
        mch.pump(2.0)
    except CallError as e:
        log(f"CmdStop: {e}")

    log(f"warp leg 1: -> celestial {args.celestial}")
    try:
        warp_to(mch, bey_ref, args.celestial, min_range=100000)
    except CallError as e:
        log(f"FAIL: warp 1 rejected: {e}")
        return 1
    wait_out_warp(mch, args.warp_wait)

    log(f"warp leg 2: -> station {args.station}")
    try:
        mch.call_bound(bey_ref, "CmdStop")
        mch.pump(2.0)
        warp_to(mch, bey_ref, args.station, min_range=0)
    except CallError as e:
        log(f"FAIL: warp 2 rejected: {e}")
        return 1
    wait_out_warp(mch, args.warp_wait)

    log("docking (the assertion: only succeeds if warp landed on grid)")
    mch.session.pop("stationid", None)
    if ensure_docked(mch, args.station, system_id, ship_item,
                     patience=120.0):
        log("PASS: undock -> warp out -> warp back -> dock round trip")
        mch.close()
        return 0
    log("FAIL: could not dock after return warp (landed off-grid?)")
    mch.close()
    return 1


if __name__ == "__main__":
    sys.exit(main())

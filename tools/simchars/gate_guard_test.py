#!/usr/bin/env python3
"""
GUARD-1 validation: fly a sim character to a high-security stargate and
loiter so the gate bubble's guard spawn timer (10-30s) fires.

The assertion is made from server logs after the run:
    docker logs server | grep DoGuardSpawn
should show police NPCs spawned for the gate, followed by idle orbit
movement from their AI.

    python gate_guard_test.py --user aura --password aura \
        --char-id 90000002 [--station 60004450] [--gate 50001721]
"""

import argparse
import sys
import time

import db
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP


def main():
    ap = argparse.ArgumentParser(description="GUARD-1 gate guard test")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=26000)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--char-id", type=int, required=True)
    ap.add_argument("--station", type=int, default=60004450)
    ap.add_argument("--gate", type=int, default=50001721,
                    help="stargate itemID (default: Amsen -> Ekura)")
    ap.add_argument("--loiter", type=float, default=90.0,
                    help="seconds to sit at the gate")
    args = ap.parse_args()

    mch = MachoClient(args.host, args.port, args.user, args.password)
    sess = mch.enter_world(args.char_id)
    system_id = sess["solarsystemid2"]
    ship_item = int(mch.session.get("shipid") or 0)
    if not ship_item:
        ship_item = int(db.query(
            "SELECT shipID FROM chrCharacters WHERE characterID = "
            f"{int(args.char_id)}")[0]["shipID"])
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

    bey_ref = mch.bind("beyonce", (system_id, SOLARSYSTEM_GROUP))
    try:
        mch.call_bound(bey_ref, "CmdStop")
        mch.pump(2.0)
    except CallError as e:
        log(f"CmdStop: {e}")

    log(f"warping to gate {args.gate}")
    try:
        mch.call_bound(bey_ref, "CmdWarpToStuff", "item", int(args.gate),
                       byname={"minRange": 0})
    except CallError as e:
        log(f"FAIL: warp rejected: {e}")
        return 1

    # ride out the warp, then loiter on the gate grid so the guard
    # spawn timer fires with a player present in the bubble
    log(f"loitering at gate for warp + {args.loiter:.0f}s")
    deadline = time.time() + 120.0 + args.loiter
    while time.time() < deadline:
        mch.pump(2.0)

    log("returning to station")
    try:
        mch.call_bound(bey_ref, "CmdWarpToStuff", "item", int(args.station),
                       byname={"minRange": 0})
    except CallError as e:
        log(f"warp home rejected: {e}")
    deadline = time.time() + 120.0
    while time.time() < deadline:
        mch.pump(2.0)

    mch.session.pop("stationid", None)
    if ensure_docked(mch, args.station, system_id, ship_item,
                     patience=180.0):
        log("PASS: gate visit round trip complete (check server logs "
            "for DoGuardSpawn)")
        mch.close()
        return 0
    log("WARN: could not re-dock; guard spawn may still have triggered "
        "(check server logs)")
    mch.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

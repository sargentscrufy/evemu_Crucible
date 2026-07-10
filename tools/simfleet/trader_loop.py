#!/usr/bin/env python3
"""
M4 continuous trader: one pilot runs arbitrage legs forever (or --legs N).
Each cycle: coordinator scan (DB) -> protocol buy/haul/sell -> verify ->
CSV metrics row.  Personality knobs keep multiple traders from piling
onto the same route.

    python trader_loop.py --pilot ilsa [--legs 3]
"""

import argparse
import csv
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import cargo
import db
import trade
from machoclient import MachoClient, CallError, log
from provision import ensure_docked

PILOTS = {
    # name: (account, pw, charID, shipID, home_station, home_system, knobs)
    "ilsa": ("fleet07", "fleet", 90000010, 140001001, 60003760, 30000142,
             dict(min_margin=0.05, max_jumps=8)),
    "rho":  ("fleet08", "fleet", 90000011, 140001022, 60003760, 30000142,
             dict(min_margin=0.07, max_jumps=5)),
    "piret": ("fleet09", "fleet", 90000012, 140001044, 60003760, 30000142,
              dict(min_margin=0.04, max_jumps=10)),
    "enna": ("fleet10", "fleet", 90000013, 140001066, 60003760, 30000142,
             dict(min_margin=0.06, max_jumps=6)),
}
METRICS = os.path.join(HERE, "trader_metrics.csv")


def write_metric(row):
    new = not os.path.exists(METRICS)
    with open(METRICS, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "pilot", "leg", "typeID", "qty", "jumps",
                        "expected", "realized", "seconds", "result"])
        w.writerow(row)


def station_of(mch, char_id):
    st = mch.session.get("stationid")
    if st:
        return int(st)
    r = db.query(f"SELECT stationID FROM chrCharacters WHERE characterID = {char_id}")
    return int(r[0]["stationID"]) if r and int(r[0]["stationID"] or 0) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", required=True, choices=sorted(PILOTS))
    ap.add_argument("--legs", type=int, default=0, help="0 = forever")
    args = ap.parse_args()
    account, pw, char, ship, home_st, home_sys, knobs = PILOTS[args.pilot]

    mch = MachoClient("127.0.0.1", 26000, account, pw)
    mch.enter_world(char)
    if not ensure_docked(mch, home_st, home_sys, ship):
        log(f"{args.pilot}: cannot reach docked start; abort")
        return 1

    cap = cargo.cargo_capacity(ship)
    leg_n = 0
    fails = 0
    while (args.legs == 0) or (leg_n < args.legs):
        leg_n += 1
        t0 = time.time()
        here = station_of(mch, char) or home_st
        budget = (trade.db_wallet(char) or 0) * 0.8
        plan = trade.find_best_route_db(char, here, cargo_m3=cap,
                                        budget=budget, **knobs)
        if plan is None:
            write_metric([int(time.time()), args.pilot, leg_n, "", "", "",
                          "", "", 0, "no-route"])
            if here != home_st:
                # dead market pocket: reposition to the home hub and rescan
                log(f"{args.pilot}: leg {leg_n}: no route from {here}; "
                    "returning home")
                import travel
                from provision import STATION_GROUP
                sref = mch.bind("ship", (here, STATION_GROUP))
                mch.call_bound(sref, "Undock", ship, False)
                mch.pump(12)
                bey = travel.bind_beyonce(mch)
                try:
                    mch.call_bound(bey, "CmdStop")
                except CallError:
                    pass
                mch.pump(8)
                travel.goto_station(mch, ship, home_st)
            else:
                log(f"{args.pilot}: leg {leg_n}: no route from home; "
                    "cooling down 120s")
                mch.pump(120)
            continue
        log(f"{args.pilot}: leg {leg_n}: {plan!r}")
        try:
            delta = trade.execute_leg(mch, char, ship, plan)
        except CallError as e:
            log(f"{args.pilot}: leg {leg_n} CallError: {str(e)[:200]}")
            delta = None
        secs = time.time() - t0
        ok = delta is not None
        fails = 0 if ok else fails + 1
        write_metric([int(time.time()), args.pilot, leg_n, plan.type_id,
                      plan.qty, plan.jumps, f"{plan.expected_profit:.0f}",
                      "" if delta is None else f"{delta:.0f}",
                      f"{secs:.0f}", "ok" if ok else "fail"])
        if fails >= 3:
            log(f"{args.pilot}: 3 consecutive failures; stopping for triage")
            break
        # settle + jitter so multiple traders desynchronize
        mch.pump(10 + random.randint(0, 20))
    mch.close()
    log(f"{args.pilot}: trader loop done ({leg_n} legs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
M3/M4 probe: Ilsa Vayne (Badger, Jita 4-4) runs ONE full arbitrage leg:
coordinator scan (DB) -> protocol buy -> load cargo -> haul (gates as
needed) -> unload -> sell -> wallet + item conservation verification.

    python trader_leg_probe.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import cargo
import db
import trade
from machoclient import MachoClient, CallError, log
from provision import ensure_docked

ACCOUNT, PW = "fleet07", "fleet"
CHAR, SHIP = 90000010, 140001001
HOME_STATION, HOME_SYSTEM = 60003760, 30000142   # Jita 4-4


def main():
    cap = cargo.cargo_capacity(SHIP)
    bal = trade.db_wallet(CHAR)
    log(f"Ilsa: Badger cargo {cap} m3, wallet {bal:,.0f} ISK")

    plan = trade.find_best_route_db(
        CHAR, HOME_STATION, cargo_m3=cap, budget=bal * 0.8,
        min_margin=0.05, max_jumps=8)
    if plan is None:
        log("TRADE-KINK: no profitable route found from Jita 4-4")
        return 1
    log(f"PLAN: {plan!r}")

    mch = MachoClient("127.0.0.1", 26000, ACCOUNT, PW)
    mch.enter_world(CHAR)
    if not ensure_docked(mch, HOME_STATION, HOME_SYSTEM, SHIP):
        log("TRADE-KINK: cannot reach docked start at Jita 4-4")
        return 1

    delta = trade.execute_leg(mch, CHAR, SHIP, plan)
    if delta is None:
        log("LEG FAILED -- see kinks above")
        mch.close()
        return 1
    log(f"LEG COMPLETE: realized {delta:,.0f} ISK "
        f"(expected {plan.expected_profit:,.0f})")
    mch.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

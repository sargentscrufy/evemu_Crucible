#!/usr/bin/env python3
"""
One-off: finish Ilsa's interrupted trade leg -- she is docked at the
destination with the purchased cargo aboard.  Unload, sell to the
standing buy order, verify wallet delta.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import cargo
import db
import trade
from machoclient import MachoClient, log
from provision import ensure_docked

ACCOUNT, PW = "fleet07", "fleet"
CHAR, SHIP = 90000010, 140001001
STATION = 60001663
SYSTEM = 30001374


def main():
    stacks = cargo.cargo_stacks(SHIP)
    log(f"cargo aboard: {stacks}")
    if not stacks:
        log("nothing to sell")
        return 1
    w0 = trade.db_wallet(CHAR)

    mch = MachoClient("127.0.0.1", 26000, ACCOUNT, PW)
    mch.enter_world(CHAR)
    if not ensure_docked(mch, STATION, SYSTEM, SHIP):
        log("cannot dock at destination")
        return 1
    inv = cargo.station_invbroker(mch, STATION)
    for item_id, tid, qty in stacks:
        moved = cargo.unload_cargo(mch, inv, CHAR, STATION, SHIP, tid)
        log(f"unloaded {moved} of type {tid}")
        bids = db.query(
            f"SELECT price FROM mktOrders WHERE bid=1 AND typeID={tid}"
            f" AND stationID={STATION} AND volRemaining>0"
            f" ORDER BY price DESC LIMIT 1")
        if not bids:
            log(f"TRADE-KINK: no buy order for {tid} here anymore")
            continue
        price = float(bids[0]["price"])
        import market
        for stack_id, stack_qty in cargo.hangar_stacks(CHAR, STATION, tid):
            market.sell_immediate(mch, STATION, tid, price, stack_qty,
                                  stack_id)
            mch.pump(2)
            log(f"sold {stack_qty} x {tid} at {price} (stack {stack_id})")
    w1 = trade.db_wallet(CHAR)
    log(f"wallet {w0:,.0f} -> {w1:,.0f} (delta {w1-w0:,.0f})")
    mch.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

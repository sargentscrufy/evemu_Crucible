#!/usr/bin/env python3
"""
M1 live probe: exercise every market.py entry point against the dev
server with the docked QA pilot and dump decoded results.  Any exception
or empty decode is an MKT finding.

    python market_probe.py
"""

import sys

import db
import market
from machoclient import MachoClient, CallError, log

CHAR = 90000014          # Sera Auvinen (qatest/fleet), docked at Nomaa
TRITANIUM = 34


def main():
    mch = MachoClient("127.0.0.1", 26000, "qatest", "fleet")
    sess = mch.enter_world(CHAR)
    log(f"in world: station={sess.get('stationid')} region={mch.session.get('regionid')}")

    log("--- wallet")
    try:
        bal = market.wallet_balance(mch)
        log(f"balance: {bal!r}")
    except CallError as e:
        log(f"MKT-FINDING: GetCashBalance failed: {str(e)[:200]}")

    log("--- GetRegionBest")
    try:
        best = market.get_region_best(mch)
        if isinstance(best, list):
            log(f"{len(best)} rows; sample: {best[:3]!r}")
        else:
            log(f"undecoded: {repr(best)[:400]}")
    except CallError as e:
        log(f"MKT-FINDING: GetRegionBest failed: {str(e)[:200]}")

    log("--- GetOrders(Tritanium)")
    try:
        sells, buys = market.get_orders(mch, TRITANIUM)
        log(f"{len(sells)} sells / {len(buys)} buys")
        for r in sells[:3]:
            log(f"  SELL {r!r}")
        for r in buys[:3]:
            log(f"  BUY  {r!r}")
        if not sells and not buys:
            raw = mch.call("marketProxy", "GetOrders", TRITANIUM)
            log(f"MKT-FINDING: decode produced nothing.  raw: {repr(raw)[:600]}")
    except CallError as e:
        log(f"MKT-FINDING: GetOrders failed: {str(e)[:200]}")

    log("--- GetStationAsks")
    try:
        rsp = market.get_station_asks(mch)
        rows = market.all_rows(rsp)
        log(f"{len(rows)} decoded rows; raw head: {repr(rsp)[:250]}")
    except CallError as e:
        log(f"MKT-FINDING: GetStationAsks failed: {str(e)[:200]}")

    log("--- GetCharOrders")
    try:
        rows = market.get_char_orders(mch)
        log(f"char orders: {rows if isinstance(rows, list) else repr(rows)[:250]}")
    except CallError as e:
        log(f"MKT-FINDING: GetCharOrders failed: {str(e)[:200]}")

    # cross-check one decoded price against the DB
    log("--- DB cross-check (Tritanium sells in region)")
    rows = db.query(
        "SELECT price, volRemaining, stationID FROM mktOrders"
        " WHERE typeID = 34 AND bid = 0 ORDER BY price LIMIT 3")
    for r in rows:
        log(f"  DB SELL {r}")

    mch.close()
    log("probe complete")


if __name__ == "__main__":
    sys.exit(main())

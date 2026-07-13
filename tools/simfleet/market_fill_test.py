#!/usr/bin/env python3
"""
MKT-4 / MKT-5 validation: range-aware, partial-fill market matching.

Production feedback 2026-07-12 (SARGENTSCRUFY): selling into a visible buy
order failed ("No sell order found"), and quick-sells put out a sell order
instead of matching.  Root causes fixed:
  - FindBuyOrder/FindSellOrder required exact same-station orders and
    volRemaining >= the full quantity (no partial fills, no range).
  - ExecuteBuyOrder ignored the requested quantity (moved whole stacks)
    and paid the asked price instead of the order's price.
  - Standing orders never crossed the book.

Tests (pilot Keva docked Jita 4-4, injected NPC-corp orders at another
Jita station with solar-system range):
  T1  immediate sell fills a system-range buy order at another station
  T2  immediate sell walks multiple orders best-price-first, pays ORDER
      prices, leaves the unfillable remainder in the hangar
  T3  standing sell crosses an overlapping buy order, lists remainder only
  T4  immediate sell with no match: clean error, nothing changes
  T5  immediate buy fills a sell order at another station in-system;
      delivery lands at the ORDER's station

    python market_fill_test.py
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
from machoclient import MachoClient, CallError, log

PORT = int(os.environ.get("EVE_PORT", "26010"))
PILOT = ("fleet01", "fleet", 90000004, "Keva")
JITA_44 = 60003760
JITA_SYS = 30000142
FORGE = 10000002
TRIT = 34
NPC_CORP = 1000125          # MKT-2-certified NPC-corp order owner
FLAG_HANGAR = 4
MARKER_ESCROW = 424242      # tags injected orders for cleanup


def filetime_now():
    return int((time.time() + 11644473600) * 10_000_000)


def other_jita_station():
    rows = db.query(f"SELECT stationID FROM staStations WHERE "
                    f"solarSystemID={JITA_SYS} AND stationID!={JITA_44} LIMIT 1")
    return int(rows[0]["stationID"])


def inject_order(station, bid, price, qty, order_range=0, min_vol=1):
    rows = db.query(
        "INSERT INTO mktOrders (typeID, ownerID, regionID, stationID, "
        "solarSystemID, orderRange, bid, price, escrow, minVolume, "
        "volEntered, volRemaining, issued, duration, jumps, isCorp, "
        "accountKey, memberID) VALUES "
        f"({TRIT}, {NPC_CORP}, {FORGE}, {station}, {JITA_SYS}, "
        f"{order_range}, {bid}, {price}, {MARKER_ESCROW}, {min_vol}, "
        f"{qty}, {qty}, {filetime_now()}, 90, 1, 0, 1000, 0); "
        "SELECT LAST_INSERT_ID() AS id")
    return int(rows[0]["id"])


def order_row(order_id):
    rows = db.query(f"SELECT volRemaining, price FROM mktOrders "
                    f"WHERE orderID={order_id}")
    return rows[0] if rows else None


def cleanup_orders():
    db.execute(f"DELETE FROM mktOrders WHERE escrow={MARKER_ESCROW}")


def wallet(char_id):
    return float(db.query(f"SELECT balance FROM chrCharacters "
                          f"WHERE characterID={char_id}")[0]["balance"])


def hangar_qty(char_id, station, item_id):
    rows = db.query(f"SELECT quantity FROM entity WHERE itemID={item_id} "
                    f"AND ownerID={char_id} AND locationID={station}")
    return int(rows[0]["quantity"]) if rows else 0


def stage_trit(char_id, qty):
    rows = db.query(
        "INSERT INTO entity (itemName, typeID, ownerID, locationID, flag, "
        "contraband, singleton, quantity, x, y, z, customInfo) VALUES "
        f"('Tritanium', {TRIT}, {char_id}, {JITA_44}, {FLAG_HANGAR}, 0, 0, "
        f"{qty}, 0, 0, 0, ''); SELECT LAST_INSERT_ID() AS id")
    return int(rows[0]["id"])


def char_sell_orders(char_id):
    return db.query(f"SELECT orderID, price, volEntered, volRemaining FROM "
                    f"mktOrders WHERE ownerID={char_id} AND bid=0")


def sell_immediate(mch, station, price, qty, item_id):
    return mch.call("marketProxy", "PlaceCharOrder",
                    int(station), TRIT, float(price), int(qty),
                    0, 32767, int(item_id), 1, 0, False, None)


def place_sell_order(mch, station, price, qty, item_id, duration=14):
    return mch.call("marketProxy", "PlaceCharOrder",
                    int(station), TRIT, float(price), int(qty),
                    0, 32767, int(item_id), 1, int(duration), False, None)


def buy_immediate(mch, station, price, qty, order_range=0):
    return mch.call("marketProxy", "PlaceCharOrder",
                    int(station), TRIT, float(price), int(qty),
                    1, int(order_range), None, 1, 0, False, None)


RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    log(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")


def run():
    acct, pw, char, tag = PILOT
    online = db.query(f"SELECT online FROM chrCharacters "
                      f"WHERE characterID={char}")[0]["online"]
    if online not in ("0", "", 0):
        raise SystemExit(f"{tag} ({char}) is online; cannot stage")

    other = other_jita_station()
    log(f"=== MKT-4/5 fill tests: {tag} @ Jita 4-4, orders @ {other} ===")

    cleanup_orders()
    db.execute(f"DELETE FROM mktOrders WHERE ownerID={char}")
    item = stage_trit(char, 5000)
    log(f"staged 5000 trit itemID {item}")

    mch = MachoClient("127.0.0.1", PORT, acct, pw)
    mch.enter_world(char)
    mch.pump(3)

    # ---- T1: fill a system-range buy order at another station ----------
    o1 = inject_order(other, bid=1, price=5.00, qty=1000)
    w0, h0 = wallet(char), hangar_qty(char, JITA_44, item)
    sell_immediate(mch, JITA_44, 5.00, 300, item)
    mch.pump(2)
    row = order_row(o1)
    w1, h1 = wallet(char), hangar_qty(char, JITA_44, item)
    check("T1 hangar -300", h0 - h1 == 300, f"({h0}->{h1})")
    check("T1 order volRemaining 700", row and int(row["volRemaining"]) == 700,
          f"({row})")
    check("T1 wallet +~1500 (net tax)", 1350 <= w1 - w0 <= 1500,
          f"(+{w1 - w0:.2f})")

    # ---- T2: multi-order walk, best price first, partial remainder -----
    cleanup_orders()
    o2a = inject_order(other, bid=1, price=6.00, qty=100)
    o2b = inject_order(other, bid=1, price=5.50, qty=150)
    w0, h0 = wallet(char), hangar_qty(char, JITA_44, item)
    sell_immediate(mch, JITA_44, 5.25, 300, item)
    mch.pump(2)
    w1, h1 = wallet(char), hangar_qty(char, JITA_44, item)
    gone_a, gone_b = order_row(o2a) is None, order_row(o2b) is None
    check("T2 hangar -250 (partial)", h0 - h1 == 250, f"({h0}->{h1})")
    check("T2 both orders consumed", gone_a and gone_b, f"({gone_a},{gone_b})")
    # order prices, not the 5.25 ask: 100*6.00 + 150*5.50 = 1425 gross
    check("T2 paid ORDER prices (~1425 net tax)", 1280 <= w1 - w0 <= 1425,
          f"(+{w1 - w0:.2f})")

    # ---- T3: standing sell crosses the book, lists remainder -----------
    cleanup_orders()
    o3 = inject_order(other, bid=1, price=4.00, qty=200)
    w0, h0 = wallet(char), hangar_qty(char, JITA_44, item)
    place_sell_order(mch, JITA_44, 3.50, 500, item, duration=14)
    mch.pump(2)
    w1, h1 = wallet(char), hangar_qty(char, JITA_44, item)
    mine = char_sell_orders(char)
    listed = mine and int(mine[0]["volEntered"]) == 300
    check("T3 hangar -500 (200 crossed + 300 listed)", h0 - h1 == 500,
          f"({h0}->{h1})")
    check("T3 buy order consumed", order_row(o3) is None)
    check("T3 sell order listed for remainder 300", listed, f"({mine})")
    check("T3 crossed fill paid in (~800 minus tax+fee)", 600 <= w1 - w0 <= 800,
          f"(+{w1 - w0:.2f})")

    # ---- T4: no match -> clean error, nothing changes -------------------
    cleanup_orders()
    w0, h0 = wallet(char), hangar_qty(char, JITA_44, item)
    try:
        sell_immediate(mch, JITA_44, 99999.0, 100, item)
    except CallError as e:
        log(f"  (T4 call error, acceptable: {str(e)[:60]})")
    mch.pump(2)
    w1, h1 = wallet(char), hangar_qty(char, JITA_44, item)
    check("T4 hangar unchanged", h0 == h1, f"({h0}->{h1})")
    check("T4 wallet unchanged", abs(w1 - w0) < 0.01, f"({w1 - w0:+.2f})")

    # ---- T5: immediate buy from another station in-system ---------------
    o5 = inject_order(other, bid=0, price=2.00, qty=100)
    w0 = wallet(char)
    buy_immediate(mch, JITA_44, 2.50, 50, order_range=0)
    mch.pump(2)
    w1 = wallet(char)
    row = order_row(o5)
    delivered = db.query(
        f"SELECT quantity FROM entity WHERE ownerID={char} AND "
        f"locationID={other} AND typeID={TRIT}")
    check("T5 paid ORDER price 2.00 (-100)", abs((w0 - w1) - 100.0) < 0.01,
          f"({w1 - w0:+.2f})")
    check("T5 sell order volRemaining 50", row and int(row["volRemaining"]) == 50,
          f"({row})")
    check("T5 delivery at ORDER's station", delivered and
          int(delivered[0]["quantity"]) == 50, f"({delivered})")

    mch.close()
    cleanup_orders()
    db.execute(f"DELETE FROM mktOrders WHERE ownerID={char}")

    passed = sum(1 for _, ok in RESULTS if ok)
    log(f"=== {passed}/{len(RESULTS)} checks passed ===")
    return passed == len(RESULTS)


if __name__ == "__main__":
    sys.exit(0 if run() else 1)

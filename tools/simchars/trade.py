"""
Trade primitive for sim characters (phase-1 M3/M4).

One arbitrage leg: buy at the current station, load cargo, haul to the
destination station (any number of gate jumps), unload, sell.  Wallet
delta and item conservation are verified against DB truth after every
step; every mismatch is a TRADE finding.

The route scorer (find_best_route) is the M4 greedy brain: scan the
region book for commodities where the best sell (ask) somewhere is
cheaper than the best buy (bid) elsewhere by more than the margin floor,
scored by profit per m3 per jump.
"""

import time

import cargo
import db
import market
import travel
from machoclient import CallError, log


def db_wallet(char_id):
    """Char cash balance straight from the DB (source of truth).
    NOTE: the server caches balances; the DB value lags until the server
    persists, so treat small windows of staleness as normal."""
    r = db.query(f"SELECT balance FROM chrCharacters"
                 f" WHERE characterID = {int(char_id)}")
    return float(r[0]["balance"]) if r else None


class TradePlan:
    def __init__(self, type_id, qty, buy_price, sell_price,
                 src_station, dst_station, jumps, volume_each):
        self.type_id = type_id
        self.qty = qty
        self.buy_price = buy_price
        self.sell_price = sell_price
        self.src_station = src_station
        self.dst_station = dst_station
        self.jumps = jumps
        self.volume_each = volume_each

    @property
    def outlay(self):
        return self.buy_price * self.qty

    @property
    def expected_profit(self):
        return (self.sell_price - self.buy_price) * self.qty

    def __repr__(self):
        return (f"TradePlan(type {self.type_id} x{self.qty}: buy "
                f"{self.buy_price:.2f}@{self.src_station} -> sell "
                f"{self.sell_price:.2f}@{self.dst_station}, {self.jumps} "
                f"jumps, profit {self.expected_profit:,.0f})")


def station_system(station_id):
    r = db.query(f"SELECT solarSystemID FROM staStations WHERE stationID = {int(station_id)}")
    return int(r[0]["solarSystemID"]) if r else None


def find_best_route(mch, char_id, here_station, cargo_m3, budget,
                    commodities, min_margin=0.08, max_jumps=6,
                    min_security=0.45):
    """Greedy arbitrage scan over the given commodity typeIDs.

    Only considers buying at THIS station (immediate fill against local
    asks) and selling to standing buy orders anywhere within max_jumps.
    Score = profit / m3 / (jumps+1).  Returns best TradePlan or None."""
    here_system = station_system(here_station)
    best, best_score = None, 0.0
    for tid in commodities:
        try:
            sells, buys = market.get_orders(mch, tid)
        except CallError as e:
            log(f"TRADE-KINK: GetOrders({tid}) failed: {str(e)[:150]}")
            continue
        local_asks = sorted((s for s in sells
                             if s["stationID"] == here_station
                             and s["volRemaining"] > 0),
                            key=lambda s: s["price"])
        if not local_asks:
            continue
        ask = local_asks[0]
        vol = cargo.type_volume(tid)
        if vol <= 0:
            continue
        for bid in sorted(buys, key=lambda b: -b["price"]):
            if bid["stationID"] == here_station:
                continue
            margin = (bid["price"] - ask["price"]) / ask["price"]
            if margin < min_margin:
                break   # buys sorted desc; nothing better follows
            dst_sys = station_system(bid["stationID"])
            if dst_sys is None:
                continue
            jumps = travel.jumps_between(here_system, dst_sys, min_security)
            if jumps is None or jumps > max_jumps:
                continue
            qty = int(min(
                cargo_m3 // vol,
                bid["volRemaining"],
                ask["volRemaining"],
                budget // ask["price"]))
            if qty < max(1, bid.get("minVolume", 1)):
                continue
            profit = (bid["price"] - ask["price"]) * qty
            score = profit / (vol * qty) / (jumps + 1)
            if score > best_score:
                best_score = score
                best = TradePlan(tid, qty, ask["price"], bid["price"],
                                 here_station, int(bid["stationID"]),
                                 jumps, vol)
    return best


def find_best_route_db(char_id, here_station, cargo_m3, budget,
                       min_margin=0.06, max_jumps=8, min_security=0.45,
                       exclude_types=()):
    """Coordinator-side arbitrage scan over the whole mktOrders book.

    Route DISCOVERY reads the DB (the 'higher coordinator' feeding the
    sim pilots); route EXECUTION in execute_leg is pure protocol.  The
    leg may start with a pickup hop: buy at any station within
    max_jumps, haul to the best standing buy order within max_jumps of
    the pickup.  Scored by profit / m3 / total jumps."""
    here_system = station_system(here_station)
    jump_cache = {}

    def jumps_from(sys_a, sys_b):
        key = (sys_a, sys_b)
        if key not in jump_cache:
            jump_cache[key] = travel.jumps_between(sys_a, sys_b, min_security)
        return jump_cache[key]

    # one DB-side join: cheapest ask per type vs every richer bid, capped
    # to the top spread candidates (keeps the SQL short -- db.query goes
    # through a command line)
    # needs idx_mkt_scan (bid, typeID, price) -- built by the coordinator;
    # min/max per type resolve from the index, then join back for the rows
    candidates = db.query(f"""
SELECT ao.typeID, ao.stationID srcStation, ao.solarSystemID srcSys,
       am.mn ask, ao.volRemaining askVol, t.volume vol,
       bo.stationID dstStation, bo.solarSystemID dstSys,
       bm.mx bid, bo.volRemaining bidVol, bo.minVolume
FROM (SELECT typeID, MIN(price) mn FROM mktOrders
      WHERE bid = 0 AND volRemaining > 0 GROUP BY typeID) am
JOIN (SELECT typeID, MAX(price) mx FROM mktOrders
      WHERE bid = 1 AND volRemaining > 0 GROUP BY typeID) bm
  ON bm.typeID = am.typeID AND bm.mx > am.mn * {1.0 + float(min_margin)}
JOIN mktOrders ao ON ao.typeID = am.typeID AND ao.bid = 0
     AND ao.price = am.mn AND ao.volRemaining > 0
JOIN mktOrders bo ON bo.typeID = bm.typeID AND bo.bid = 1
     AND bo.price = bm.mx AND bo.volRemaining > 0
JOIN invTypes t ON t.typeID = am.typeID
WHERE bo.stationID != ao.stationID AND t.volume > 0
GROUP BY am.typeID
ORDER BY (bm.mx - am.mn) / am.mn DESC LIMIT 120""")
    best, best_score = None, 0.0
    for c in candidates:
        tid = int(c["typeID"])
        if tid in exclude_types:
            continue
        ask_price = float(c["ask"])
        bid_price = float(c["bid"])
        vol = float(c["vol"])
        pickup = jumps_from(here_system, int(c["srcSys"]))
        if pickup is None or pickup > max_jumps:
            continue
        haul = jumps_from(int(c["srcSys"]), int(c["dstSys"]))
        if haul is None or (pickup + haul) > max_jumps:
            continue
        qty = int(min(cargo_m3 // vol, int(c["bidVol"]), int(c["askVol"]),
                      budget // ask_price))
        if qty < max(1, int(c["minVolume"] or 1)):
            continue
        profit = (bid_price - ask_price) * qty
        score = profit / (vol * qty) / (pickup + haul + 1)
        if score > best_score:
            best_score = score
            best = TradePlan(tid, qty, ask_price, bid_price,
                             int(c["srcStation"]), int(c["dstStation"]),
                             pickup + haul, vol)
    return best


def execute_leg(mch, char_id, ship_id, plan, kink=None):
    """Run one buy->haul->sell leg.  Returns realized wallet delta or None."""
    note = kink or (lambda m: log(f"TRADE-KINK: {m}"))
    t0 = time.time()
    w0 = db_wallet(char_id)

    # --- pickup hop: get to the source station if not already there
    here = mch.session.get("stationid")
    if here != plan.src_station:
        from provision import STATION_GROUP
        if here:
            sref = mch.bind("ship", (here, STATION_GROUP))
            mch.call_bound(sref, "Undock", ship_id, False)
            mch.pump(12)
            bey = travel.bind_beyonce(mch)
            try:
                mch.call_bound(bey, "CmdStop")
            except CallError:
                pass
            mch.pump(8)
        if not travel.goto_station(mch, ship_id, plan.src_station, kink=note):
            note(f"pickup hop to {plan.src_station} failed")
            return None

    # --- buy (immediate fill at source station)
    try:
        market.buy_immediate(mch, plan.src_station, plan.type_id,
                             plan.buy_price, plan.qty)
    except CallError as e:
        note(f"buy failed: {str(e)[:200]}")
        return None
    mch.pump(3)
    stacks = cargo.hangar_stacks(char_id, plan.src_station, plan.type_id)
    have = sum(q for _, q in stacks)
    if have < plan.qty:
        note(f"buy verify: wanted {plan.qty}, hangar has {have}")
        if have == 0:
            return None
        plan.qty = have

    # --- load
    inv = cargo.station_invbroker(mch, plan.src_station)
    moved = cargo.load_cargo(mch, inv, char_id, plan.src_station, ship_id,
                             plan.type_id, plan.qty, kink=note)
    if moved <= 0:
        note("nothing loaded; aborting leg")
        return None

    # --- undock + haul
    from provision import STATION_GROUP
    sref = mch.bind("ship", (plan.src_station, STATION_GROUP))
    mch.call_bound(sref, "Undock", ship_id, False)
    mch.pump(12)
    bey = travel.bind_beyonce(mch)
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(8)
    if not travel.goto_station(mch, ship_id, plan.dst_station, kink=note):
        note(f"haul to {plan.dst_station} failed (cargo aboard!)")
        return None

    # --- unload + sell (sells need the hangar stack itemID -- MKT-1)
    inv = cargo.station_invbroker(mch, plan.dst_station)
    cargo.unload_cargo(mch, inv, char_id, plan.dst_station, ship_id,
                       plan.type_id, kink=note)
    sold = 0
    for item_id, qty in cargo.hangar_stacks(char_id, plan.dst_station,
                                            plan.type_id):
        try:
            market.sell_immediate(mch, plan.dst_station, plan.type_id,
                                  plan.sell_price, qty, item_id)
            sold += qty
        except CallError as e:
            note(f"sell of stack {item_id} x{qty} failed: {str(e)[:200]}")
    if sold == 0:
        note("nothing sold")
        return None
    mch.pump(3)

    # --- verify
    w1 = db_wallet(char_id)
    left = cargo.hangar_stacks(char_id, plan.dst_station, plan.type_id)
    if left:
        note(f"sell verify: {sum(q for _, q in left)} units unsold in hangar")
    delta = None if (w0 is None or w1 is None) else (w1 - w0)
    log(f"TRADE leg done in {time.time()-t0:.0f}s: {plan!r} realized "
        f"wallet delta {delta if delta is None else format(delta, ',.0f')}")
    return delta

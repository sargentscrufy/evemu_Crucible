#!/usr/bin/env python3
"""
Provision a sim character: fund -> buy -> assemble -> fit -> board.

The selector picks the best affordable archetype template available on
the character's local market, honoring the hull's real slot layout.

Usage:
    python provision.py --user aura --password aura --char-id 90000002 \
        --archetype hauler [--fund 20000000] [--undock-test] [--port 26000]

Requires the character to be OFFLINE at start (funding + fresh session).
"""

import argparse
import time

import db
import fits
from machoclient import MachoClient, CallError, log

STATION_GROUP = 15
SOLARSYSTEM_GROUP = 5


def pick_fit(archetype, station_id, budget):
    """Choose the priciest affordable, locally-available template."""
    candidates = []
    for tpl in fits.templates_for(archetype):
        try:
            ship_tid = db.type_id(tpl.ship)
        except KeyError:
            continue
        ask = db.station_ask(station_id, ship_tid)
        if ask is None:
            continue
        ship_price = ask[0]
        lo, mid, hi = db.slot_layout(ship_tid)
        plan, dropped = fits.slot_flags(tpl, lo, mid, hi)
        total = ship_price
        buyable = []
        for type_name, flag in plan:
            tid = db.type_id(type_name)
            mod_ask = db.station_ask(station_id, tid)
            if mod_ask is None:
                dropped.append(type_name)
                continue
            buyable.append((type_name, tid, flag, mod_ask[0]))
            total += mod_ask[0]
        if total <= budget:
            candidates.append((total, tpl, ship_tid, ship_price,
                               buyable, dropped))
    if not candidates:
        return None
    candidates.sort(key=lambda c: -c[0])   # prefer the best we can afford
    return candidates[0]


def immediate_buy(mch, station_id, tid, price, qty=1):
    """PlaceCharOrder as an immediate buy against the standing sell order.

    Signature (MarketProxyService.cpp): stationID, typeID, price(float),
    quantity, bid, orderRange, itemID?, minVolume, duration, useCorp,
    located?.  duration=0 -> immediate.
    """
    mch.call("marketProxy", "PlaceCharOrder",
             station_id, tid, float(price), qty, 1, 0, None, 1, 0,
             False, None)


def ensure_docked(mch, station_id, system_id, ship_item, patience=90.0):
    """If the session is undocked, dock at the given station and wait.

    Sends CmdStop first: login warp-in can leave the ship in a stuck
    warp/align state (DestinyError 'warp align/speed is incorrect') that
    silently blocks dock requests — the real client also stops on login.
    """
    if mch.session.get("stationid"):
        return True
    log(f"not docked; requesting dock at {station_id}")
    bey_ref = mch.bind("beyonce", (system_id, SOLARSYSTEM_GROUP))
    try:
        mch.call_bound(bey_ref, "CmdStop")
    except CallError as e:
        log(f"CmdStop: {e}")
    mch.pump(2.0)
    deadline = time.time() + patience
    mch.call_bound(bey_ref, "CmdDock", station_id, ship_item)
    next_retry = time.time() + 25.0
    while time.time() < deadline:
        mch.pump(2.0)
        if mch.session.get("stationid"):
            log("docked")
            return True
        if time.time() > next_retry:
            next_retry = time.time() + 25.0
            log("dock retry (stop + dock)")
            try:
                mch.call_bound(bey_ref, "CmdStop")
                mch.pump(1.0)
                mch.call_bound(bey_ref, "CmdDock", station_id, ship_item)
            except CallError as e:
                log(f"dock retry: {e}")
    return False


def provision(args):
    # ---- offline phase: everything the Director does before login ----
    station_id = db.char_station(args.char_id) or args.home_station
    if not station_id:
        raise SystemExit("character has no station (in space?); pass "
                         "--home-station")

    balance = db.wallet_balance(args.char_id)
    if args.fund and balance < args.fund:
        log(f"funding wallet: {balance:,.0f} -> {args.fund:,.0f} ISK")
        db.fund_wallet(args.char_id, args.fund)
        balance = args.fund

    # stranded in space from a previous run/crash? recover to the dock
    # perimeter while offline so the online dock request is trivial
    if not db.char_station(args.char_id):
        ship_row = db.query("SELECT shipID FROM chrCharacters WHERE "
                            f"characterID = {int(args.char_id)}")
        if ship_row and int(ship_row[0]["shipID"]):
            log(f"recovering stranded ship to station {station_id} "
                "perimeter")
            db.recover_ship_to_station(args.char_id,
                                       int(ship_row[0]["shipID"]),
                                       station_id)

    # select fit against the local market
    choice = pick_fit(args.archetype, station_id, balance * 0.95)
    if choice is None:
        raise SystemExit(f"no affordable {args.archetype!r} template "
                         f"available at station {station_id}")
    total, tpl, ship_tid, ship_price, modules, dropped = choice
    log(f"selected fit {tpl.name!r}: {tpl.ship} + "
        f"{len(modules)} modules, est {total:,.0f} ISK")
    for d in dropped:
        log(f"  (dropped, unavailable/no slot: {d})")

    # grant the archetype's skills (hull + modules, incl. prerequisites)
    fit_types = [ship_tid] + [tid for _n, tid, _f, _p in modules]
    granted = 0
    for skill_tid, level in db.skill_closure(fit_types):
        if db.grant_skill(args.char_id, skill_tid, level):
            granted += 1
    log(f"skill grant: {granted} skills added/raised for the fit")

    # ---- online phase ----
    mch = MachoClient(args.host, args.port, args.user, args.password,
                      verbose=args.verbose)
    sess = mch.enter_world(args.char_id)
    system_id = sess["solarsystemid2"]
    log(f"in world: station {sess['stationid']}, system {system_id}")

    # if a previous run left the character in space, dock first
    cur_ship = mch.session.get("shipid") or db.query(
        "SELECT shipID FROM chrCharacters WHERE characterID = "
        f"{int(args.char_id)}")[0]["shipID"]
    if not ensure_docked(mch, station_id, system_id, int(cur_ship)):
        raise SystemExit("could not dock; aborting")

    # buy what the hangar doesn't already hold (idempotent re-runs)
    if db.hangar_items(args.char_id, station_id, ship_tid):
        log(f"{tpl.ship} already in hangar, skipping purchase")
    else:
        log(f"buying {tpl.ship} @ {ship_price:,.2f}")
        immediate_buy(mch, station_id, ship_tid, ship_price)
    owned = {}
    for type_name, tid, flag, price in modules:
        owned.setdefault(tid, len(db.hangar_items(args.char_id,
                                                  station_id, tid)))
        if owned[tid] > 0:
            owned[tid] -= 1
            log(f"{type_name} already in hangar, skipping purchase")
            continue
        log(f"buying {type_name} @ {price:,.2f}")
        immediate_buy(mch, station_id, tid, price)
    mch.pump(2.0)

    # 5. find the hull in hangar
    hulls = db.hangar_items(args.char_id, station_id, ship_tid)
    if not hulls:
        raise SystemExit("ship purchase did not arrive in hangar")
    ship_item = hulls[0]["itemID"]
    log(f"ship item {ship_item} in hangar "
        f"(packaged={not hulls[0]['singleton']})")

    # 6. assemble + board prep: bind ship service at the station
    ship_ref = mch.bind("ship", (station_id, STATION_GROUP))
    if not hulls[0]["singleton"]:
        log("assembling ship")
        # must send a LIST: the server's single-int AssembleShip overload
        # re-checks the original tuple and silently no-ops (bug SHIP-1)
        mch.call_bound(ship_ref, "AssembleShip", [ship_item])

    # 7. make it the active ship BEFORE fitting: the server resolves
    #    module-slot moves against the pilot's active ship
    #    (InventoryBound::MoveItems uses pClient->GetShip()), so fitting a
    #    non-active hull hits the active ship's slots instead.
    if int(mch.session.get("shipid") or 0) == ship_item:
        log("ship already active")
    else:
        log("activating ship")
        old_ship = mch.session.get("shipid")
        if old_ship:
            mch.call_bound(ship_ref, "ActivateShip", ship_item, old_ship)
        else:
            mch.call_bound(ship_ref, "ActivateShip", ship_item)
        mch.pump(2.0)

    # 8. fit modules through the ship's bound inventory
    inv_ref = mch.bind("invbroker", (station_id, STATION_GROUP))
    rsp = mch.call_bound(inv_ref, "GetInventoryFromId", ship_item, 1)
    from machoclient import find_bound_refs
    sub = [r for r in find_bound_refs(rsp) if r != inv_ref]
    if not sub:
        raise SystemExit(f"no ship inventory binding in {rsp!r}")
    ship_inv = sub[0]

    used = set()
    for type_name, tid, flag, _price in modules:
        mods = [m for m in db.hangar_items(args.char_id, station_id, tid)
                if m["itemID"] not in used]
        if not mods:
            log(f"  !! {type_name} not found in hangar, skipping")
            continue
        used.add(mods[0]["itemID"])
        log(f"fitting {type_name} -> flag {flag}")
        try:
            mch.call_bound(ship_inv, "Add", mods[0]["itemID"], station_id,
                           byname={"flag": flag, "qty": 1})
        except CallError as e:
            log(f"  !! fit failed: {e}")

    # 9. verify from DB
    fitting = db.ship_fitting(ship_item)
    log("final fitting:")
    for f in fitting:
        log(f"  flag {f['flag']:>2}  {f['typeName']}")

    # 10. optional undock/redock round trip
    if args.undock_test:
        log("UNDOCK TEST: undocking...")
        try:
            mch.call_bound(ship_ref, "Undock", ship_item, False)
            mch.pump(10.0)
            log(f"in space? session: solarsystemid2="
                f"{mch.session.get('solarsystemid2')} "
                f"stationid={mch.session.get('stationid')}")
            mch.session.pop("stationid", None)
            if ensure_docked(mch, station_id, system_id, ship_item):
                log("undock/redock round trip complete")
            else:
                log("!! did not re-dock within patience window; character "
                    "left in space (next run will dock first)")
        except (CallError, TimeoutError) as e:
            log(f"undock test: {e}")

    mch.close()
    log("provisioning complete")


def main():
    ap = argparse.ArgumentParser(description="Provision a sim character")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=26000)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--char-id", type=int, required=True)
    ap.add_argument("--archetype", default="hauler",
                    choices=sorted({f.archetype for f in fits.FITS}))
    ap.add_argument("--fund", type=float, default=20000000)
    ap.add_argument("--home-station", type=int, default=0,
                    help="fallback station when the character is in space")
    ap.add_argument("--undock-test", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    provision(ap.parse_args())


if __name__ == "__main__":
    main()

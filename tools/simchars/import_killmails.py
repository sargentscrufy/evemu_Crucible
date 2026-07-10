#!/usr/bin/env python3
"""
Replicate killmail ships (hull + exact fitting + cargo) into a character's
station hangar, directly in the DB (Director-side provisioning).

Input: a JSON file of killmails (see data/sargentscrufy_losses.json,
built from zkillboard/ESI). For each killmail a fully-assembled ship is
created in the hangar with modules in their recorded slots, loaded
charges, rigs, drones, and cargo.

Era handling:
  - typeIDs missing from this server's (Crucible) invTypes are skipped
    and reported — later-era items cannot exist here.
  - pre-2012 killmails carry flag 0 for fitted items; those modules are
    slot-solved from their dogma power effects (lo=11 / hi=12 / med=13,
    rig=2663) and charges are placed in cargo.

Usage:
    python import_killmails.py --char-id 90000003 --station 60014659 \
        --data data/sargentscrufy_losses.json [--fund 1000000000]

Character must be OFFLINE (server caches items/wallets of online chars).
"""

import argparse
import json
import os

import db
from machoclient import log

FLAG_HANGAR = 4
FLAG_CARGO = 5
FLAG_DRONEBAY = 87
LO = list(range(11, 19))
MID = list(range(19, 27))
HI = list(range(27, 35))
RIG = [92, 93, 94]
# flags valid in the Crucible era; anything else (ore holds, fuel bays,
# subsystem slots from later expansions) is remapped to cargo
VALID_FLAGS = {FLAG_HANGAR, FLAG_CARGO, FLAG_DRONEBAY, *LO, *MID, *HI, *RIG}

EFFECT_LO, EFFECT_HI, EFFECT_MID, EFFECT_RIG = 11, 12, 13, 2663


def type_info(tid):
    rows = db.query(
        "SELECT t.typeID, t.typeName, g.categoryID FROM invTypes t "
        f"JOIN invGroups g USING (groupID) WHERE t.typeID = {int(tid)}")
    return rows[0] if rows else None


def slot_effect(tid):
    rows = db.query(
        "SELECT effectID FROM dgmTypeEffects WHERE typeID = "
        f"{int(tid)} AND effectID IN (11, 12, 13, 2663)")
    return int(rows[0]["effectID"]) if rows else 0


def insert_entity(name, tid, owner, location, flag, qty, singleton):
    # INSERT and LAST_INSERT_ID must share one connection (each db call
    # is its own mariadb session, where LAST_INSERT_ID() would be 0)
    rows = db.query(
        "INSERT INTO entity (itemName, typeID, ownerID, locationID, flag, "
        "singleton, quantity) VALUES "
        f"({db.sql_str(name)}, {int(tid)}, {int(owner)}, {int(location)}, "
        f"{int(flag)}, {int(singleton)}, {int(qty)}); "
        "SELECT LAST_INSERT_ID() AS id")
    return int(rows[0]["id"])


def import_killmail(km, char_id, station_id):
    ship = type_info(km["ship_type_id"])
    if ship is None:
        log(f"KM {km['killmail_id']}: hull type {km['ship_type_id']} does "
            f"not exist in this era — SKIPPED ENTIRELY")
        return None
    year = km["time"][:4]
    ship_name = f"{ship['typeName']} '{year[2:]}"

    ship_item = insert_entity(ship_name, km["ship_type_id"], char_id,
                              station_id, FLAG_HANGAR, 1, 1)
    log(f"KM {km['killmail_id']} ({km['time']}): {ship_name} "
        f"-> item {ship_item}")

    # merge duplicate (type, flag) rows (ESI splits destroyed/dropped)
    merged = {}
    for it in km["items"]:
        key = (it["type"], it["flag"])
        merged[key] = merged.get(key, 0) + it["qty"]

    used_slots = set()
    skipped = []
    deferred = []   # flag-0 items to slot-solve after flagged ones land

    for (tid, flag), qty in sorted(merged.items(), key=lambda kv: kv[0][1],
                                   reverse=True):
        info = type_info(tid)
        if info is None:
            skipped.append((tid, qty))
            continue
        if flag == 0:
            deferred.append((tid, info, qty))
            continue
        if flag not in VALID_FLAGS:
            log(f"  flag {flag} not valid in this era; {info['typeName']} "
                f"x{qty} -> cargo")
            flag = FLAG_CARGO
        singleton = 1 if (flag in LO + MID + HI + RIG
                          and int(info["categoryID"]) in (7, 32)) else 0
        if flag in LO + MID + HI + RIG and singleton:
            used_slots.add(flag)
        insert_entity(info["typeName"], tid, char_id, ship_item, flag,
                      qty, singleton)

    # slot-solve the pre-2012 flag-0 items
    for tid, info, qty in deferred:
        cat = int(info["categoryID"])
        if cat == 8:  # charges without slot info go to cargo
            insert_entity(info["typeName"], tid, char_id, ship_item,
                          FLAG_CARGO, qty, 0)
            continue
        if cat == 18:  # drones
            insert_entity(info["typeName"], tid, char_id, ship_item,
                          FLAG_DRONEBAY, qty, 0)
            continue
        if cat in (7, 32):  # modules/subsystems: place per power effect
            eff = slot_effect(tid)
            bank = {EFFECT_LO: LO, EFFECT_MID: MID, EFFECT_HI: HI,
                    EFFECT_RIG: RIG}.get(eff)
            if bank is None:  # not fittable? stash in cargo
                insert_entity(info["typeName"], tid, char_id, ship_item,
                              FLAG_CARGO, qty, 0)
                continue
            for _ in range(qty):
                slot = next((s for s in bank if s not in used_slots), None)
                if slot is None:  # out of slots -> cargo
                    insert_entity(info["typeName"], tid, char_id,
                                  ship_item, FLAG_CARGO, 1, 0)
                    continue
                used_slots.add(slot)
                insert_entity(info["typeName"], tid, char_id, ship_item,
                              slot, 1, 1)
            continue
        # anything else (implants dropped into wrecks, etc.) -> cargo
        insert_entity(info["typeName"], tid, char_id, ship_item,
                      FLAG_CARGO, qty, 0)

    for tid, qty in skipped:
        log(f"  skipped type {tid} x{qty} (not in this era's data)")
    return ship_item


def main():
    ap = argparse.ArgumentParser(description="killmail hangar importer")
    ap.add_argument("--char-id", type=int, required=True)
    ap.add_argument("--station", type=int, required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--fund", type=float, default=0)
    args = ap.parse_args()

    rows = db.query("SELECT online FROM chrCharacters WHERE characterID = "
                    f"{args.char_id}")
    if not rows:
        raise SystemExit(f"character {args.char_id} not found")
    if rows[0]["online"] not in ("0", ""):
        raise SystemExit("character is online; log out first")

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           args.data) if not os.path.isabs(args.data)
              else args.data) as f:
        data = json.load(f)

    log(f"importing {len(data['killmails'])} killmails for "
        f"{data.get('character', '?')} into station {args.station}")
    ships = []
    for km in data["killmails"]:
        item = import_killmail(km, args.char_id, args.station)
        if item:
            ships.append(item)

    if args.fund:
        db.fund_wallet(args.char_id, args.fund)
        log(f"wallet funded: {args.fund:,.0f} ISK")

    log(f"done: {len(ships)} ships in hangar")


if __name__ == "__main__":
    main()

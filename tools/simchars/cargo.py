"""
Cargo / hangar inventory layer for sim characters (phase-1 M3).

Wire shapes (InvBrokerService.cpp + provision.py fitting flow):
  - bind "invbroker" (stationID, STATION_GROUP) while docked
  - GetInventoryFromId(shipID, 1)      -> bound ship inventory
  - GetInventory(containerHangar=4, charID) -> bound hangar inventory
  - <inv>.Add(itemID, fromLocationID, byname flag/qty) moves items into
    that inventory; flagCargoHold=5, flagHangar=4.
Item ground truth is read back from the DB (entity table) after every
move -- economy integrity checks are non-negotiable before scaling bots.
"""

import db
from machoclient import CallError, find_bound_refs, log

FLAG_HANGAR = 4
FLAG_CARGO = 5
CONTAINER_HANGAR = 10004    # Inv::Container::Hangar (InvBrokerService.cpp)


def station_invbroker(mch, station_id):
    from provision import STATION_GROUP
    return mch.bind("invbroker", (int(station_id), STATION_GROUP))


def ship_inventory(mch, inv_ref, ship_id):
    rsp = mch.call_bound(inv_ref, "GetInventoryFromId", int(ship_id), 1)
    subs = [r for r in find_bound_refs(rsp) if r != inv_ref]
    if not subs:
        raise CallError(f"no ship inventory bind in {repr(rsp)[:200]}")
    return subs[0]


def hangar_inventory(mch, inv_ref, char_id):
    rsp = mch.call_bound(inv_ref, "GetInventory", CONTAINER_HANGAR,
                         int(char_id))
    subs = [r for r in find_bound_refs(rsp) if r != inv_ref]
    if not subs:
        raise CallError(f"no hangar inventory bind in {repr(rsp)[:200]}")
    return subs[0]


# ------------------------------------------------------------ DB truth

def hangar_stacks(char_id, station_id, type_id):
    """[(itemID, qty)] of a type in the char's station hangar (DB truth)."""
    rows = db.query(
        f"SELECT itemID, quantity FROM entity WHERE ownerID = {int(char_id)}"
        f" AND locationID = {int(station_id)} AND flag = {FLAG_HANGAR}"
        f" AND typeID = {int(type_id)}")
    return [(int(r["itemID"]), int(r["quantity"])) for r in rows]


def cargo_stacks(ship_id, type_id=None):
    """[(itemID, typeID, qty)] in a ship's cargo hold (DB truth)."""
    cond = f" AND typeID = {int(type_id)}" if type_id else ""
    rows = db.query(
        f"SELECT itemID, typeID, quantity FROM entity"
        f" WHERE locationID = {int(ship_id)} AND flag = {FLAG_CARGO}{cond}")
    return [(int(r["itemID"]), int(r["typeID"]), int(r["quantity"]))
            for r in rows]


def type_volume(type_id):
    r = db.query(f"SELECT volume FROM invTypes WHERE typeID = {int(type_id)}")
    return float(r[0]["volume"]) if r else 0.0


def cargo_capacity(ship_id):
    r = db.query(
        f"SELECT valueFloat, valueInt FROM entity_attributes"
        f" WHERE itemID = {int(ship_id)} AND attributeID = 38")  # capacity
    if r:
        v = r[0]["valueFloat"] or r[0]["valueInt"]
        return float(v)
    # fall back to type default
    r = db.query(
        f"SELECT t.capacity FROM invTypes t JOIN entity e ON e.typeID = t.typeID"
        f" WHERE e.itemID = {int(ship_id)}")
    return float(r[0]["capacity"]) if r else 0.0


# ------------------------------------------------------------ movements

def load_cargo(mch, inv_ref, char_id, station_id, ship_id, type_id, qty,
               kink=None):
    """Move qty of type from station hangar into ship cargo.  Verifies via
    DB that the cargo count actually changed by qty."""
    note = kink or (lambda m: log(f"CARGO-KINK: {m}"))
    before = sum(q for _, _, q in cargo_stacks(ship_id, type_id))
    ship_inv = ship_inventory(mch, inv_ref, ship_id)
    remaining = int(qty)
    for item_id, stack_qty in hangar_stacks(char_id, station_id, type_id):
        if remaining <= 0:
            break
        take = min(stack_qty, remaining)
        try:
            mch.call_bound(ship_inv, "Add", item_id, int(station_id),
                           byname={"flag": FLAG_CARGO, "qty": take})
            remaining -= take
        except CallError as e:
            note(f"load Add({item_id} x{take}) failed: {str(e)[:180]}")
            break
    mch.pump(2)
    after = sum(q for _, _, q in cargo_stacks(ship_id, type_id))
    moved = after - before
    if moved != int(qty):
        note(f"load verify: wanted {qty}, cargo delta {moved}")
    return moved


def unload_cargo(mch, inv_ref, char_id, station_id, ship_id, type_id=None,
                 kink=None):
    """Move all cargo (optionally one type) from ship to station hangar.
    Returns units moved per DB verification."""
    note = kink or (lambda m: log(f"CARGO-KINK: {m}"))
    stacks = cargo_stacks(ship_id, type_id)
    if not stacks:
        return 0
    hangar_inv = hangar_inventory(mch, inv_ref, char_id)
    moved = 0
    for item_id, tid, qty in stacks:
        try:
            mch.call_bound(hangar_inv, "Add", item_id, int(ship_id),
                           byname={"flag": FLAG_HANGAR, "qty": qty})
            moved += qty
        except CallError as e:
            note(f"unload Add({item_id} x{qty}) failed: {str(e)[:180]}")
    mch.pump(2)
    left = cargo_stacks(ship_id, type_id)
    if left:
        note(f"unload verify: {len(left)} stacks still in cargo: {left}")
    return moved

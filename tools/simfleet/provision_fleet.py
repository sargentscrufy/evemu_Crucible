#!/usr/bin/env python3
"""
Provision the sim-player fleet from fleet.json:

  1. accounts        -- direct DB insert (same shape/role as the aura acct)
  2. characters      -- protocol CreateCharacterWithDoll (reuses the
                        proven full-doll builders from aura_bot)
  3. ships and fits  -- direct DB staging at the home station, assembled,
                        modules fitted per fleet.json; drones to drone bay
  4. skills + ISK    -- closure-granted for hull+fit; wallets funded

Characters must be OFFLINE and the server should be RESTARTED after
provisioning so item caches load fresh.

    python provision_fleet.py [--only-missing]
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))
sys.path.insert(0, os.path.join(HERE, "..", "smoke-bot"))

import db
from evemarshal import WStr
import login as eve_login
import aura_bot  # character_info/portrait_info/MachoSession/find_ints

FLEET = json.load(open(os.path.join(HERE, "fleet.json")))
HOME_STATION = FLEET["home_station"]
PASSWORD = FLEET["password"]

FLAG_HANGAR = 4
FLAG_DRONEBAY = 87
SLOT_BASE = {"hi": 27, "med": 19, "low": 11}


def log(msg):
    print(f"[fleet] {msg}", flush=True)


def ensure_account(name):
    rows = db.query(f"SELECT accountID FROM account WHERE accountName = '{name}'")
    if rows:
        return int(rows[0]["accountID"])
    db.execute(
        "INSERT INTO account (accountName, password, hash, type, role, online, banned) "
        f"VALUES ('{name}', '{PASSWORD}', '', 23, 7131450020691447808, 0, 0)")
    acct = int(db.query("SELECT LAST_INSERT_ID() AS id")[0]["id"])
    log(f"account {name} created ({acct})")
    return acct


def ensure_character(user, char_name):
    rows = db.query(
        f"SELECT characterID FROM chrCharacters WHERE characterName = '{char_name}'")
    if rows:
        return int(rows[0]["characterID"])
    log(f"creating character {char_name!r} on {user}")
    conn, info = eve_login.login("127.0.0.1", 26000, user, PASSWORD, log=log)
    mch = aura_bot.MachoSession(conn, info.user_id)
    rsp = mch.call(
        "charUnboundMgr", "CreateCharacterWithDoll",
        WStr(char_name), aura_bot.BLOODLINE_CIVIRE, aura_bot.GENDER_FEMALE,
        aura_bot.ANCESTRY_MERCS, aura_bot.character_info(),
        aura_bot.portrait_info(), aura_bot.SCHOOL_STI)
    chars = aura_bot.find_ints(rsp, 90000000, 98000000)
    if not chars:
        raise RuntimeError(f"creation failed for {char_name}: {rsp!r}")
    conn.close()
    log(f"created {char_name} = {chars[0]}")
    time.sleep(2)
    return chars[0]


def insert_item(name, type_id, owner, location, flag, qty=1, singleton=1):
    rows = db.query(
        "INSERT INTO entity (itemName, typeID, ownerID, locationID, flag, "
        "contraband, singleton, quantity, x, y, z, customInfo) VALUES "
        f"('{name}', {type_id}, {owner}, {location}, {flag}, 0, {singleton}, "
        f"{qty}, 0, 0, 0, ''); SELECT LAST_INSERT_ID() AS id")
    return int(rows[0]["id"])


def stage_ship(char_id, char_name, ship_name, fit):
    hull_tid = int(db.type_id(ship_name))
    existing = db.query(
        f"SELECT itemID FROM entity WHERE ownerID = {char_id} AND "
        f"typeID = {hull_tid} AND locationID = {HOME_STATION}")
    if existing:
        return int(existing[0]["itemID"])

    ship = insert_item(f"{char_name}'s {ship_name}", hull_tid, char_id,
                       HOME_STATION, FLAG_HANGAR)
    fitted_types = [hull_tid]
    for rack in ("hi", "med", "low"):
        for i, mod_name in enumerate(fit.get(rack, [])):
            tid = db.type_id(mod_name)
            if not tid:
                log(f"KINK: module type not found: {mod_name!r}")
                continue
            insert_item("", int(tid), char_id, ship, SLOT_BASE[rack] + i)
            fitted_types.append(int(tid))
    for drone_name in fit.get("drones", []):
        tid = db.type_id(drone_name)
        if tid:
            insert_item("", int(tid), char_id, ship, FLAG_DRONEBAY)
            fitted_types.append(int(tid))

    db.execute(f"UPDATE chrCharacters SET shipID = {ship} WHERE characterID = {char_id}")

    # skills for hull + everything fitted, prerequisites included
    for skill_tid, level in db.skill_closure(fitted_types):
        db.grant_skill(char_id, skill_tid, level)

    log(f"{char_name}: {ship_name} {ship} staged with "
        f"{len(fitted_types)-1} modules/drones + skills")
    return ship


def main():
    for pilot in FLEET["pilots"]:
        ensure_account(pilot["account"])
        char_id = ensure_character(pilot["account"], pilot["name"])
        # dock the char at home
        db.execute(
            f"UPDATE chrCharacters SET stationID = {HOME_STATION}, "
            f"solarSystemID = {FLEET['home_system']} WHERE characterID = {char_id}")
        db.execute(
            f"UPDATE entity SET locationID = {HOME_STATION}, flag = 4 "
            f"WHERE itemID = {char_id}")
        stage_ship(char_id, pilot["name"], pilot["ship"],
                   FLEET["fits"][pilot["ship"]])
        db.fund_wallet(char_id, 50_000_000)
    log("fleet provisioned. RESTART THE SERVER before flying "
        "(item caches must reload).")


if __name__ == "__main__":
    sys.exit(main())

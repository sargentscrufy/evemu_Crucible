#!/usr/bin/env python3
"""
Live-fire BRAWLER: an armed Merlin that patrols slowly near a station and
FIGHTS BACK when attacked -- locks its aggressor, orbits, and returns fire
(150mm rail + antimatter) until one of you dies.

    EVE_PILOT="fleet01:fleet:90000004:Keva" python brawler_target.py
"""

import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import fittings
import provision_fleet as pf
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

PORT = int(os.environ.get("EVE_PORT", "26010"))
_p = os.environ.get("EVE_PILOT", "fleet01:fleet:90000004:Keva").split(":")
ACCT, PW, CHAR, TAG = _p[0], _p[1], int(_p[2]), _p[3]
STATION, SYSTEM = 60003760, 30000142
MERLIN, RAIL, AMMO = 603, fittings.RAILGUN_150, fittings.ANTIMATTER_S
SSE = getattr(fittings, "SSE", 8205)   # Small Shield Extender I


def stage():
    ship = pf.insert_item(f"{TAG}'s Brawler", MERLIN, CHAR, STATION, 4)
    pf.insert_item("", RAIL, CHAR, ship, 27)       # hi slot
    pf.insert_item("", SSE, CHAR, ship, 19)        # med slot
    pf.insert_item("", AMMO, CHAR, ship, 5, qty=5000, singleton=0)
    for skill_tid, lvl in db.skill_closure([MERLIN, RAIL, SSE]):
        db.grant_skill(CHAR, skill_tid, lvl)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, locationID={STATION}, "
               f"solarSystemID={SYSTEM}, shipID={ship} WHERE characterID={CHAR}")
    return ship


def ship_alive(item_id):
    return bool(db.query(f"SELECT itemID FROM entity WHERE itemID={item_id}"))


def find_aggressor(notes, own_ids):
    """scan notification reprs for a damage event naming a source shipID"""
    for n in notes:
        r = repr(n)
        if "source" not in r and "Damage" not in r:
            continue
        for m in re.finditer(r"14\d{7}", r):
            sid = int(m.group(0))
            if sid not in own_ids:
                return sid
    return 0


def run():
    online = db.query(f"SELECT online FROM chrCharacters WHERE characterID={CHAR}")[0]["online"]
    if online not in ("0", "", 0):
        raise SystemExit(f"{TAG} online; cannot stage")
    ship = stage()
    log(f"=== {TAG}: Brawler Merlin {ship} (150mm rail, will return fire) ===")

    mch = MachoClient("127.0.0.1", PORT, ACCT, PW)
    mch.enter_world(CHAR)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log("could not stage docked"); return

    mods = {int(r["typeID"]): int(r["itemID"]) for r in db.query(
        f"SELECT itemID, typeID FROM entity WHERE locationID={ship} "
        f"AND flag BETWEEN 19 AND 34")}
    rail, sse = mods.get(RAIL), mods.get(SSE)

    st_dogma = mch.bind("dogmaIM", (STATION, STATION_GROUP))
    for m in (rail, sse):
        if not m: continue
        try: mch.call_bound(st_dogma, "SetModuleOnline", ship, m)
        except CallError: pass
    charge = db.query(f"SELECT itemID FROM entity WHERE locationID={ship} "
                      f"AND flag=5 AND typeID={AMMO} LIMIT 1")
    try:
        mch.call_bound(st_dogma, "LoadAmmoToModules", ship, [rail],
                       AMMO, int(charge[0]["itemID"]), ship)
        mch.pump(2)
    except CallError as e:
        log(f"ammo load: {str(e)[:80]}")

    sref = mch.bind("ship", (STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", ship, False)
    log(f"{TAG}: undocked -- patrolling off Jita 4-4, weapons hot")
    mch.pump(10)
    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
    for m in (rail, sse):     # COMP-D: re-online after undock
        if not m: continue
        for _ in range(2):
            try: mch.activate_module(dogma, m, "online", None, 0)
            except CallError: pass
            mch.pump(1.5)

    heading = 1.0
    try:
        mch.call_bound(bey, "CmdGotoDirection", 0.7 * heading, 0.1, 0.7 * heading)
        mch.call_bound(bey, "CmdSetSpeedFraction", 0.4)
    except CallError: pass

    own_ids = {ship, rail or 0, sse or 0}
    aggressor, engaged = 0, False
    flip_at = time.time() + 240
    deadline = time.time() + 120 * 60
    note_idx = len(mch.notifications)

    while time.time() < deadline:
        try:
            mch.pump(5)
        except Exception as e:
            log(f"session hiccup: {str(e)[:60]}")
        if not ship_alive(ship):
            log(f"=== {TAG}: Brawler DESTROYED. Good fight. ===")
            break
        if not engaged:
            aggressor = find_aggressor(mch.notifications[note_idx:], own_ids)
            note_idx = len(mch.notifications)
            if aggressor:
                log(f"{TAG}: taking fire from {aggressor} -- returning fire")
                try: mch.call_bound(dogma, "AddTarget", aggressor)
                except CallError as e: log(f"lock: {str(e)[:80]}")
                mch.pump(5)
                try: mch.call_bound(bey, "CmdOrbit", aggressor, 2500)
                except CallError: pass
                try:
                    mch.activate_module(dogma, rail, "targetAttack", aggressor, 1000)
                    engaged = True
                except CallError as e:
                    log(f"fire: {str(e)[:80]}")
            elif time.time() > flip_at:
                heading = -heading
                flip_at = time.time() + 240
                try:
                    mch.call_bound(bey, "CmdGotoDirection", 0.7 * heading, 0.1, 0.7 * heading)
                    mch.call_bound(bey, "CmdSetSpeedFraction", 0.4)
                except CallError: pass
    else:
        log(f"{TAG}: patrol over, nobody picked a fight")

    try: mch.close()
    except Exception: pass
    db.execute(f"UPDATE chrCharacters SET online=0 WHERE characterID={CHAR}")


if __name__ == "__main__":
    run()

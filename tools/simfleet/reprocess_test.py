#!/usr/bin/env python3
"""
IND-1: reprocessing (refining) validation loop.

A docked pilot with a stack of ore in the station hangar calls the station
reprocessing service to refine it into minerals.  Server path:
`reprocessingSvc` -> Reprocess() computes yield = batches * efficiency *
(1 - tax), spawns the mineral output (invTypeMaterials) into the hangar, and
consumes the ore (portionSize batches).

This test stages Veldspar, refines it, and confirms Tritanium appears in the
hangar with the ore consumed.  Refining skills are granted so the yield is
comfortably above zero.

Run:  python reprocess_test.py
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import provision_fleet as pf
import pvp_battle as pvp
from machoclient import MachoClient, CallError, log
from provision import ensure_docked

STATION, SYSTEM = pvp.STATION, pvp.SYSTEM      # Iyen-Oursta IV - Moon 4
PILOT = ("fleet01", "fleet", 90000004, "Keva")

VELDSPAR = 1230          # portionSize 333 -> 1000 Tritanium per batch
TRITANIUM = 34
ROOKIE = 601             # Ibis, just so the pilot has a ship while docked
FLAG_HANGAR = 4
REFINE_SKILLS = [(3385, 5), (3389, 5), (12195, 4)]   # Refining, Refinery Eff, Veldspar Proc
VELD_QTY = 3330          # 10 batches


def stage(char_id, char_name, veld_qty):
    """Give the pilot ore + a ship in the station hangar and dock them."""
    HOME = pf.HOME_STATION
    pf.HOME_STATION = STATION
    # clear any prior ore/minerals so the yield reads clean
    db.execute(f"DELETE FROM entity WHERE ownerID={char_id} AND locationID={STATION} "
               f"AND typeID IN ({VELDSPAR},{TRITANIUM})")
    ship = pf.insert_item(f"{char_name}'s Ibis", ROOKIE, char_id, STATION, FLAG_HANGAR)
    ore = pf.insert_item("", VELDSPAR, char_id, STATION, FLAG_HANGAR, qty=veld_qty)
    for sk, lvl in REFINE_SKILLS:
        db.grant_skill(char_id, sk, lvl)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, solarSystemID={SYSTEM}, "
               f"shipID={ship} WHERE characterID={char_id}")
    pf.HOME_STATION = HOME
    return ship, ore


def hangar_qty(char_id, type_id):
    r = db.query(f"SELECT COALESCE(SUM(quantity),0) q FROM entity "
                 f"WHERE ownerID={char_id} AND locationID={STATION} AND typeID={type_id}")
    return int(r[0]["q"]) if r else 0


def run():
    acct, pw, char, tag = PILOT
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={char}")[0]["online"] not in ("0", ""):
        raise SystemExit(f"char {char} online; cannot stage")
    ship, ore = stage(char, tag, VELD_QTY)
    log(f"=== IND-1 reprocess: {tag} staged {VELD_QTY} Veldspar (item {ore}) at station {STATION}")

    result = dict(ore_before=VELD_QTY, ore_after=None, trit_before=0, trit_after=0, refined=False)
    mch = MachoClient("127.0.0.1", 26000, acct, pw)
    mch.enter_world(char)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log(f"{tag}: could not dock"); return result
    result["trit_before"] = hangar_qty(char, TRITANIUM)

    rep = mch.bind("reprocessingSvc", STATION)
    log(f"{tag}: bound reprocessingSvc; requesting quote + reprocess")
    try:
        mch.call_bound(rep, "GetQuotes", [ore], ship)
    except CallError as e:
        log(f"{tag}: GetQuotes: {str(e)[:100]}")
    try:
        mch.call_bound(rep, "Reprocess", [ore], STATION, char, FLAG_HANGAR, False, [])
        log(f"{tag}: Reprocess call returned")
    except CallError as e:
        log(f"{tag}: Reprocess FAILED: {str(e)[:160]}")
    mch.pump(3)
    mch.close()

    result["trit_after"] = hangar_qty(char, TRITANIUM)
    result["ore_after"] = hangar_qty(char, VELDSPAR)
    gained = result["trit_after"] - result["trit_before"]
    result["refined"] = gained > 0 and result["ore_after"] < VELD_QTY

    log("=== VERDICT ===")
    log(f"  Veldspar: {VELD_QTY} -> {result['ore_after']} (consumed {VELD_QTY - result['ore_after']})")
    log(f"  Tritanium gained: {gained}")
    log(f"  >>> REPROCESSING: {'PASS' if result['refined'] else 'FAIL'}")
    return result


if __name__ == "__main__":
    run()

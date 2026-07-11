#!/usr/bin/env python3
"""
IND-4 (and manufacturing consumption proof): processing -> manufacturing chain.

A pilot refines ore into minerals, then manufactures an item from those
minerals -- exercising reprocessing and manufacturing back-to-back and, in
particular, proving that a manufacturing job CONSUMES its bill of materials.

Reprocessing spawns minerals into the loaded station inventory (via
SpawnItem + Move), which is exactly where the manufacturing job's
GetBOMItems() looks -- so this is the honest way to stage materials for a
consumption test (DB-inserted stacks aren't in the runtime inventory).

Chain:  3330 Veldspar --reprocess--> ~8000 Tritanium
        Harvester Mining Drone BPO (needs 5 Tritanium/run) --manufacture--> 1 drone
Verify: Tritanium dropped by the job's requirement AND the drone was built.

    python industry_chain_test.py            # real ~2 min job wait
    python industry_chain_test.py --fast     # DB-advance the job clock
"""

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import cargo
import provision_fleet as pf
import pvp_battle as pvp
from machoclient import MachoClient, CallError, log
from provision import ensure_docked

STATION, SYSTEM = pvp.STATION, pvp.SYSTEM
STATION_GROUP = 15
PILOT = ("fleet01", "fleet", 90000004, "Keva")

VELDSPAR, TRITANIUM = 1230, 34
DRONE_BP, DRONE = 3219, 3218          # Harvester Mining Drone (needs 5 Tritanium/run)
ASSEMBLY_LINE = 78851
FLAG_HANGAR = 4
VELD_QTY = 3330


def stage(char_id, char_name):
    HOME = pf.HOME_STATION
    pf.HOME_STATION = STATION
    db.execute(f"DELETE FROM entity WHERE ownerID={char_id} AND locationID={STATION} "
               f"AND typeID IN ({VELDSPAR},{TRITANIUM},{DRONE_BP},{DRONE})")
    ship = pf.insert_item(f"{char_name}'s Ibis", 601, char_id, STATION, FLAG_HANGAR)
    ore = pf.insert_item("", VELDSPAR, char_id, STATION, FLAG_HANGAR, qty=VELD_QTY)
    bp = pf.insert_item("", DRONE_BP, char_id, STATION, FLAG_HANGAR, singleton=1)
    db.execute(f"DELETE FROM invBlueprints WHERE itemID={bp}")
    db.execute(f"INSERT INTO invBlueprints (itemID, copy, mLevel, pLevel, runs) "
               f"VALUES ({bp}, 0, 10, 10, 1000)")
    for sk, lvl in ((3385, 5), (3389, 5), (12195, 4),      # refining
                    (3380, 5), (3387, 4), (3388, 5),        # industry
                    (3436, 5), (3437, 5)):                  # drone/production support
        db.grant_skill(char_id, sk, lvl)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, solarSystemID={SYSTEM}, "
               f"shipID={ship} WHERE characterID={char_id}")
    pf.HOME_STATION = HOME
    return ship, ore, bp


def hangar_qty(char_id, type_id):
    r = db.query(f"SELECT COALESCE(SUM(quantity),0) q FROM entity "
                 f"WHERE ownerID={char_id} AND locationID={STATION} AND typeID={type_id}")
    return int(r[0]["q"]) if r else 0


def find_job(char_id, bp_id):
    r = db.query(f"SELECT jobID,endProductionTime FROM ramJobs WHERE installerID={char_id} "
                 f"AND installedItemID={bp_id} ORDER BY jobID DESC LIMIT 1")
    return r[0] if r else None


def _ft_now():
    return int((time.time() + 11644473600) * 10_000_000)


def run(fast=False):
    acct, pw, char, tag = PILOT
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={char}")[0]["online"] not in ("0", ""):
        raise SystemExit(f"char {char} online; cannot stage")
    ship, ore, bp = stage(char, tag)
    log(f"=== IND-4 chain: {tag} reprocess {VELD_QTY} Veldspar -> build Harvester Mining Drone")

    r = dict(trit_refined=0, trit_pre_job=0, trit_post_job=0, drones=0)
    mch = MachoClient("127.0.0.1", 26000, acct, pw)
    mch.enter_world(char)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log(f"{tag}: could not dock"); return r
    inv = cargo.station_invbroker(mch, STATION)
    cargo.hangar_inventory(mch, inv, char)

    # --- 1. reprocess ore -> minerals (into the loaded hangar) ---
    rep = mch.bind("reprocessingSvc", STATION)
    try:
        mch.call_bound(rep, "Reprocess", [ore], STATION, char, FLAG_HANGAR, False, [])
    except CallError as e:
        log(f"{tag}: Reprocess failed: {str(e)[:120]}"); mch.close(); return r
    mch.pump(2)
    r["trit_refined"] = hangar_qty(char, TRITANIUM)
    log(f"{tag}: refined -> {r['trit_refined']} Tritanium")
    if r["trit_refined"] < 10:
        log(f"{tag}: not enough Tritanium to build"); mch.close(); return r

    # reload hangar so the freshly-spawned minerals are enumerable by the job
    cargo.hangar_inventory(mch, inv, char)
    r["trit_pre_job"] = hangar_qty(char, TRITANIUM)

    # --- 2. manufacture the drone from those minerals ---
    assembly_line_data = [[STATION, STATION_GROUP], [], [STATION, ASSEMBLY_LINE]]
    bp_data  = [[STATION, STATION_GROUP], [[STATION, char, FLAG_HANGAR]], [bp]]
    bom_data = [[STATION, STATION_GROUP], [[STATION, char, FLAG_HANGAR]], []]
    try:
        mch.call("ramProxy", "InstallJob", assembly_line_data, bp_data, bom_data,
                 FLAG_HANGAR, 1, 1, 0, False, "IND-4 chain")
    except CallError as e:
        log(f"{tag}: InstallJob failed: {str(e)[:160]}"); mch.close(); return r
    job = find_job(char, bp)
    if not job:
        log(f"{tag}: no job created"); mch.close(); return r
    job_id = int(job["jobID"])
    log(f"{tag}: manufacturing job {job_id} installed")

    if fast:
        db.execute(f"UPDATE ramJobs SET endProductionTime={_ft_now()-10} WHERE jobID={job_id}")
    else:
        wait_s = max(0, (int(job["endProductionTime"]) - _ft_now()) / 10_000_000.0) + 5
        log(f"{tag}: waiting {wait_s:.0f}s for the job")
        end = time.time() + wait_s
        while time.time() < end:
            mch.pump(5.0)

    try:
        mch.call("ramProxy", "CompleteJob", [[STATION, STATION_GROUP], [], [STATION]], job_id, False)
    except CallError as e:
        log(f"{tag}: CompleteJob failed: {str(e)[:160]}")
    mch.pump(3)
    mch.close()

    r["trit_post_job"] = hangar_qty(char, TRITANIUM)
    r["drones"] = hangar_qty(char, DRONE)
    consumed = r["trit_pre_job"] - r["trit_post_job"]

    log("=== VERDICT ===")
    log(f"  reprocess: 3330 Veldspar -> {r['trit_refined']} Tritanium")
    log(f"  manufacture: Tritanium {r['trit_pre_job']} -> {r['trit_post_job']} (consumed {consumed})")
    log(f"  Harvester Mining Drones built: {r['drones']}")
    ok = r["drones"] > 0 and consumed > 0
    log(f"  >>> INDUSTRY CHAIN (reprocess + manufacture w/ consumption): {'PASS' if ok else 'FAIL'}")
    if r["drones"] > 0 and consumed == 0:
        log("  NOTE: product built but NO materials consumed -- MANUF material-consumption bug")
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    args = ap.parse_args()
    run(fast=args.fast)

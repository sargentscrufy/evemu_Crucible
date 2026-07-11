#!/usr/bin/env python3
"""
IND-2: manufacturing (industry job) validation loop.

A docked pilot with a blueprint (BPO) and the required minerals in the
station hangar installs a manufacturing job on a station assembly line, waits
out the production time, completes the job, and the built item is delivered to
the hangar.  Server path:  ramProxy.InstallJob (consume materials, schedule
job in ramJobs) -> wait endProductionTime -> ramProxy.CompleteJob (SpawnItem
the product).

We build Antimatter Charge S (222) from its BPO (1137): 1 run needs
184 Tritanium / 15 Pyerite / 1 Nocxium, 300 s base build time.

    python manufacture_test.py            # waits the real ~5 min job time
    python manufacture_test.py --fast     # DB-advances the job clock

Run flags let CI skip the wait; the default is an honest end-to-end run.
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
STATION_GROUP = 15                    # invGroups.Station
PILOT = ("fleet01", "fleet", 90000004, "Keva")

BP_TYPE = 1137                        # Antimatter Charge S Blueprint (BPO)
PRODUCT = 222                         # Antimatter Charge S
ASSEMBLY_LINE = 78851                 # a manufacturing line at STATION
FLAG_HANGAR = 4
ACTIVITY_MANUFACTURING = 1
# generous minerals (base 184/15/1 + waste headroom)
MATS = {34: 400, 35: 60, 38: 10}      # Tritanium, Pyerite, Nocxium


def stage(char_id, char_name):
    HOME = pf.HOME_STATION
    pf.HOME_STATION = STATION
    # clean slate for the blueprint, mats and product
    db.execute(f"DELETE FROM entity WHERE ownerID={char_id} AND locationID={STATION} "
               f"AND typeID IN ({BP_TYPE},{PRODUCT},34,35,38)")
    ship = pf.insert_item(f"{char_name}'s Ibis", 601, char_id, STATION, FLAG_HANGAR)
    bp = pf.insert_item("", BP_TYPE, char_id, STATION, FLAG_HANGAR, singleton=1)
    # a BPO: copy=0, researched ME/PE so waste is low, plenty of runs
    db.execute(f"DELETE FROM invBlueprints WHERE itemID={bp}")
    db.execute(f"INSERT INTO invBlueprints (itemID, copy, mLevel, pLevel, runs) "
               f"VALUES ({bp}, 0, 10, 10, 1000)")
    for tid, qty in MATS.items():
        pf.insert_item("", tid, char_id, STATION, FLAG_HANGAR, qty=qty)
    # industry skills: Industry, Mass Production, Production Efficiency
    for sk, lvl in ((3380, 5), (3387, 4), (3388, 5)):
        db.grant_skill(char_id, sk, lvl)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, solarSystemID={SYSTEM}, "
               f"shipID={ship} WHERE characterID={char_id}")
    pf.HOME_STATION = HOME
    return ship, bp


def hangar_qty(char_id, type_id):
    r = db.query(f"SELECT COALESCE(SUM(quantity),0) q FROM entity "
                 f"WHERE ownerID={char_id} AND locationID={STATION} AND typeID={type_id}")
    return int(r[0]["q"]) if r else 0


def find_job(char_id, bp_id):
    r = db.query(f"SELECT jobID, endProductionTime, completedStatusID FROM ramJobs "
                 f"WHERE installerID={char_id} AND installedItemID={bp_id} "
                 f"ORDER BY jobID DESC LIMIT 1")
    return r[0] if r else None


def run(fast=False):
    acct, pw, char, tag = PILOT
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={char}")[0]["online"] not in ("0", ""):
        raise SystemExit(f"char {char} online; cannot stage")
    ship, bp = stage(char, tag)
    log(f"=== IND-2 manufacture: {tag} BPO {bp} (Antimatter Charge S) at station {STATION}")

    result = dict(installed=False, job_id=None, completed=False,
                  product_before=0, product_after=0, mats_before=dict(MATS))

    mch = MachoClient("127.0.0.1", 26000, acct, pw)
    mch.enter_world(char)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log(f"{tag}: could not dock"); return result
    result["product_before"] = hangar_qty(char, PRODUCT)

    # load the station hangar into the server's runtime inventory so the job's
    # bill-of-materials scan (GetBOMItems enumerates the loaded inventory) can
    # see and consume the staged minerals.
    try:
        inv = cargo.station_invbroker(mch, STATION)
        cargo.hangar_inventory(mch, inv, char)
        mch.pump(1)
    except CallError as e:
        log(f"{tag}: hangar load: {str(e)[:80]}")

    # --- InstallJob ---
    assembly_line_data = [[STATION, STATION_GROUP], [], [STATION, ASSEMBLY_LINE]]
    bp_data  = [[STATION, STATION_GROUP], [[STATION, char, FLAG_HANGAR]], [bp]]
    bom_data = [[STATION, STATION_GROUP], [[STATION, char, FLAG_HANGAR]], []]
    try:
        mch.call("ramProxy", "InstallJob",
                 assembly_line_data, bp_data, bom_data,
                 FLAG_HANGAR, 1, ACTIVITY_MANUFACTURING, 0, False, "IND-2 test")
        log(f"{tag}: InstallJob call returned")
    except CallError as e:
        log(f"{tag}: InstallJob FAILED: {str(e)[:200]}")
        mch.close(); return result

    job = find_job(char, bp)
    if not job:
        log(f"{tag}: no job row created"); mch.close(); return result
    result["installed"] = True
    result["job_id"] = int(job["jobID"])
    mats_left = {t: hangar_qty(char, t) for t in MATS}
    log(f"{tag}: job {result['job_id']} installed; mats now {mats_left} (were {MATS})")

    # --- wait for production, then CompleteJob ---
    end_ft = int(job["endProductionTime"])
    if fast:
        # advance the job clock: pretend production finished
        db.execute(f"UPDATE ramJobs SET endProductionTime={_ft_now()-10} WHERE jobID={result['job_id']}")
        log(f"{tag}: --fast: advanced job clock")
    else:
        wait_s = max(0, (end_ft - _ft_now()) / 10_000_000.0) + 5
        log(f"{tag}: waiting {wait_s:.0f}s for production to finish")
        deadline = time.time() + wait_s
        while time.time() < deadline:
            mch.pump(5.0)

    loc_data = [[STATION, STATION_GROUP], [], [STATION]]
    try:
        mch.call("ramProxy", "CompleteJob", loc_data, result["job_id"], False)
        log(f"{tag}: CompleteJob call returned")
    except CallError as e:
        log(f"{tag}: CompleteJob FAILED: {str(e)[:200]}")
    mch.pump(3)
    mch.close()

    result["product_after"] = hangar_qty(char, PRODUCT)
    gained = result["product_after"] - result["product_before"]
    result["completed"] = gained > 0

    log("=== VERDICT ===")
    log(f"  InstallJob    : {'OK job '+str(result['job_id']) if result['installed'] else 'FAIL'}")
    log(f"  materials used: { {t: MATS[t]-hangar_qty(char,t) for t in MATS} }")
    log(f"  product built : {gained} Antimatter Charge S")
    log(f"  >>> MANUFACTURING: {'PASS' if (result['installed'] and result['completed']) else ('INSTALL-ONLY' if result['installed'] else 'FAIL')}")
    if result["completed"] and all(MATS[t] == hangar_qty(char, t) for t in MATS):
        log("  NOTE: materials show as NOT consumed -- DB-staged stacks aren't in the")
        log("        runtime inventory GetBOMItems() enumerates. Consumption is proven")
        log("        with reprocessed (loaded) materials in industry_chain_test.py.")
    return result


def _ft_now():
    # Windows FILETIME: 100ns ticks since 1601-01-01
    return int((time.time() + 11644473600) * 10_000_000)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="DB-advance the job clock instead of waiting")
    args = ap.parse_args()
    run(fast=args.fast)

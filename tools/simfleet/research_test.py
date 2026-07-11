#!/usr/bin/env python3
"""
IND-3: blueprint research (ME/TE) and copy validation loop.

At a research-capable station a pilot installs, on the appropriate assembly
line, a Material-Efficiency research job (activity 3), a Time-Efficiency
research job (activity 4), and a copy job (activity 5) against a BPO, then
completes each.  Server (RamProxyService::CompleteJob):
  ME research -> Blueprint::UpdateMLevel(runs)
  TE research -> Blueprint::UpdatePLevel(runs)
  copy        -> spawns `runs` BPCs (copy=1) with `copyRuns` runs each.

Verify: the BPO's mLevel/pLevel rise and a BPC appears in the hangar.
(Invention, activity 8, is not implemented server-side -- reported, not run.)

    python research_test.py            # real job waits
    python research_test.py --fast     # DB-advance each job clock
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
from machoclient import MachoClient, CallError, log
from provision import ensure_docked

STATION, SYSTEM = 60000988, 30001401     # a station with research + copy lines
STATION_GROUP = 15
PILOT = ("fleet01", "fleet", 90000004, "Keva")

BP_TYPE = 1137                            # Antimatter Charge S Blueprint (BPO)
FLAG_HANGAR = 4
LINES = {3: 281, 4: 261, 5: 251}          # ME, TE, copy assembly lines at this station
# science/industry skills that research + copy require
SKILLS = [(3380, 5), (3402, 5), (3403, 5), (3406, 5), (3409, 5), (3408, 5)]


def stage(char_id, char_name):
    HOME = pf.HOME_STATION
    pf.HOME_STATION = STATION
    db.execute(f"DELETE FROM entity WHERE ownerID={char_id} AND locationID={STATION} AND typeID={BP_TYPE}")
    ship = pf.insert_item(f"{char_name}'s Ibis", 601, char_id, STATION, FLAG_HANGAR)
    bp = pf.insert_item("", BP_TYPE, char_id, STATION, FLAG_HANGAR, singleton=1)
    db.execute(f"DELETE FROM invBlueprints WHERE itemID={bp}")
    db.execute(f"INSERT INTO invBlueprints (itemID, copy, mLevel, pLevel, runs) VALUES ({bp}, 0, 0, 0, 1000)")
    for sk, lvl in SKILLS:
        db.grant_skill(char_id, sk, lvl)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, solarSystemID={SYSTEM}, shipID={ship} WHERE characterID={char_id}")
    pf.HOME_STATION = HOME
    return ship, bp


def bp_levels(bp_id):
    r = db.query(f"SELECT mLevel, pLevel FROM invBlueprints WHERE itemID={bp_id}")
    return (int(r[0]["mLevel"]), int(r[0]["pLevel"])) if r else (None, None)


def bpc_count(char_id):
    return len(db.query(f"SELECT b.itemID FROM invBlueprints b JOIN entity e ON e.itemID=b.itemID "
                        f"WHERE e.ownerID={char_id} AND e.typeID={BP_TYPE} AND b.copy=1"))


def _ft_now():
    return int((time.time() + 11644473600) * 10_000_000)


def find_job(char_id, bp_id):
    r = db.query(f"SELECT jobID,endProductionTime FROM ramJobs WHERE installerID={char_id} "
                 f"ORDER BY jobID DESC LIMIT 1")
    return r[0] if r else None


def do_job(mch, char, bp, activity, line, runs, copy_runs, fast):
    """Install + complete one research/copy job; returns True on success."""
    assembly = [[STATION, STATION_GROUP], [], [STATION, line]]
    bp_data  = [[STATION, STATION_GROUP], [[STATION, char, FLAG_HANGAR]], [bp]]
    bom_data = [[STATION, STATION_GROUP], [[STATION, char, FLAG_HANGAR]], []]
    try:
        mch.call("ramProxy", "InstallJob", assembly, bp_data, bom_data,
                 FLAG_HANGAR, runs, activity, copy_runs, False, f"IND-3 act{activity}")
    except CallError as e:
        log(f"  activity {activity} InstallJob FAILED: {str(e)[:140]}"); return False
    job = find_job(char, bp)
    if not job:
        log(f"  activity {activity}: no job row"); return False
    jid = int(job["jobID"])
    if fast:
        db.execute(f"UPDATE ramJobs SET endProductionTime={_ft_now()-10} WHERE jobID={jid}")
    else:
        wait = max(0, (int(job["endProductionTime"]) - _ft_now()) / 10_000_000.0) + 5
        log(f"  activity {activity}: waiting {wait:.0f}s");
        end = time.time() + wait
        while time.time() < end:
            mch.pump(5.0)
    try:
        mch.call("ramProxy", "CompleteJob", [[STATION, STATION_GROUP], [], [STATION]], jid, False)
    except CallError as e:
        log(f"  activity {activity} CompleteJob FAILED: {str(e)[:140]}"); return False
    mch.pump(2)
    return True


def run(fast=False):
    acct, pw, char, tag = PILOT
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={char}")[0]["online"] not in ("0", ""):
        raise SystemExit(f"char {char} online; cannot stage")
    ship, bp = stage(char, tag)
    log(f"=== IND-3 research: {tag} BPO {bp} at station {STATION} (ME/TE/copy)")

    mch = MachoClient("127.0.0.1", 26000, acct, pw)
    mch.enter_world(char)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log(f"{tag}: could not dock"); return
    inv = cargo.station_invbroker(mch, STATION)
    cargo.hangar_inventory(mch, inv, char)

    me0, pe0 = bp_levels(bp)
    bpc0 = bpc_count(char)
    log(f"{tag}: start ME={me0} PE={pe0} BPCs={bpc0}")

    # EVEmu activity enum: ResearchTime(PE)=3, ResearchMaterial(ME)=4, Copying=5
    r = {}
    r["me"] = do_job(mch, char, bp, 4, LINES[4], 3, 0, fast)   # ME research +3
    r["te"] = do_job(mch, char, bp, 3, LINES[3], 2, 0, fast)   # TE/PE research +2
    r["copy"] = do_job(mch, char, bp, 5, LINES[5], 1, 10, fast)  # 1 BPC, 10 runs each
    me1, pe1 = bp_levels(bp)
    bpc1 = bpc_count(char)
    mch.close()

    me_ok = me1 is not None and me1 > me0
    pe_ok = pe1 is not None and pe1 > pe0
    copy_ok = bpc1 > bpc0

    log("=== VERDICT ===")
    log(f"  ME research : {me0} -> {me1}   {'PASS' if me_ok else 'FAIL'}")
    log(f"  TE research : PE {pe0} -> {pe1}   {'PASS' if pe_ok else 'FAIL'}")
    log(f"  copy (BPC)  : {bpc0} -> {bpc1} copies   {'PASS' if copy_ok else 'FAIL'}")
    log(f"  invention   : SKIP (activity 8 not implemented server-side)")
    log(f"  >>> RESEARCH+COPY: {'PASS' if (me_ok and pe_ok and copy_ok) else 'PARTIAL/FAIL'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    args = ap.parse_args()
    run(fast=args.fast)

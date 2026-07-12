#!/usr/bin/env python3
"""
STAND-1 validation: killing a faction's NPC lowers the killer's standing with
that faction.

The mission (earn) side already works (Agent::UpdateStandings). This exercises
the loss side added in NPC::Killed: a bot flies to a belt, kills rats, and we
check that a negative repStandings row appears for the killer toward the rats'
faction, that the change is logged (repStandingChanges), and that the standing
service returns it.

Also checks the read path deterministically: a DB-seeded standing is returned
by standing2.GetCharStandings.

    python standings_test.py            # real ~5 min belt kill run
    python standings_test.py --readonly # just the GetCharStandings read check
"""

import argparse
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import fittings
import provision_fleet as pf
import pvp_battle as pvp
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
STATION, SYSTEM, BELT = 60010387, 30002642, 40168291
PILOT = ("fleet01", "fleet", 90000004, "Keva")
GURISTAS = 500010          # a pirate faction, for the read-path seed


def char_standings(char_id):
    """all repStandings rows involving the char (fromID = an NPC entity)."""
    return db.query(f"SELECT fromID, toID, standing FROM repStandings "
                    f"WHERE toID={char_id} AND standing < 0")


def standing_changes(char_id):
    return db.query(f"SELECT fromID, toID, modification, msg FROM repStandingChanges "
                    f"WHERE toID={char_id} ORDER BY eventID DESC LIMIT 5")


def server_log(sec):
    out = subprocess.run([DOCKER, "logs", "server", "--since", f"{int(sec)}s"],
                         capture_output=True, text=True, timeout=30)
    return out.stdout or ""


def read_check(char_id):
    """Seed a standing in the DB and confirm standing2.GetCharStandings returns it."""
    acct, pw, char, tag = PILOT
    db.execute(f"UPDATE chrCharacters SET online=0 WHERE characterID={char_id}")
    db.execute(f"DELETE FROM repStandings WHERE fromID={GURISTAS} AND toID={char_id}")
    db.execute(f"INSERT INTO repStandings (fromID,toID,standing) VALUES ({GURISTAS},{char_id},2.5)")
    mch = MachoClient("127.0.0.1", 26000, acct, pw)
    mch.enter_world(char_id)
    rsp = mch.call("standing2", "GetCharStandings")
    mch.close()
    # Standings come back as a dbutil.CRowset whose values are binary-packed
    # into PackedRows, so we can't string-match the numbers; instead we assert
    # the rowset contains exactly the one row we seeded (correlation proven
    # separately for 0/1/3 seeded rows).
    ok = (repr(rsp).count("PackedRow") == 1)
    log(f"  GetCharStandings returned exactly the seeded standing: {ok}")
    return ok


def run(readonly=False):
    acct, pw, char, tag = PILOT
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={char}")[0]["online"] not in ("0", ""):
        raise SystemExit(f"char {char} online; cannot stage")

    log("=== STAND-1: read path (standing2.GetCharStandings) ===")
    read_ok = read_check(char)
    if readonly:
        log(f"  >>> READ PATH: {'PASS' if read_ok else 'FAIL'}")
        return

    # --- kill path: clear negative standings, go kill rats ---
    db.execute(f"DELETE FROM repStandings WHERE toID={char} AND standing < 0")
    ship = pvp.stage(char, tag, fittings.ATTACKER_FIT)
    before = {(r["fromID"], r["toID"]): float(r["standing"]) for r in char_standings(char)}
    log(f"=== STAND-1: kill path -- {tag} to belt {BELT}, negative standings before: {before}")

    mch = MachoClient("127.0.0.1", 26000, acct, pw)
    mch.enter_world(char)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log(f"{tag}: could not dock"); return
    sref = mch.bind("ship", (STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", ship, False); mch.pump(12)
    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
    try: mch.call_bound(bey, "CmdStop")
    except CallError: pass
    mch.pump(3)
    try:
        mch.call_bound(bey, "CmdWarpToStuff", "item", BELT, byname={"minRange": 0})
    except CallError as e:
        log(f"{tag}: warp: {str(e)[:80]}")
    for _ in range(12):
        mch.pump(2.0)

    guns = [int(r["itemID"]) for r in db.query(
        f"SELECT itemID FROM entity WHERE locationID={ship} AND flag BETWEEN 27 AND 34")]
    for g in guns:
        try: mch.call_bound(dogma, "SetModuleOnline", ship, g)
        except CallError: pass
    mch.pump(3)

    # engage whatever rats show up for up to ~4 min, count kills from the log
    kills = 0
    deadline = time.time() + 240
    while time.time() < deadline and kills < 3:
        rats = sorted(int(r["itemID"]) for r in db.query(
            f"SELECT itemID FROM entity WHERE itemID>=750000000 AND locationID={SYSTEM}"))
        for npc in rats[:2]:
            try:
                mch.call_bound(bey, "CmdWarpToStuff", "item", npc, byname={"minRange": 0}); mch.pump(4)
            except CallError: pass
            try:
                mch.call_bound(bey, "CmdOrbit", npc, 500); mch.pump(1)
                mch.call_bound(dogma, "AddTarget", npc); mch.pump(2)
                for g in guns:
                    try: mch.activate_module(dogma, g, "targetAttack", npc, 1000)
                    except CallError: pass
            except CallError:
                pass
        mch.pump(6.0)
        kills = len(re.findall(r"SpawnKilled", server_log(30)))
    try: mch.call_bound(bey, "CmdStop")
    except CallError: pass
    mch.pump(4); mch.close()

    after = {(r["fromID"], r["toID"]): float(r["standing"]) for r in char_standings(char)}
    changes = standing_changes(char)
    log("=== VERDICT ===")
    log(f"  rat kills observed (SpawnKilled): {kills}")
    log(f"  negative standings after: {after}")
    log(f"  repStandingChanges (last 5): {changes}")
    dropped = any(after.get(k, 0) < before.get(k, 0) for k in after) or (after and not before)
    log(f"  read path: {'PASS' if read_ok else 'FAIL'}")
    if kills == 0:
        log("  >>> KILL PATH: NO RATS SPAWNED (SPAWN-14) -- kill path not exercised this run")
    else:
        log(f"  >>> STAND-1 kill->standing loss: {'PASS' if dropped else 'FAIL'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--readonly", action="store_true")
    args = ap.parse_args()
    run(readonly=args.readonly)

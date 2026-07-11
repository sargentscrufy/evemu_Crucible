#!/usr/bin/env python3
"""
SPAWN-13 + NPC-EWAR belt probe.

SPAWN-13: belt rats spawn 10-15 km off the belt (SPAWN-12) but used to be
warped away by RoamSpawns when a pilot arrived mid bubble-recreation -- they
"scattered" thousands of km and became unlockable.  The fix keeps RoamSpawns
from using a belt as a roam source while a pilot is physically near it.

This probe warps a combat bot to the belt, waits for the spawn, then -- with
NO warp-to-npc workaround -- repeatedly tries to lock every rat directly over
a window.  Rats that stay in targeting range lock immediately; scattered rats
fail with range errors.  It also tries a warp-out to detect an NPC warp
scramble (NPC-EWAR), and scrapes the server log for the NPC-EWAR line.

Run:  python belt_scatter_probe.py
"""

import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import fittings
import pvp_battle as pvp
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
STATION, SYSTEM, BELT = 60010387, 30002642, 40168291
PILOT = ("fleet01", "fleet", 90000004, "Keva")


def server_log(seconds):
    out = subprocess.run([DOCKER, "logs", "server", "--since", f"{int(seconds)}s"],
                         capture_output=True, text=True, timeout=30)
    return (out.stdout or "") + (out.stderr or "")


_SPAWN_RE = re.compile(r"Spawning NPC type \d+ \((\d+)\)")


def live_rats():
    """rat NPC itemIDs -- prefer the DB dynamic-entity range, fall back to
    scraping the spawn log (NPCs aren't always written to `entity`)."""
    rows = db.query(
        f"SELECT itemID FROM entity WHERE itemID >= 750000000 "
        f"AND locationID = {SYSTEM}")
    ids = set(int(r["itemID"]) for r in rows)
    for m in _SPAWN_RE.finditer(server_log(180)):
        ids.add(int(m.group(1)))
    return sorted(ids)


def run():
    acct, pw, char, tag = PILOT
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={char}")[0]["online"] not in ("0", ""):
        raise SystemExit(f"char {char} online; cannot stage")
    ship = pvp.stage(char, tag, fittings.ATTACKER_FIT)
    log(f"=== SPAWN-13 probe: {tag} ship {ship} -> belt {BELT}")

    result = dict(spawned=0, direct_locks=0, lock_attempts=0, range_fails=0,
                  ewar_scram=False, ewar_log=False, samples=[])

    mch = MachoClient("127.0.0.1", 26000, acct, pw)
    mch.enter_world(char)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log(f"{tag}: could not dock"); return result
    sref = mch.bind("ship", (STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", ship, False)
    mch.pump(12)
    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(3)

    # warp to the belt (arms the spawn)
    log(f"{tag}: warping to belt {BELT}")
    try:
        mch.call_bound(bey, "CmdWarpToStuff", "item", BELT, byname={"minRange": 0})
    except CallError as e:
        log(f"{tag}: warp to belt: {str(e)[:80]}")
    for _ in range(10):
        mch.pump(2.0)

    # wait for the spawn (up to 160s -- belt spawn timer + bubble re-check).
    # keep pumping so the pilot stays registered in the belt bubble.
    rats = []
    deadline = time.time() + 160
    while time.time() < deadline:
        rats = live_rats()
        if rats:
            break
        mch.pump(4.0)
    result["spawned"] = len(rats)
    if not rats:
        log(f"{tag}: no rats spawned in 90s"); mch.close(); return result
    log(f"{tag}: {len(rats)} rats spawned: {rats[:8]}")

    # SPAWN-13 metric: over a 60s window, try to lock every rat DIRECTLY (no
    # warp-to-npc).  count direct locks vs range failures at each sample.
    window = time.time() + 60
    locked_ids = set()
    while time.time() < window:
        rats = live_rats()
        sample_lock = 0
        for npc in rats:
            result["lock_attempts"] += 1
            try:
                mch.call_bound(dogma, "AddTarget", npc)
                sample_lock += 1
                locked_ids.add(npc)
            except CallError as e:
                if "Range" in str(e) or "TooFar" in str(e):
                    result["range_fails"] += 1
        result["samples"].append((round(time.time() - (window - 60), 1),
                                  len(rats), sample_lock))
        log(f"{tag}: t+{len(result['samples'])*4}s rats={len(rats)} direct-locked={sample_lock}")
        mch.pump(4.0)
    result["direct_locks"] = len(locked_ids)

    # NPC-EWAR: try to warp out.  if a scrambling rat pinned us -> WarpScrambled
    try:
        mch.call_bound(bey, "CmdWarpToStuff", "item", STATION, byname={"minRange": 0})
        log(f"{tag}: warp-out accepted (not scrammed)")
    except CallError as e:
        if "WarpScrambled" in str(e):
            result["ewar_scram"] = True
            log(f"{tag}: warp-out BLOCKED -- NPC-EWAR scramble active")
        else:
            log(f"{tag}: warp-out: {str(e)[:80]}")
    mch.pump(5)
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(4)
    mch.close()

    txt = server_log(150)
    result["ewar_log"] = ("NPC-EWAR" in txt)

    # verdict
    log("=== VERDICT ===")
    log(f"  rats spawned           : {result['spawned']}")
    log(f"  distinct rats direct-locked: {result['direct_locks']} / {result['spawned']}")
    log(f"  lock attempts / range-fails: {result['lock_attempts']} / {result['range_fails']}")
    log(f"  NPC-EWAR scram blocked warp: {result['ewar_scram']} (log seen: {result['ewar_log']})")
    # SPAWN-13 passes if the bot could directly lock the rats (they stayed in
    # range near the belt) rather than everything failing on range.
    spawn13 = (result["direct_locks"] >= 1
               and result["direct_locks"] >= result["spawned"] * 0.5)
    log(f"  >>> SPAWN-13 (rats stay lockable): {'PASS' if spawn13 else 'FAIL'}")
    log(f"  >>> NPC-EWAR: {'OBSERVED' if (result['ewar_scram'] or result['ewar_log']) else 'not seen this spawn (no scram rat)'}")
    result["spawn13"] = "PASS" if spawn13 else "FAIL"
    return result


if __name__ == "__main__":
    run()

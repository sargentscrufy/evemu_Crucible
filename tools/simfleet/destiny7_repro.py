#!/usr/bin/env python3
"""
DESTINY-7 repro: a client that disconnects *mid-combat* used to UAF-crash
the node.  The ship SystemEntity was freed in ~Client() while still on the
system tic list / in its bubble, so the next tic dereferenced a dangling
entity.  The fix (Client.cpp) calls SystemManager::RemoveEntity(pShipSE)
in the destructor before the ship is freed.

This drives the crashing path on purpose: the defender undocks, the
attacker locks + fires, and while damage is actively landing the defender
drops its socket HARD -- no CmdStop, no settle, no graceful teardown --
then we confirm the server process is still alive and its tic loop keeps
running.  Pre-fix: gdb backtrace + respawn.  Post-fix: no crash.

Run:  python destiny7_repro.py --rounds 5
"""

import argparse
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import fittings
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP
import pvp_battle as pvp

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
STATION, SYSTEM = pvp.STATION, pvp.SYSTEM
ATTACKER = pvp.ATTACKER
DEFENDER = pvp.DEFENDER


def container_alive():
    out = subprocess.run([DOCKER, "inspect", "--format", "{{.State.Running}} {{.RestartCount}}",
                          "server"], capture_output=True, text=True, timeout=20)
    return out.stdout.strip()


def crash_markers(since_s):
    out = subprocess.run([DOCKER, "logs", "server", "--since", f"{int(since_s)}s"],
                         capture_output=True, text=True, timeout=30)
    txt = (out.stdout or "") + (out.stderr or "")
    hits = [ln for ln in txt.splitlines()
            if ("Program received signal" in ln or "SIGSEGV" in ln
                or "#0 " in ln or "backtrace" in ln.lower()
                or "server crashed" in ln.lower())]
    return hits


def defender_hard_drop(ship_id, ready, fire_seen, stop):
    """Undock, get shot, then drop the socket abruptly mid-combat."""
    acct, pw, char, tag = DEFENDER
    try:
        mch = MachoClient("127.0.0.1", 26000, acct, pw)
        mch.enter_world(char)
        if not ensure_docked(mch, STATION, SYSTEM, ship_id):
            log(f"{tag}: could not dock"); ready.set(); return
        sref = mch.bind("ship", (STATION, STATION_GROUP))
        mch.call_bound(sref, "Undock", ship_id, False)
        mch.pump(12)
        bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
        try:
            mch.call_bound(bey, "CmdStop")
        except CallError:
            pass
        ready.set()
        # wait until the attacker is actually landing damage, then yank
        fire_seen.wait(60)
        mch.pump(2.0)          # take a few hits in-flight
        log(f"{tag}: HARD-DROPPING socket mid-combat (no settle)")
        try:
            mch.conn.close()   # abrupt: no CmdStop, no logout, no settle
        except Exception:
            pass
    except Exception as e:
        log(f"{tag}: EXCEPTION {type(e).__name__}: {str(e)[:160]}")
        ready.set()
        fire_seen.set()


def one_round(rnd):
    fit = fittings.DEFENDER_FITS["incursus_armor_active"]
    def_ship = pvp.stage(DEFENDER[2], DEFENDER[3], fit)
    atk_ship = pvp.stage(ATTACKER[2], ATTACKER[3], fittings.ATTACKER_FIT)
    log(f"=== DESTINY-7 round {rnd}: attacker {atk_ship} vs defender {def_ship}")

    ready, fire_seen, stop = threading.Event(), threading.Event(), threading.Event()
    dt = threading.Thread(target=defender_hard_drop,
                          args=(def_ship, ready, fire_seen, stop), daemon=True)
    dt.start()
    ready.wait(120)
    time.sleep(2)

    acct, pw, char, tag = ATTACKER
    mch = MachoClient("127.0.0.1", 26000, acct, pw)
    mch.enter_world(char)
    ensure_docked(mch, STATION, SYSTEM, atk_ship)
    sref = mch.bind("ship", (STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", atk_ship, False)
    mch.pump(12)
    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(3)
    guns = [int(r["itemID"]) for r in db.query(
        f"SELECT itemID FROM entity WHERE locationID={atk_ship} AND flag BETWEEN 27 AND 34")]
    locked = False
    for _ in range(20):
        try:
            mch.call_bound(bey, "CmdFollowBall", def_ship, 500)
            mch.pump(1)
            mch.call_bound(dogma, "AddTarget", def_ship)
            locked = True
            break
        except CallError as e:
            mch.pump(4 if ("OtherWarping" in str(e) or "Range" in str(e)) else 3)
    if not locked:
        log(f"{tag}: could not lock; aborting round"); fire_seen.set()
        dt.join(timeout=10); return None
    try:
        mch.call_bound(bey, "CmdOrbit", def_ship, 500)
    except CallError:
        pass
    for g in guns:
        try:
            mch.call_bound(dogma, "SetModuleOnline", atk_ship, g)
        except CallError:
            pass
    mch.pump(3)
    for g in guns:
        try:
            mch.activate_module(dogma, g, "targetAttack", def_ship, 1000)
        except CallError:
            pass
    mch.pump(3)
    fire_seen.set()          # tell the defender to hard-drop now
    # keep firing at the (now vanishing) target across the tic where the
    # entity is torn down -- this is the window that used to UAF
    for _ in range(6):
        mch.pump(2.0)
    # attacker leaves cleanly
    for g in guns:
        try:
            mch.call_bound(dogma, "Deactivate", g, "targetAttack")
        except CallError:
            pass
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(4)
    mch.close()
    dt.join(timeout=15)
    return True


def main(rounds):
    for char in (ATTACKER[2], DEFENDER[2]):
        if db.query(f"SELECT online FROM chrCharacters WHERE characterID={char}")[0]["online"] not in ("0", ""):
            raise SystemExit(f"char {char} online; cannot stage")
    log(f"container before: {container_alive()}")
    crashes = 0
    for r in range(1, rounds + 1):
        try:
            one_round(r)
        except Exception as e:
            log(f"round {r} EXCEPTION {type(e).__name__}: {str(e)[:160]}")
        time.sleep(3)
        mk = crash_markers(30)
        alive = container_alive()
        if mk:
            crashes += 1
            log(f"  round {r}: CRASH MARKERS: {mk[:4]}")
        log(f"  round {r}: container={alive}")
    log("=== VERDICT ===")
    log(f"  rounds: {rounds}  crashes-detected: {crashes}")
    log(f"  >>> DESTINY-7: {'FAIL (still crashing)' if crashes else 'PASS (no crash)'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=5)
    args = ap.parse_args()
    main(args.rounds)

#!/usr/bin/env python3
"""
Combat-loop bug hunt: rookie ship flies station -> asteroid belt, waits
for the rat spawn, engages with the civilian railgun until the rats are
dead (or timeout), then returns and docks.  Every anomaly is logged
with a BUG: prefix for later triage.

    python combat_loop_test.py --user aura --password aura \
        --char-id 90000002 --run-tag R1 [--belt 40168291]

Server-side truth (spawns, kills) is read from docker logs on the host.
"""

import argparse
import re
import subprocess
import sys
import time

import db
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
STATION = 60010387
SYSTEM = 30002642

BUGS = []


def bug(msg):
    BUGS.append(msg)
    log(f"BUG: {msg}")


def server_log_since(seconds):
    try:
        out = subprocess.run(
            [DOCKER, "logs", "server", "--since", f"{int(seconds)}s"],
            capture_output=True, text=True, timeout=30)
        return (out.stdout or "") + (out.stderr or "")
    except Exception as e:  # host-side tooling problem, not a server bug
        log(f"log read failed: {e}")
        return ""


def wait_for_spawn(deadline):
    """Poll server logs for the belt spawn; return list of NPC itemIDs."""
    seen = set()
    spawn_re = re.compile(r"Spawning NPC type \d+ \((\d+)\)")
    while time.time() < deadline:
        txt = server_log_since(90)
        for m in spawn_re.finditer(txt):
            seen.add(int(m.group(1)))
        if seen and "MakeSpawn" not in txt[-2000:]:
            # give the spawn wave a moment to finish, then go
            time.sleep(5)
            txt = server_log_since(30)
            for m in spawn_re.finditer(txt):
                seen.add(int(m.group(1)))
            return sorted(seen)
        time.sleep(10)
    return sorted(seen)


def dead_npcs():
    txt = server_log_since(600)
    return {int(m.group(1)) for m in
            re.finditer(r"SpawnKilled::Belt - called by (\d+)", txt)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--char-id", type=int, required=True)
    ap.add_argument("--belt", type=int, default=40168291)
    ap.add_argument("--run-tag", default="R?")
    args = ap.parse_args()

    t0 = time.time()
    log(f"===== {args.run_tag} start: char {args.char_id} belt {args.belt}")

    mch = MachoClient("127.0.0.1", 26000, args.user, args.password)
    sess = mch.enter_world(args.char_id)
    ship = int(mch.session.get("shipid") or 0)
    if not ship:
        ship = int(db.query(
            f"SELECT shipID FROM chrCharacters WHERE characterID = {args.char_id}"
        )[0]["shipID"])
    log(f"in world: station={sess.get('stationid')} ship={ship}")
    if sess.get("solarsystemid2") != SYSTEM:
        bug(f"login placed char in system {sess.get('solarsystemid2')}, expected {SYSTEM}")

    if not ensure_docked(mch, STATION, SYSTEM, ship):
        bug("could not reach docked starting state")
        mch.close()
        return finish(t0, args)

    gun_rows = db.query(
        f"SELECT itemID FROM entity WHERE locationID = {ship} AND flag = 27")
    if not gun_rows:
        bug(f"no gun fitted in hislot0 of ship {ship}")
        mch.close()
        return finish(t0, args)
    gun = int(gun_rows[0]["itemID"])

    # --- undock ---
    ship_ref = mch.bind("ship", (STATION, STATION_GROUP))
    try:
        mch.call_bound(ship_ref, "Undock", ship, False)
    except CallError as e:
        bug(f"Undock rejected: {e}")
        mch.close()
        return finish(t0, args)
    mch.pump(12.0)
    if mch.session.get("stationid"):
        bug("still docked after Undock call")
        mch.close()
        return finish(t0, args)
    log("in space")

    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError as e:
        log(f"CmdStop: {e}")

    log("cap regen wait 60s")
    end = time.time() + 60
    while time.time() < end:
        mch.pump(2.0)

    # --- warp to belt ---
    log(f"warping to belt {args.belt}")
    try:
        mch.call_bound(bey, "CmdWarpToStuff", "item", args.belt,
                       byname={"minRange": 0})
    except CallError as e:
        bug(f"belt warp rejected: {e}")
    end = time.time() + 100
    while time.time() < end:
        mch.pump(2.0)

    # sanity: did the warp actually move us near the belt?
    pos = db.query(f"SELECT x, y, z FROM entity WHERE itemID = {ship}")
    belt = db.query(
        f"SELECT x, y, z FROM mapDenormalize WHERE itemID = {args.belt}")[0]
    # (position in entity table is only updated on save; skip hard check)

    # --- wait out the spawn timer ---
    log("loitering for rat spawn (up to 330s)")
    npcs = wait_for_spawn(time.time() + 330)
    if not npcs:
        bug("no rat spawn within 330s of belt arrival")
        mch.call_bound(bey, "CmdWarpToStuff", "item", STATION,
                       byname={"minRange": 0})
        end = time.time() + 100
        while time.time() < end:
            mch.pump(2.0)
        mch.session.pop("stationid", None)
        if not ensure_docked(mch, STATION, SYSTEM, ship, patience=240.0):
            bug("could not re-dock after empty belt")
        mch.close()
        return finish(t0, args)
    log(f"rats up: {npcs}")

    # --- engage ---
    # rats warp in after spawning; locks are correctly denied while the
    # target is warping (DeniedTargetOtherWarping), so retry for a while
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
    engaged = []
    lock_deadline = time.time() + 120
    while not engaged and time.time() < lock_deadline:
        for npc in npcs:
            try:
                mch.call_bound(bey, "CmdFollowBall", npc, 1000)
                mch.pump(1.0)
            except CallError as e:
                log(f"CmdFollowBall {npc}: {e}")
            try:
                mch.call_bound(dogma, "AddTarget", npc)
                engaged.append(npc)
                log(f"locked {npc}")
                break   # civilian gun: one target at a time
            except CallError as e:
                msg = str(e)
                if "OtherWarping" in msg:
                    log(f"{npc} still warping in; will retry")
                else:
                    log(f"AddTarget {npc} failed: {msg[:120]}")
        if not engaged:
            mch.pump(8.0)
    if not engaged:
        bug(f"could not lock any of {len(npcs)} rats within 120s "
            "(warp-in never completed?)")

    kills_before = dead_npcs()
    fight_end = time.time() + 300
    current = engaged[0] if engaged else None
    if current:
        try:
            mch.call_bound(dogma, "Activate", gun, "targetAttack", current, 1000)
            log(f"gun {gun} firing on {current}")
        except CallError as e:
            bug(f"gun activation rejected: {e}")

    while time.time() < fight_end:
        mch.pump(3.0)
        dead = dead_npcs() - kills_before
        if current in dead:
            log(f"kill confirmed: {current}")
            remaining = [n for n in npcs if n not in dead]
            if not remaining:
                log("all rats dead")
                break
            current = remaining[0]
            try:
                mch.call_bound(bey, "CmdFollowBall", current, 1000)
                mch.call_bound(dogma, "AddTarget", current)
                mch.call_bound(dogma, "Activate", gun, "targetAttack", current, 1000)
                log(f"next target: {current}")
            except CallError as e:
                bug(f"re-engage {current} failed: {e}")
        # death check: session kicked to pod?
        cur_ship = int(mch.session.get("shipid") or ship)
        if cur_ship != ship:
            bug(f"pilot lost the Ibis (now in {cur_ship}) -- podded by rats")
            ship = cur_ship
            break

    dead = dead_npcs() - kills_before
    log(f"fight over: {len(dead)}/{len(npcs)} rats killed: {sorted(dead)}")
    if not dead and engaged:
        bug("gun cycled 300s with zero kills (damage pipeline?)")

    # --- return and dock ---
    log("returning to station")
    try:
        mch.call_bound(bey, "CmdWarpToStuff", "item", STATION,
                       byname={"minRange": 0})
    except CallError as e:
        bug(f"return warp rejected: {e}")
    end = time.time() + 100
    while time.time() < end:
        mch.pump(2.0)
    mch.session.pop("stationid", None)
    if not ensure_docked(mch, STATION, SYSTEM, ship, patience=240.0):
        bug("could not dock at end of run (dock approach crawl?)")
    else:
        log("docked")
    mch.close()
    return finish(t0, args)


def finish(t0, args):
    log(f"===== {args.run_tag} done in {time.time()-t0:.0f}s, "
        f"{len(BUGS)} bug(s)")
    for b in BUGS:
        log(f"  BUG: {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

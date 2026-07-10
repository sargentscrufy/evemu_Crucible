#!/usr/bin/env python3
"""
Fleet mechanics trial: three sim pilots form a fleet, travel together,
and fight rats across three asteroid belts.

Per-belt sequence: leader fleet-warps (CmdWarpToStuff byname fleet=True)
and we OBSERVE whether members are warped by the server (expected
finding: the fleet flag is parsed and dropped -- FLEET-1); members then
warp individually as fallback so the combat validation still runs.
Members engage any rats present; findings logged as FLEET:/KINK:.

    python fleet_trio_test.py
"""

import os
import queue
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

STATION, SYSTEM = 60010387, 30002642
BELTS = [40168291, 40168296, 40168299]
PILOTS = [
    ("fleet06", "fleet", 90000006, 140000891, "Mira (Cormorant, FC)"),
    ("fleet04", "fleet", 90000004, 140000843, "Keva (Merlin)"),
    ("fleet05", "fleet", 90000005, 140000866, "Jorn (Rifter)"),
]

FINDINGS = []
fleet_q = queue.Queue()
barrier = threading.Barrier(3, timeout=600)


def finding(msg):
    FINDINGS.append(msg)
    log(f"FLEET: {msg}")


def pump_for(mch, s):
    end = time.time() + s
    while time.time() < end:
        mch.pump(2.0)


def pilot_thread(user, pw, char, ship, tag, is_leader):
    try:
        mch = MachoClient("127.0.0.1", 26000, user, pw)
        mch.enter_world(char)
        log(f"{tag}: in world")
        if not ensure_docked(mch, STATION, SYSTEM, ship):
            finding(f"{tag}: could not reach docked start")
            return

        # --- fleet formation ---
        if is_leader:
            rsp = mch.call("fleetObjectHandler", "CreateFleet")
            txt = repr(rsp)
            import re
            ids = [int(x) for x in re.findall(r"\b(\d{8,})\b", txt)]
            fleet_id = ids[0] if ids else None
            if not fleet_id:
                finding(f"CreateFleet gave no fleetID: {txt[:300]}")
                return
            log(f"{tag}: fleet {fleet_id} created")
            fref = mch.bind("fleetObjectHandler", fleet_id)
            fleet_q.put(fleet_id)
            fleet_q.put(fleet_id)
            pump_for(mch, 5)
            for _, _, mchar, _, mtag in PILOTS[1:]:
                try:
                    mch.call_bound(fref, "Invite", mchar, None, None, None)
                    log(f"{tag}: invited {mtag}")
                except CallError as e:
                    finding(f"Invite({mtag}) failed: {str(e)[:200]}")
            pump_for(mch, 10)
            try:
                comp = mch.call_bound(fref, "GetFleetComposition")
                log(f"{tag}: composition: {repr(comp)[:400]}")
            except CallError as e:
                finding(f"GetFleetComposition failed: {str(e)[:200]}")
        else:
            fleet_id = fleet_q.get(timeout=120)
            pump_for(mch, 8)   # let the invite land
            fref = mch.bind("fleetObjectHandler", fleet_id)
            try:
                mch.call_bound(fref, "AcceptInvite", None)
                log(f"{tag}: accepted invite to fleet {fleet_id}")
            except CallError as e:
                finding(f"{tag} AcceptInvite failed: {str(e)[:200]}")

        barrier.wait()

        # --- undock everyone ---
        sref = mch.bind("ship", (STATION, STATION_GROUP))
        mch.call_bound(sref, "Undock", ship, False)
        pump_for(mch, 10)
        if mch.session.get("stationid"):
            finding(f"{tag}: still docked after Undock")
            return
        bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
        try:
            mch.call_bound(bey, "CmdStop")
        except CallError:
            pass
        pump_for(mch, 45)      # cap regen + clear
        barrier.wait()

        # --- three belts ---
        for i, belt in enumerate(BELTS, 1):
            if is_leader:
                log(f"=== BELT {i}: leader fleet-warps to {belt}")
                try:
                    mch.call_bound(bey, "CmdWarpToStuff", "item", belt,
                                   byname={"minRange": 0, "fleet": True})
                except CallError as e:
                    finding(f"fleet warp to {belt} rejected: {str(e)[:200]}")
                pump_for(mch, 75)
            else:
                # wait through the leader's warp window, then check if the
                # server moved US (fleet warp propagation)
                pump_for(mch, 75)
                moved = repr(mch.session)  # session doesn't carry position
                # fall back: warp individually (documents FLEET-1 either way;
                # server logs show whether our ship warped once or twice)
                try:
                    mch.call_bound(bey, "CmdWarpToStuff", "item", belt,
                                   byname={"minRange": 0})
                    log(f"{tag}: individual warp to belt {i} issued")
                except CallError as e:
                    finding(f"{tag} individual warp {belt} failed: {str(e)[:200]}")
                pump_for(mch, 75)

            barrier.wait()

            # --- engage anything the server spawned here ---
            import subprocess, re as _re
            DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
            out = subprocess.run([DOCKER, "logs", "server", "--since", "240s"],
                                 capture_output=True, text=True, timeout=30)
            npcs = sorted(set(int(m) for m in _re.findall(
                r"Spawning NPC type \d+ \((\d+)\)", out.stdout or "")))
            if npcs:
                dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
                gun_rows = db.query(f"SELECT itemID FROM entity WHERE locationID = {ship} AND flag BETWEEN 27 AND 34")
                guns = [int(r["itemID"]) for r in gun_rows]
                locked = None
                for npc in npcs:
                    try:
                        mch.call_bound(bey, "CmdFollowBall", npc, 1000)
                        mch.pump(1.0)
                        mch.call_bound(dogma, "AddTarget", npc)
                        locked = npc
                        break
                    except CallError:
                        continue
                if locked:
                    for g in guns:
                        try:
                            mch.call_bound(dogma, "Activate", g, "targetAttack", locked, 1000)
                        except CallError as e:
                            finding(f"{tag} gun {g} activate failed: {str(e)[:150]}")
                    log(f"{tag}: engaging {locked} with {len(guns)} guns")
                    pump_for(mch, 90)
                else:
                    log(f"{tag}: no lockable rats at belt {i}")
            else:
                log(f"{tag}: no rats at belt {i} yet")
            barrier.wait()

        # --- home ---
        try:
            mch.call_bound(bey, "CmdWarpToStuff", "item", STATION,
                           byname={"minRange": 0})
        except CallError:
            pass
        pump_for(mch, 90)
        mch.session.pop("stationid", None)
        if ensure_docked(mch, STATION, SYSTEM, ship, patience=240.0):
            log(f"{tag}: home and docked")
        else:
            finding(f"{tag}: failed final dock")
        mch.close()
    except Exception as e:
        finding(f"{tag}: EXCEPTION {type(e).__name__}: {str(e)[:300]}")


def main():
    threads = []
    for i, (user, pw, char, ship, tag) in enumerate(PILOTS):
        t = threading.Thread(target=pilot_thread,
                             args=(user, pw, char, ship, tag, i == 0),
                             daemon=True)
        threads.append(t)
        t.start()
        time.sleep(15)
    for t in threads:
        t.join(timeout=1800)
    log("===== TRIO RUN COMPLETE =====")
    for f in FINDINGS:
        log(f"  FLEET: {f}")


if __name__ == "__main__":
    main()

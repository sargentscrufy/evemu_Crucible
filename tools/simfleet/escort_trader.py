#!/usr/bin/env python3
"""
M4a: escorted trading.  A hauler runs arbitrage legs while a destroyer
escort fleets up with her and shadows the route.

Mechanics:
  - hauler creates the fleet, invites the escort (all-in-world barrier
    first -- FLEET-2), then runs trader legs as fleet leader.  Her
    in-system warps carry `fleet: True`, so the SERVER warps the escort
    with her (FLEET-1).
  - gate jumps don't propagate; the escort polls the leader's system
    (coordinator knowledge) and jumps after her, then the next fleet
    warp snaps formation again.
  - on grid the escort locks + engages any NPC that appears (docker-log
    scan, same machinery as combat_loop_test).

    python escort_trader.py [--legs 2]
"""

import argparse
import os
import queue
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import cargo
import db
import trade
import travel
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

HAULER = ("fleet07", "fleet", 90000010, 140001001, "Ilsa(hauler)")
ESCORT = ("fleet03", "fleet", 90000006, 140001273, "Mira(escort)")
HOME_STATION, HOME_SYSTEM = 60003760, 30000142
DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"

fleet_q = queue.Queue()
formed = threading.Event()
done = threading.Event()


def undock(mch, station, ship):
    sref = mch.bind("ship", (station, STATION_GROUP))
    mch.call_bound(sref, "Undock", ship, False)
    mch.pump(12)
    bey = travel.bind_beyonce(mch)
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(6)
    return bey


def char_location(char_id):
    r = db.query(f"SELECT solarSystemID, stationID FROM chrCharacters"
                 f" WHERE characterID = {char_id}")
    return (int(r[0]["solarSystemID"] or 0), int(r[0]["stationID"] or 0))


def recent_npcs():
    out = subprocess.run([DOCKER, "logs", "server", "--since", "90s"],
                         capture_output=True, text=True, timeout=45)
    return sorted(set(int(m) for m in re.findall(
        r"Spawning NPC type \d+ \((\d+)\)", out.stdout or "")))


def hauler_thread(legs):
    acct, pw, char, ship, tag = HAULER
    try:
        mch = MachoClient("127.0.0.1", 26000, acct, pw)
        mch.enter_world(char)
        if not ensure_docked(mch, HOME_STATION, HOME_SYSTEM, ship):
            log(f"{tag}: no docked start")
            return
        # fleet up (escort must be in world first)
        formed.wait(timeout=180)
        rsp = mch.call("fleetObjectHandler", "CreateFleet")
        ids = [int(x) for x in re.findall(r"\b(\d{8,})\b", repr(rsp))]
        fref = mch.bind("fleetObjectHandler", ids[0])
        mch.pump(3)
        mch.call_bound(fref, "Invite", ESCORT[2], None, None, None)
        fleet_q.put(ids[0])
        log(f"{tag}: fleet {ids[0]}, escort invited")
        mch.pump(10)

        # monkey-patch travel's station warp to carry the fleet flag so
        # the server drags the escort along on every in-system warp
        orig_call = mch.call_bound
        def fleet_call(ref, method, *a, byname=None, **kw):
            if method == "CmdWarpToStuff" and byname and "minRange" in byname:
                byname = dict(byname)
                byname["fleet"] = True
            return orig_call(ref, method, *a, byname=byname, **kw)
        mch.call_bound = fleet_call

        cap = cargo.cargo_capacity(ship)
        for leg in range(1, legs + 1):
            here = int(mch.session.get("stationid") or HOME_STATION)
            budget = (trade.db_wallet(char) or 0) * 0.8
            plan = trade.find_best_route_db(char, here, cargo_m3=cap,
                                            budget=budget, min_margin=0.05,
                                            max_jumps=6)
            if plan is None:
                log(f"{tag}: leg {leg}: no route; ending")
                break
            log(f"{tag}: leg {leg}: {plan!r}")
            delta = trade.execute_leg(mch, char, ship, plan)
            log(f"{tag}: leg {leg} realized {delta}")
        mch.close()
    except Exception as e:
        log(f"{tag}: EXCEPTION {type(e).__name__}: {str(e)[:250]}")
    finally:
        done.set()


def escort_thread():
    acct, pw, char, ship, tag = ESCORT
    try:
        mch = MachoClient("127.0.0.1", 26000, acct, pw)
        mch.enter_world(char)
        if not ensure_docked(mch, HOME_STATION, HOME_SYSTEM, ship):
            log(f"{tag}: no docked start")
            return
        formed.set()
        fleet_id = fleet_q.get(timeout=180)
        mch.pump(3)
        fref = mch.bind("fleetObjectHandler", fleet_id)
        mch.call_bound(fref, "AcceptInvite", None)
        mch.pump(5)
        log(f"{tag}: in fleet {fleet_id} "
            f"(session fleetid={mch.session.get('fleetid')})")

        # undock and shadow the hauler until the run ends
        bey = undock(mch, HOME_STATION, ship)
        guns = [int(r["itemID"]) for r in db.query(
            f"SELECT itemID FROM entity WHERE locationID = {ship}"
            f" AND flag BETWEEN 27 AND 34")]
        engaged = set()
        while not done.is_set():
            mch.pump(15)
            my_sys = int(mch.session.get("solarsystemid2") or 0)
            h_sys, h_station = char_location(HAULER[2])
            if h_sys and h_sys != my_sys:
                log(f"{tag}: hauler moved to {h_sys}; following")
                travel.goto_system(mch, ship, h_sys)
                bey = travel.bind_beyonce(mch)
                continue
            # engage anything that spawned on/near our grid
            for npc in recent_npcs():
                if npc in engaged:
                    continue
                try:
                    mch.call_bound(bey, "CmdFollowBall", npc, 1000)
                    mch.pump(1)
                    dogma = mch.bind("dogmaIM", (my_sys, SOLARSYSTEM_GROUP))
                    mch.call_bound(dogma, "AddTarget", npc)
                    for g in guns:
                        try:
                            mch.call_bound(dogma, "Activate", g,
                                           "targetAttack", npc, 1000)
                        except CallError:
                            pass
                    engaged.add(npc)
                    log(f"{tag}: engaging hostile {npc}")
                    mch.pump(30)
                except CallError:
                    engaged.add(npc)   # not lockable (other grid); skip
        # home
        log(f"{tag}: run over; returning home")
        travel.goto_station(mch, ship, HOME_STATION)
        mch.close()
    except Exception as e:
        log(f"{tag}: EXCEPTION {type(e).__name__}: {str(e)[:250]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legs", type=int, default=1)
    args = ap.parse_args()
    te = threading.Thread(target=escort_thread, daemon=True)
    th = threading.Thread(target=hauler_thread, args=(args.legs,),
                          daemon=True)
    te.start()
    time.sleep(10)
    th.start()
    th.join(timeout=3600)
    done.set()
    te.join(timeout=600)
    log("ESCORTED RUN COMPLETE")


if __name__ == "__main__":
    main()

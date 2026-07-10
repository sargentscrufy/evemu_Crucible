#!/usr/bin/env python3
"""
SPAWN-11 verification, round 2.  Sera starts docked at Iyen-Oursta III
(60010387).  Undock, warp to belt 40168291, LOITER until the server
actually spawns a wave (belt timers are 30..900s), then dock and wait
out the 5-min unwatched grace.  Verdict comes from server logs.

    python spawn11_probe2.py
"""

import re
import subprocess
import sys
import time

import travel
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, STATION_GROUP

CHAR, SHIP = 90000014, 140001104
STATION, SYSTEM, BELT = 60010387, 30002642, 40168291
DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"


def spawns_since(seconds):
    out = subprocess.run([DOCKER, "logs", "server", "--since", f"{seconds}s"],
                         capture_output=True, text=True, timeout=45)
    return re.findall(r"Spawning NPC type \d+ \((\d+)\)", out.stdout or "")


def main():
    mch = MachoClient("127.0.0.1", 26000, "qatest", "fleet")
    mch.enter_world(CHAR)
    if not ensure_docked(mch, STATION, SYSTEM, SHIP):
        log("SPAWN11-2: cannot reach docked start")
        return 1

    sref = mch.bind("ship", (STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", SHIP, False)
    mch.pump(12)
    bey = travel.bind_beyonce(mch)
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(8)

    mch.call_bound(bey, "CmdWarpToStuff", "item", BELT, byname={"minRange": 0})
    mch.pump(50)
    log("at belt; loitering until the wave spawns (up to 16 min)...")
    t0 = time.time()
    spawned = False
    while time.time() - t0 < 960:
        mch.pump(20)
        if spawns_since(25):
            spawned = True
            break
    log(f"spawned={spawned} after {time.time()-t0:.0f}s; retreating")
    mch.call_bound(bey, "CmdWarpToStuff", "item", STATION,
                   byname={"minRange": 0})
    mch.pump(70)
    mch.session.pop("stationid", None)
    if not ensure_docked(mch, STATION, SYSTEM, SHIP, patience=200.0):
        log("SPAWN11-2: failed to dock after loiter")
        return 1
    if not spawned:
        log("SPAWN11-2: no wave spawned during loiter; inconclusive")
        mch.close()
        return 1
    log(f"docked {time.strftime('%H:%M:%S')}; waiting 7 min unwatched...")
    end = time.time() + 420
    while time.time() < end:
        mch.pump(5)
    mch.close()
    log("SPAWN11-2 COMPLETE -- check logs for 'despawning stale wave'")
    return 0


if __name__ == "__main__":
    sys.exit(main())

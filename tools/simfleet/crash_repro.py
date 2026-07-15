"""
crash_repro.py -- replay the two live crashes from 2026-07-15 (TARG-3 hunt)

Crash 1: player targets the mission silo -> server segfault
         (root cause by inspection: ISE entities had no TargetManager and
          StartTargeting derefs the target's manager.  TARG-3 fixed; this
          verifies.)
Crash 2: after reconnection, warping out to the deadspace pocket -> segfault
         (no backtrace survived the container recreate; this hunts it)

Flow: accept mission -> undock -> agent-warp to gate room -> TARGET THE GATE
(same ISE class as the silo, same code path) -> restart the server container
(simulated crash recovery) -> reconnect -> try every pocket-warp path a
player has -> report survival per step.
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "smoke-bot"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "simchars"))
import db
import fittings
import smartbomb_test as sb
import provision_fleet as pf
from machoclient import MachoClient, CallError, log as mlog
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP
from netclient import ConnectionClosed

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
PORT = int(os.environ.get("EVE_PORT", "26010"))
ACCT, PW, CHAR, TAG = "qatest", "fleet", 90000014, "Sera"
STATION, SYSTEM, AGENT = 60003754, 30000144, 3016815

def log(m): print(f"[repro] {m}", flush=True)

def srv(sec):
    out = subprocess.run([DOCKER, "logs", "server", "--since", f"{int(sec)}s"],
                         capture_output=True, text=True, timeout=45)
    return (out.stdout or "") + (out.stderr or "")

def server_healthy():
    out = subprocess.run([DOCKER, "inspect", "server", "--format",
                          "{{.State.Health.Status}}"],
                         capture_output=True, text=True).stdout
    return "healthy" in out

def check_crash(step, window=25):
    time.sleep(2)
    tail = srv(window)
    if "SIGSEGV" in tail:
        log(f"*** SERVER CRASHED at step: {step} ***")
        for ln in tail.splitlines():
            if re.match(r"#\d+ ", ln) or "SIGSEGV" in ln:
                log("    " + ln[:160])
        return True
    log(f"  [OK] server survived: {step}")
    return False

def connect():
    m = MachoClient("127.0.0.1", PORT, ACCT, PW)
    m.enter_world(CHAR)
    return m

def main():
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={CHAR}")[0]["online"] not in ("0", "", 0):
        raise SystemExit(f"{TAG} flagged online; cannot stage")
    db.execute(f"DELETE FROM agtOffers WHERE characterID={CHAR}")

    ship = sb.stage_hi(CHAR, TAG, fittings.CORMORANT, [fittings.RAILGUN_150] * 7)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, locationID={STATION}, "
               f"solarSystemID={SYSTEM}, shipID={ship} WHERE characterID={CHAR}")

    log("=== phase 1: crash-1 repro (target ISE scenery) ===")
    mch = connect()
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log("could not stage docked"); return

    ref = mch.bind("agentMgr", AGENT)
    rsp = mch.call_bound(ref, "DoAction", None)
    if "(11," in repr(rsp):
        mch.call_bound(ref, "DoAction", 11); mch.pump(2)
        ref = mch.bind("agentMgr", AGENT)
        mch.call_bound(ref, "DoAction", None)
    t0 = time.time()
    mch.call_bound(ref, "DoAction", 3)   # accept
    mch.pump(4)
    tail = srv(int(time.time() - t0 + 3))
    g = re.search(r"RegisterMissionGate - gate (\d+)", tail)
    gateID = int(g.group(1)) if g else 0
    log(f"mission accepted, gate {gateID}")

    sref = mch.bind("ship", (STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", ship, False)
    mch.pump(10)
    log("settling out of warp-safe state (~24s)")
    mch.pump(24)
    aref = mch.bind("agentMgr", AGENT)
    try:
        mch.call_bound(aref, "WarpToLocation", 0, 0, 0.0, False, AGENT)
    except CallError as e:
        log(f"agent warp: {str(e)[:80]}")
    log("agent-warping to gate room (~55s)")
    mch.pump(55)

    if gateID:
        dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
        try:
            mch.call_bound(dogma, "AddTarget", gateID)
            log("  AddTarget(gate) accepted -- lock resolving")
        except (CallError, ConnectionClosed) as e:
            log(f"  AddTarget(gate): {type(e).__name__} {str(e)[:90]}")
        mch.pump(8)
    if check_crash("targeting ISE scenery (crash-1 path)"):
        return

    log("=== phase 2: simulated crash recovery (server restart) ===")
    try: mch.close()
    except Exception: pass
    db.execute(f"UPDATE chrCharacters SET online=0 WHERE characterID={CHAR}")
    subprocess.run([DOCKER, "compose", "restart", "server"],
                   cwd=r"G:\Claude\Evemu", capture_output=True, text=True)
    for _ in range(60):
        if server_healthy(): break
        time.sleep(5)
    log("server healthy; reconnecting")
    time.sleep(4)

    mch = connect()
    mch.pump(4)
    # char may load in space (was in space at 'crash'); if docked, undock
    sref = mch.bind("ship", (STATION, STATION_GROUP))
    try:
        mch.call_bound(sref, "Undock", ship, False)
        mch.pump(10)
    except (CallError, ConnectionClosed) as e:
        log(f"undock after reconnect: {type(e).__name__} {str(e)[:70]}")
    if check_crash("reconnect + undock"):
        return

    log("=== phase 3: post-reconnect pocket warps ===")
    # (a) agent-menu warp with the site registry wiped
    try:
        aref = mch.bind("agentMgr", AGENT)
        mch.call_bound(aref, "WarpToLocation", 0, 0, 0.0, False, AGENT)
        log("  (a) WarpToLocation accepted")
    except (CallError, ConnectionClosed) as e:
        log(f"  (a) WarpToLocation: {type(e).__name__} {str(e)[:90]}")
    mch.pump(8)
    if check_crash("(a) agent warp, empty registry"): return

    # (b) WarpToStuff on the persisted P&P mission bookmark
    rows = db.query(f"SELECT bookmarkID FROM bookmarks WHERE ownerID={CHAR} "
                    f"AND memo LIKE '%Mission Site' ORDER BY bookmarkID DESC LIMIT 1")
    if rows:
        bmID = int(rows[0]["bookmarkID"])
        try:
            bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
            mch.call_bound(bey, "CmdWarpToStuff", "bookmark", bmID)
            log(f"  (b) CmdWarpToStuff(bookmark {bmID}) accepted")
        except (CallError, ConnectionClosed) as e:
            log(f"  (b) CmdWarpToStuff: {type(e).__name__} {str(e)[:90]}")
        mch.pump(45)
        if check_crash("(b) warp to persisted P&P bookmark", window=50): return
    else:
        log("  (b) no P&P mission bookmark; skipped")

    # (c) activate the STALE pre-restart gate (purged from DB at boot)
    if gateID:
        try:
            mch.call("keeper", "ActivateAccelerationGate", gateID)
            log(f"  (c) ActivateAccelerationGate({gateID}) accepted?!")
        except (CallError, ConnectionClosed) as e:
            log(f"  (c) stale gate: {type(e).__name__} {str(e)[:90]}")
        mch.pump(8)
        if check_crash("(c) stale purged gate activation"): return

    log("=== all phases survived ===")
    try:
        aref = mch.bind("agentMgr", AGENT)
        mch.call_bound(aref, "DoAction", 11)
    except Exception: pass
    try: mch.close()
    except Exception: pass

if __name__ == "__main__":
    main()

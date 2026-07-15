#!/usr/bin/env python3
"""
SECMISSION-M3 full-chain QA: encounter mission against the retail site shape.

Sera (qatest) at the Perimeter L1 security agent:
  1. request mission   -> briefing rsp must carry the custom PROSE string
  2. accept            -> server log must show leader + henchmen + transport
                          spawn and RegisterMissionDrop
  3. undock + agentMgr.WarpToLocation -> server warps her to HER site
                          (leader taunt arrives as a notify)
  4. smartbomb the transport until it dies
  5. VERIFY: InjectMissionLoot fired and the goal item row sits inside the
     jettisoned objective container dropped beside the transport (M3i)

    python secmission_qa.py
"""

import math
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))
sys.path.insert(0, HERE)

import db
import fittings
import provision_fleet as pf
import smartbomb_test as sb
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
PORT = int(os.environ.get("EVE_PORT", "26010"))
ACCT, PW, CHAR, TAG = "qatest", "fleet", 90000014, "Sera"
STATION, SYSTEM, AGENT = 60003754, 30000144, 3016815
CORMORANT, RAIL, AMMO, SMARTBOMB, SSE = fittings.CORMORANT, fittings.RAILGUN_150, fittings.ANTIMATTER_S, sb.SMARTBOMB, 377

PASS = []
def check(name, ok, detail=""):
    PASS.append(bool(ok))
    log(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")

def srv(sec):
    out = subprocess.run([DOCKER, "logs", "server", "--since", f"{int(sec)}s"],
                         capture_output=True, text=True, timeout=45)
    return (out.stdout or "") + (out.stderr or "")

def run():
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={CHAR}")[0]["online"] not in ("0", "", 0):
        raise SystemExit(f"{TAG} online; cannot stage")
    db.execute(f"DELETE FROM agtOffers WHERE characterID={CHAR}")

    ship = sb.stage_hi(CHAR, TAG, CORMORANT, [RAIL] * 7 + [SMARTBOMB])
    pf.insert_item("", SSE, CHAR, ship, 19)
    pf.insert_item("", AMMO, CHAR, ship, 5, qty=4000, singleton=0)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, locationID={STATION}, "
               f"solarSystemID={SYSTEM}, shipID={ship} WHERE characterID={CHAR}")

    mch = MachoClient("127.0.0.1", PORT, ACCT, PW)
    mch.enter_world(CHAR)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log("could not stage docked"); return False

    # --- 1. request: briefing must be PROSE ---------------------------
    ref = mch.bind("agentMgr", AGENT)
    rsp = mch.call_bound(ref, "DoAction", None)
    if "(11," in repr(rsp):
        mch.call_bound(ref, "DoAction", 11); mch.pump(2)
        ref = mch.bind("agentMgr", AGENT)
        mch.call_bound(ref, "DoAction", None)
    mch.call_bound(ref, "DoAction", 2)
    brief = repr(mch.call_bound(ref, "GetMissionBriefingInfo"))
    prose = any(t in brief for t in ("Guristas", "freighter", "hauler", "deadspace",
                                     "snatch team", "press gang", "operative"))
    check("briefing carries custom prose string", prose, f"({brief[brief.find('Mission Briefing'):brief.find('Mission Briefing')+120]!r})")

    # --- 2. accept: retail site shape ----------------------------------
    t0 = time.time()
    mch.call_bound(ref, "DoAction", 3)
    mch.pump(4)
    tail = srv(int(time.time() - t0 + 3))
    m = re.search(r"SpawnMissionSite - '([^']+)' .*gate (\d+) -> pocket \(leader \+ (\d+) henchmen \+ transport (\d+)", tail)
    check("two-room site spawned (gate -> pocket)", bool(m), (m.group(0)[:120] if m else "no spawn log"))
    drop = re.search(r"RegisterMissionDrop - npc (\d+) will drop (\d+) x(\d+)", tail)
    check("transport tagged for mission drop", bool(drop), (drop.group(0) if drop else ""))
    gatereg = re.search(r"RegisterMissionGate - gate (\d+) -> pocket", tail)
    check("gate registered to pocket", bool(gatereg), (gatereg.group(0)[:80] if gatereg else ""))
    if not (m and drop and gatereg):
        mch.close(); return False
    transport = int(m.group(4))
    gate = int(gatereg.group(1))
    # M3i: pocket + site coords for the approach leg (gate drops us 30km short)
    pock = re.search(r"RegisterMissionGate - gate \d+ -> pocket \((-?\d+), (-?\d+), (-?\d+)\)", tail)
    site = re.search(r"SpawnMissionSite - .* in \d+ at \((-?\d+), (-?\d+), (-?\d+)\)", tail)
    pocket_xyz = [float(pock.group(i)) for i in (1, 2, 3)] if pock else None
    site_xyz = [float(site.group(i)) for i in (1, 2, 3)] if site else None

    # --- 3. undock + WarpToLocation ------------------------------------
    # docked: online + instant antimatter load into all 7 rails
    st_dogma = mch.bind("dogmaIM", (STATION, STATION_GROUP))
    guns = [int(r["itemID"]) for r in db.query(
        f"SELECT itemID FROM entity WHERE locationID={ship} AND flag BETWEEN 27 AND 33 "
        f"AND typeID={RAIL}")]
    for g in guns:
        try: mch.call_bound(st_dogma, "SetModuleOnline", ship, g)
        except CallError: pass
    sref = mch.bind("ship", (STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", ship, False)
    mch.pump(10)
    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
    mods = [int(r["itemID"]) for r in db.query(
        f"SELECT itemID FROM entity WHERE locationID={ship} AND flag BETWEEN 27 AND 34")]
    sb_id = [int(r["itemID"]) for r in db.query(
        f"SELECT itemID FROM entity WHERE locationID={ship} AND typeID={SMARTBOMB}")][0]
    for m in mods:
        for _ in range(2):
            try: mch.activate_module(dogma, m, "online", None, 0)
            except CallError: pass
            mch.pump(1.0)
    log("settling out of warp-safe state (~24s)")
    mch.pump(24)

    def load_guns():
        fresh = db.query(f"SELECT itemID FROM entity WHERE locationID={ship} "
                         f"AND flag=5 AND typeID={AMMO} LIMIT 1")
        if not fresh:
            log("no ammo left in cargo"); return
        try:
            mch.call_bound(dogma, "LoadAmmoToModules", ship, guns, AMMO,
                           int(fresh[0]["itemID"]), ship)
            mch.pump(12)   # reload timer
        except CallError as e:
            log(f"load: {str(e)[:60]}")
    load_guns()   # proven combat-loop pattern: in-space load into empty guns

    note_idx = len(mch.notifications)
    aref = mch.bind("agentMgr", AGENT)
    try:
        mch.call_bound(aref, "WarpToLocation", 0, 0, 0.0, False, AGENT)
        check("agentMgr.WarpToLocation accepted", True)
    except CallError as e:
        check("agentMgr.WarpToLocation accepted", False, str(e)[:100])
    mch.pump(50)   # warp + land at room 1 (the gate; hostile-free)

    # --- 3b. activate the acceleration gate -> pocket -------------------
    note_idx = len(mch.notifications)
    try:
        mch.call("keeper", "ActivateAccelerationGate", gate)
        check("ActivateAccelerationGate accepted", True)
    except CallError as e:
        check("ActivateAccelerationGate accepted", False, str(e)[:100])
    mch.pump(40)   # gate warp into the pocket
    notes = "\n".join(repr(n) for n in mch.notifications[note_idx:])
    taunt = any(t in notes for t in ("Pity you", "Cargo is cargo", "you are alone",
                                     "pays well", "Fresh meat", "Cruisers on the field",
                                     "Fourteen head"))
    check("leader taunt on gate activation", taunt)

    # --- 3c. close to engagement range -----------------------------------
    # M3h drops the pilot 30km short of the pocket (retail standoff).  the
    # rails are deep in falloff there (live QA: ~97% grazes, hauler
    # effectively unkillable) -- drive the warp line toward the pocket
    # before opening up, like a human pilot would.
    if pocket_xyz and site_xyz:
        dx = [pocket_xyz[i] - site_xyz[i] for i in range(3)]
        n = math.sqrt(sum(c * c for c in dx)) or 1.0
        hd = [c / n for c in dx]
        try:
            mch.call_bound(bey, "CmdGotoDirection", hd[0], hd[1], hd[2])
            mch.call_bound(bey, "CmdSetSpeedFraction", 1.0)
            log("closing ~25km to engagement range (~140s; expect escort aggro)")
            mch.pump(140)
            mch.call_bound(bey, "CmdSetSpeedFraction", 0.0)
        except CallError as e:
            log(f"approach: {str(e)[:60]}")

    # --- 4. kill the transport ------------------------------------------
    # lock it and open up with all seven rails; keep the bomb pulsing too.
    # warp duration varies with site distance -- retry the lock until the
    # ship has actually dropped out of warp
    locked = False
    for _ in range(8):
        try:
            mch.call_bound(dogma, "AddTarget", transport)
            locked = True
            break
        except CallError:
            mch.pump(6)
    if not locked:
        log("lock never succeeded")
    mch.pump(6)
    for g in guns:
        try: mch.activate_module(dogma, g, "targetAttack", transport, 1000)
        except CallError: pass
    killed = False
    t1 = time.time()
    # 140 iterations: a 3-henchman spawn + the 30km approach leg can push a
    # clean kill past the old 90 (live: hauler died ~30s after cutoff)
    for i in range(140):
        try: mch.activate_module(dogma, sb_id, "empWave", None, 1000)
        except CallError: pass
        # turrets run dry after ~30 volleys of their 40-round clips --
        # reload only when actually empty (reloading loaded guns throws)
        if i in (30, 62):
            load_guns()
        for g in guns:
            try: mch.activate_module(dogma, g, "targetAttack", transport, 1000)
            except CallError: pass
        mch.pump(4)
        if re.search(r"InjectMissionLoot - dropped", srv(12)):
            killed = True
            break
        if not db.query(f"SELECT itemID FROM entity WHERE itemID={ship}"):
            log("QA ship destroyed by escort"); break
    tail = srv(int(time.time() - t1 + 5))
    # M3i: the objective now drops in its own jettisoned container (retail
    # shape), not inside the wreck
    inj = re.search(r"InjectMissionLoot - dropped (\d+) x(\d+) in container (\d+)", tail)
    check("transport killed + InjectMissionLoot fired", bool(inj), (inj.group(0) if inj else ""))

    # --- 5. goal item is inside the objective container -------------------
    if inj:
        can = int(inj.group(3))
        rows = db.query(f"SELECT typeID, quantity FROM entity WHERE locationID={can}")
        goal = [r for r in rows if int(r["typeID"]) == int(inj.group(1))]
        check("goal item row inside objective container", bool(goal), f"({rows})")

    # cleanup: quit mission, log off
    try:
        aref = mch.bind("agentMgr", AGENT)
        mch.call_bound(aref, "DoAction", 11)
    except CallError: pass
    mch.pump(3)
    try: mch.close()
    except Exception: pass
    db.execute(f"UPDATE chrCharacters SET online=0 WHERE characterID={CHAR}")

    log(f"=== {sum(PASS)}/{len(PASS)} checks passed ===")
    return all(PASS)

if __name__ == "__main__":
    sys.exit(0 if run() else 1)

#!/usr/bin/env python3
"""
Smart bomb test.  A smartbomb is an area-of-effect weapon: on each cycle it
damages every ship within its EMP field range of the firing ship, with no
lock.  Baseline (before SMARTBOMB-1) the module cycled but dealt zero damage
(empty case in ProcessActiveCycle).  This drives it live:

  attacker (Merlin + 'Pike' Small EMP Smartbomb, range 3600 m) approaches a
  defender Merlin to inside 3600 m, onlines + activates the smartbomb (no
  target), and we read the defender's DAMAGE log.  Damage landing => PASS.

Run:  python smartbomb_test.py
"""

import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import provision_fleet as pf
import pvp_battle as pvp
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
STATION, SYSTEM = pvp.STATION, pvp.SYSTEM
ATTACKER = pvp.ATTACKER          # Mira 90000006
DEFENDER = pvp.DEFENDER          # Keva 90000004
MERLIN = 603
SMARTBOMB = 23864                # 'Pike' Small EMP Smartbomb I (range 3600 m, 140 EM)


def stage_hi(char_id, char_name, hull, hi_mods=()):
    HOME = pf.HOME_STATION
    pf.HOME_STATION = STATION
    hull_name = db.query(f"SELECT typeName FROM invTypes WHERE typeID={hull}")[0]["typeName"]
    ship = pf.insert_item(f"{char_name}'s {hull_name}", hull, char_id, STATION, 4)
    fitted = [hull]
    for i, tid in enumerate(hi_mods):
        pf.insert_item("", int(tid), char_id, ship, 27 + i)   # hi slots 27..33
        fitted.append(int(tid))
    for skill_tid, lvl in db.skill_closure(fitted):
        db.grant_skill(char_id, skill_tid, lvl)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, solarSystemID={SYSTEM}, "
               f"shipID={ship} WHERE characterID={char_id}")
    pf.HOME_STATION = HOME
    return ship


def docker_dmg(sec):
    out = subprocess.run([DOCKER, "logs", "server", "--since", f"{int(sec)}s"],
                         capture_output=True, text=True, timeout=45)
    return out.stdout or ""


def defender_thread(ship_id, ready, stop):
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
        while not stop.is_set():
            mch.pump(2.0)
        try:
            mch.call_bound(bey, "CmdStop")
        except CallError:
            pass
        mch.pump(4)
        mch.close()
    except Exception as e:
        log(f"{tag}: EXCEPTION {type(e).__name__}: {str(e)[:160]}")
        ready.set()


def run(window=60.0):
    for c in (ATTACKER[2], DEFENDER[2]):
        if db.query(f"SELECT online FROM chrCharacters WHERE characterID={c}")[0]["online"] not in ("0", ""):
            raise SystemExit(f"char {c} online; cannot stage")
    def_ship = stage_hi(DEFENDER[2], DEFENDER[3], MERLIN)               # bare target
    atk_ship = stage_hi(ATTACKER[2], ATTACKER[3], MERLIN, [SMARTBOMB])  # smartbomb
    log(f"=== SMARTBOMB test: attacker {atk_ship} (smartbomb) vs defender {def_ship}")

    ready, stop = threading.Event(), threading.Event()
    dt = threading.Thread(target=defender_thread, args=(def_ship, ready, stop), daemon=True)
    dt.start()
    ready.wait(120)
    time.sleep(2)

    result = dict(damaged=False, final_s=1.0, final_a=1.0, final_h=1.0, log_hit=False)
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
    sb = db.query(f"SELECT itemID FROM entity WHERE locationID={atk_ship} AND flag BETWEEN 27 AND 33")
    sb_id = int(sb[0]["itemID"]) if sb else None

    # online it (online-effect path -- SetModuleOnline is a bot no-op, COMP-H)
    for _ in range(2):
        try:
            mch.call_bound(dogma, "SetModuleOnline", atk_ship, sb_id)
        except CallError:
            pass
        try:
            mch.activate_module(dogma, sb_id, "online", None, 0)
        except CallError as e:
            log(f"{tag}: online-effect: {str(e)[:80]}")
        mch.pump(5)

    # settle: the undock push leaves the ship in a warp/align state for ~20 s;
    # empWave is not warp-safe so it would be denied (DeniedActivateInWarp).
    # let it settle, then close to within field range (3600 m) sublight.
    log(f"{tag}: settling out of post-undock warp state")
    for _ in range(13):
        mch.pump(2.0)
    try:
        mch.call_bound(bey, "CmdFollowBall", def_ship, 500)
    except CallError:
        pass
    mch.pump(6.0)

    log(f"{tag}: activating smartbomb {sb_id} (continuous pulse)")
    t0 = time.time()
    end = t0 + window
    dmg_re = re.compile(rf"\({def_ship}\): DamageUpdate - S:(\d+\.\d+) A:(\d+\.\d+) H:(\d+\.\d+)")
    try:
        mch.activate_module(dogma, sb_id, "empWave", None, 1000)   # keep pulsing
    except CallError as e:
        log(f"{tag}: smartbomb activate: {str(e)[:100]}")
    while time.time() < end:
        mch.pump(6.0)
        # keep in range + re-pulse if it stopped (no target => shouldn't, but safe)
        try:
            mch.call_bound(bey, "CmdFollowBall", def_ship, 500)
        except CallError:
            pass
        txt = docker_dmg(20)
        hits = dmg_re.findall(txt)
        if "empWave" in txt or "Smartbomb" in txt or "EMP Smartbomb" in txt:
            result["log_hit"] = True
        if hits:
            s, a, h = hits[-1]
            result["final_s"], result["final_a"], result["final_h"] = float(s), float(a), float(h)
            if float(s) < 1.0 or float(a) < 1.0 or float(h) < 1.0:
                result["damaged"] = True
                break

    try:
        mch.call_bound(dogma, "Deactivate", sb_id, __import__("evemarshal").WStr("empWave"))
    except CallError:
        pass
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(4)
    mch.close()
    stop.set()
    dt.join(timeout=15)

    log("=== VERDICT ===")
    log(f"  defender tank after burst: S:{result['final_s']:.2f} A:{result['final_a']:.2f} H:{result['final_h']:.2f}")
    log(f"  >>> SMARTBOMB deals AoE damage: {'PASS' if result['damaged'] else 'FAIL (no damage)'}")
    return result


if __name__ == "__main__":
    run()

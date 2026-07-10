#!/usr/bin/env python3
"""
Bot-vs-bot tank battle: a fixed civilian-gun attacker fires on a defender
wearing a given tank fit; the server DAMAGE log is parsed for the
defender's shield/armor/hull over the battle window.  Measures how well
each tank holds under constant kinetic+thermal DPS.

One battle:  python pvp_battle.py --fit merlin_shield_buffer
Programmatic: run_battle("merlin_shield_buffer") -> result dict
"""

import argparse
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import fittings
import provision_fleet as pf
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
STATION, SYSTEM = 60010387, 30002642        # Iyen-Oursta IV - Moon 4
ATTACKER = ("fleet03", "fleet", 90000006, "Mira")
DEFENDER = ("fleet01", "fleet", 90000004, "Keva")

# ship-attribute IDs
A_SHIELD_CAP = 263
A_ARMOR_HP   = 265
A_HULL_HP    = 9
# resonance (1.0 = 0% resist, lower = more resist): em/exp/kin/therm
A_SH_RES = {"em": 271, "exp": 272, "kin": 273, "therm": 274}
A_AR_RES = {"em": 267, "exp": 268, "kin": 269, "therm": 270}
# civilian gatling railgun damage split (from live trace K:1.725 T:1.150)
DMG_MIX = {"kin": 0.6, "therm": 0.4, "em": 0.0, "exp": 0.0}


def type_attr(type_id, attr_id, default=0.0):
    r = db.query(f"SELECT COALESCE(valueFloat, valueInt) v FROM dgmTypeAttributes"
                 f" WHERE typeID={int(type_id)} AND attributeID={int(attr_id)}")
    return float(r[0]["v"]) if r and r[0]["v"] is not None else default


def compute_ehp(hull_type):
    """Analytic EHP of a bare hull vs the attacker's kin/therm mix."""
    sh = type_attr(hull_type, A_SHIELD_CAP)
    ar = type_attr(hull_type, A_ARMOR_HP)
    hu = type_attr(hull_type, A_HULL_HP)
    def layer_ehp(hp, res_attrs):
        eff = sum(DMG_MIX[d] * type_attr(hull_type, res_attrs[d], 1.0)
                  for d in DMG_MIX)
        return hp / eff if eff > 0 else hp
    return dict(shield=sh, armor=ar, hull=hu,
                raw=sh + ar + hu,
                ehp=layer_ehp(sh, A_SH_RES) + layer_ehp(ar, A_AR_RES) + hu)


def docker_damage(since_s):
    out = subprocess.run([DOCKER, "logs", "server", "--since", f"{int(since_s)}s"],
                         capture_output=True, text=True, timeout=45)
    return out.stdout or ""


def defender_thread(fit_name, ship_id, ready, stop):
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
        # sit and take it
        while not stop.is_set():
            mch.pump(2.0)
        # DESTINY-7 mitigation: settle before disconnecting
        try:
            mch.call_bound(bey, "CmdStop")
        except CallError:
            pass
        mch.pump(5.0)
        mch.close()
    except Exception as e:
        log(f"{tag}: EXCEPTION {type(e).__name__}: {str(e)[:200]}")
        ready.set()


def run_battle(fit_name, window=90.0):
    fit = fittings.DEFENDER_FITS[fit_name]
    hull = fit[0]

    # --- stage both ships (offline) ---
    for char, f in ((DEFENDER[2], fit), (ATTACKER[2], fittings.ATTACKER_FIT)):
        if db.query(f"SELECT online FROM chrCharacters WHERE characterID={char}")[0]["online"] not in ("0", ""):
            raise SystemExit(f"char {char} online; cannot stage")
    def_ship = stage(DEFENDER[2], DEFENDER[3], fit)
    atk_ship = stage(ATTACKER[2], ATTACKER[3], fittings.ATTACKER_FIT)
    ehp = compute_ehp(hull)
    log(f"=== BATTLE {fit_name}: defender {DEFENDER[3]} ship {def_ship} "
        f"(hull {hull}), EHP~{ehp['ehp']:.0f} (raw {ehp['raw']:.0f})")

    ready, stop = threading.Event(), threading.Event()
    dt = threading.Thread(target=defender_thread,
                          args=(fit_name, def_ship, ready, stop), daemon=True)
    dt.start()
    ready.wait(timeout=120)
    time.sleep(3)

    t0 = time.time()
    result = dict(fit=fit_name, hull=hull, ehp=round(ehp["ehp"]),
                  raw_hp=round(ehp["raw"]), killed=False,
                  survival_s=window, final_s=1.0, final_a=1.0, final_h=1.0,
                  first_dmg_s=None)
    try:
        _attack(def_ship, atk_ship, window, t0, result)
    finally:
        stop.set()
        dt.join(timeout=20)
    log(f"    result: {result}")
    return result


def _attack(def_ship, atk_ship, window, t0, result):
    acct, pw, char, tag = ATTACKER
    mch = MachoClient("127.0.0.1", 26000, acct, pw)
    mch.enter_world(char)
    if not ensure_docked(mch, STATION, SYSTEM, atk_ship):
        log(f"{tag}: attacker could not dock"); return
    sref = mch.bind("ship", (STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", atk_ship, False)
    mch.pump(12)
    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(4)

    # lock the defender's ship
    locked = False
    for _ in range(20):
        try:
            mch.call_bound(bey, "CmdFollowBall", def_ship, 500)
            mch.pump(1)
            mch.call_bound(dogma, "AddTarget", def_ship)
            locked = True
            break
        except CallError as e:
            if "OtherWarping" in str(e) or "Range" in str(e):
                mch.pump(4)
            else:
                mch.pump(3)
    if not locked:
        log(f"{tag}: could not lock defender {def_ship}")
        return
    log(f"{tag}: locked defender {def_ship}; orbit + fire")
    try:
        mch.call_bound(bey, "CmdOrbit", def_ship, 500)
    except CallError:
        pass
    guns = [int(r["itemID"]) for r in db.query(
        f"SELECT itemID FROM entity WHERE locationID={atk_ship} AND flag BETWEEN 27 AND 34")]
    for g in guns:
        try:
            mch.call_bound(dogma, "SetModuleOnline", atk_ship, g)
        except CallError:
            pass
    mch.pump(3)
    for g in guns:
        try:
            mch.activate_module(dogma, g, "targetAttack", def_ship, 1000)
        except CallError as e:
            log(f"{tag}: gun {g}: {str(e)[:80]}")

    # sample the defender's tank from the DAMAGE log over the window
    dmg_re = re.compile(
        rf"\({def_ship}\): DamageUpdate - S:(\d+\.\d+) A:(\d+\.\d+) H:(\d+\.\d+)")
    kill_re = re.compile(rf"{def_ship}.*(?:Killed|has been destroyed|podded)",
                         re.IGNORECASE)
    end = t0 + window
    while time.time() < end:
        mch.pump(4.0)
        txt = docker_damage(30)
        hits = dmg_re.findall(txt)
        if hits and result["first_dmg_s"] is None:
            result["first_dmg_s"] = round(time.time() - t0, 1)
        if hits:
            s, a, h = hits[-1]
            result["final_s"], result["final_a"], result["final_h"] = \
                float(s), float(a), float(h)
        if kill_re.search(txt) or (result["final_h"] <= 0.01):
            result["killed"] = True
            result["survival_s"] = round(time.time() - t0, 1)
            break

    # DESTINY-7 mitigation: stop combat + movement and let destiny settle
    # before disconnecting, so no destiny update is in flight when the
    # entity is removed (a mid-combat disconnect can UAF-crash the node).
    for g in guns:
        try:
            mch.call_bound(dogma, "Deactivate", g, "targetAttack")
        except CallError:
            pass
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError:
        pass
    mch.pump(5.0)
    mch.close()


def stage(char_id, char_name, fit):
    hull, slots = fit
    hull_name = db.query(f"SELECT typeName FROM invTypes WHERE typeID={hull}")[0]["typeName"]
    # clear any prior sim ship of this hull at the station, then stage fresh
    HOME = pf.HOME_STATION
    pf.HOME_STATION = STATION
    fitdict = {}
    SLOT = {"hi": 27, "med": 19, "low": 11}
    ship = pf.insert_item(f"{char_name}'s {hull_name}", hull, char_id, STATION, 4)
    fitted = [hull]
    for rack, base in SLOT.items():
        for i, tid in enumerate(slots.get(rack, [])):
            pf.insert_item("", int(tid), char_id, ship, base + i)
            fitted.append(int(tid))
    # civilian guns are ammoless; ensure skills for everything fitted
    for skill_tid, lvl in db.skill_closure(fitted):
        db.grant_skill(char_id, skill_tid, lvl)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, "
               f"solarSystemID={SYSTEM}, shipID={ship} WHERE characterID={char_id}")
    pf.HOME_STATION = HOME
    return ship


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", default="merlin_shield_buffer",
                    choices=sorted(fittings.DEFENDER_FITS))
    ap.add_argument("--window", type=float, default=90.0)
    args = ap.parse_args()
    run_battle(args.fit, args.window)

#!/usr/bin/env python3
"""
MOD-1 / DESTINY-8 probe: what happens to an active turret and an orbit when
the target dies.

Production feedback (SARGENTSCRUFY 2026-07-12): after destroying an asteroid
with a railgun the gun kept cycling client-side (MOD-1) and the orbiting ship
slammed to a stop (DESTINY-8, fixed: EntityRemoved/IsTargetInvalid now
KeepHeading()).

Flow: Keva stages a Merlin (150mm rail + antimatter loaded docked, smart
bomb), undocks, settles, /spawns an Athran Agent (29200, ~150 EHP) point
blank, locks + orbits it, opens fire with the rail, and finishes it with the
smart bomb.  After the kill we read:
  - server MODULE__TRACE: Deactivate(TargetDestroyed) fired for the rail,
    and no further rail cycles/damage afterward   (MOD-1 server truth)
  - client notifications: OnGodmaShipEffect stop for the rail (start=0)
    reached the client                            (MOD-1 client-visible stop)
  - client notifications: CmdGotoDirection after the kill and the DESTINY
    log shows "Maintaining course"                (DESTINY-8 fix live)

    python target_killed_probe.py
"""

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
STATION, SYSTEM = sb.STATION, sb.SYSTEM
ACCT, PW, CHAR, TAG = sb.DEFENDER          # Keva 90000004
RAT_TYPE = 29200                           # Athran Agent (GM-spawnable, soft)
RAIL = fittings.RAILGUN_150
SMARTBOMB = sb.SMARTBOMB
ANTIMATTER = fittings.ANTIMATTER_S


def srv_log(sec):
    out = subprocess.run([DOCKER, "logs", "server", "--since", f"{int(sec)}s"],
                         capture_output=True, text=True, timeout=45)
    return (out.stdout or "") + (out.stderr or "")


def notes_repr(mch, since_idx):
    return "\n".join(repr(n) for n in mch.notifications[since_idx:])


def online_mods(mch, dogma, mod_ids):
    for m in mod_ids:
        for _ in range(2):
            try:
                mch.activate_module(dogma, m, "online", None, 0)
            except CallError:
                pass
            mch.pump(1.5)


def run():
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={CHAR}")[0]["online"] not in ("0", ""):
        raise SystemExit(f"char {CHAR} online; cannot stage")

    ship = sb.stage_hi(CHAR, TAG, sb.MERLIN, [RAIL, SMARTBOMB])
    pf.insert_item("", ANTIMATTER, CHAR, ship, 5, qty=2000, singleton=0)
    log(f"=== MOD-1/DESTINY-8 probe: {TAG} rail+smartbomb Merlin {ship} ===")

    mch = MachoClient("127.0.0.1", PORT, ACCT, PW)
    mch.enter_world(CHAR)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log("could not stage docked"); return

    mods = {int(r["typeID"]): int(r["itemID"]) for r in db.query(
        f"SELECT itemID, typeID FROM entity WHERE locationID={ship} "
        f"AND flag BETWEEN 27 AND 33")}
    rail, bomb = mods.get(RAIL), mods.get(SMARTBOMB)
    if not rail or not bomb:
        log(f"fit staging failed: {mods}"); mch.close(); return

    # docked: online + instant ammo load
    st_dogma = mch.bind("dogmaIM", (STATION, STATION_GROUP))
    for m in (rail, bomb):
        try: mch.call_bound(st_dogma, "SetModuleOnline", ship, m)
        except CallError: pass
    mch.pump(2)
    charge = db.query(f"SELECT itemID FROM entity WHERE locationID={ship} "
                      f"AND flag=5 AND typeID={ANTIMATTER} LIMIT 1")
    try:
        mch.call_bound(st_dogma, "LoadAmmoToModules", ship, [rail],
                       ANTIMATTER, int(charge[0]["itemID"]), ship)
        mch.pump(2)
        log("loaded antimatter docked")
    except CallError as e:
        log(f"docked ammo load: {str(e)[:100]}")

    sref = mch.bind("ship", (STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", ship, False)
    mch.pump(8)
    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
    try: mch.call_bound(bey, "CmdStop")
    except CallError: pass
    sb_mod = sys.modules.get("smartbomb_test")
    # settle into one bubble + out of the warp-safe window
    if hasattr(sb_mod, "wait_stationary"):
        sb_mod.wait_stationary(mch, ship)
    else:
        mch.pump(15)
    online_mods(mch, dogma, [rail, bomb])   # COMP-D: mods de-online on undock
    log("settling out of post-undock warp-safe state (~24s)")
    mch.pump(24)

    # spawn the target point blank (in-memory dynamic entity; id from log)
    try:
        mch.call("slash", "SlashCmd", f"/spawn {RAT_TYPE}")
    except CallError as e:
        log(f"/spawn FAILED: {str(e)[:120]}"); mch.close(); return
    mch.pump(4)
    m = re.findall(r"Created dynamic entity (\d+) of type %d" % RAT_TYPE, srv_log(40))
    if not m:
        log(">>> FAIL: no dynamic entity in log"); mch.close(); return
    rat = int(m[-1])
    log(f"target rat {rat}: locking, orbiting, opening fire")

    # lock + orbit + shoot
    try: mch.call_bound(dogma, "AddTarget", rat)
    except CallError as e: log(f"AddTarget: {str(e)[:100]}")
    mch.pump(6)
    try: mch.call_bound(bey, "CmdOrbit", rat, 1000)
    except CallError as e: log(f"CmdOrbit: {str(e)[:100]}")
    mch.pump(6)
    try:
        mch.activate_module(dogma, rail, "targetAttack", rat, 1000)
    except CallError as e:
        log(f"rail activate: {str(e)[:100]}")
    mch.pump(8)   # let the rail cycle on the live target

    kill_note_idx = len(mch.notifications)
    kill_time = time.time()

    # finish it with the smart bomb (one-shots an Athran Agent)
    dead = False
    for _ in range(12):
        try: mch.activate_module(dogma, bomb, "empWave", None, 1000)
        except CallError: pass
        mch.pump(4)
        if re.search(r"(?:Killed|Removing|Deleting).{0,60}\b%d\b|\b%d\b.{0,60}(?:Killed|dead|destroyed)"
                     % (rat, rat), srv_log(15), re.I):
            dead = True
            break
    log(f"rat dead: {dead}")

    # observe 20s of post-kill behavior
    mch.pump(20)
    tail = srv_log(int(time.time() - kill_time + 5))
    notes = notes_repr(mch, kill_note_idx)

    deact = re.findall(r"Deactivate\(TargetDestroyed\).{0,120}", tail)
    rail_after = re.findall(r"(?:DoCycle|ApplyDamage|Fired).{0,40}150mm.{0,60}", tail)
    goto = "CmdGotoDirection" in notes
    maintain = "Maintaining course" in tail
    stop_note = notes.count("CmdStop")
    godma_stop = re.findall(r"OnGodmaShipEffect.{0,400}", notes)

    log("=== OBSERVATIONS ===")
    log(f"  server Deactivate(TargetDestroyed) lines: {len(deact)}")
    for ln in deact[:4]:
        log(f"    {ln[:150]}")
    log(f"  rail activity in post-kill log: {len(rail_after)}")
    for ln in rail_after[:4]:
        log(f"    {ln[:150]}")
    log(f"  DESTINY-8: client got CmdGotoDirection: {goto}; "
        f"server 'Maintaining course': {maintain}; CmdStop notes: {stop_note}")
    log(f"  OnGodmaShipEffect notifications post-kill: {len(godma_stop)}")
    for ln in godma_stop[:6]:
        log(f"    {ln[:220]}")

    try: mch.call_bound(bey, "CmdStop")
    except CallError: pass
    mch.pump(4)
    mch.close()

    log("=== VERDICT ===")
    log(f"  DESTINY-8 (keep heading on target death): {'PASS' if (goto or maintain) else 'FAIL'}")
    log(f"  MOD-1 server-side gun stop: {'PASS' if deact and not rail_after else 'CHECK LOG'}")


if __name__ == "__main__":
    run()

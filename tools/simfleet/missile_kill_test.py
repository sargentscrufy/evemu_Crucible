#!/usr/bin/env python3
"""
Missile combat validation harness (CAMPAIGN tooling).

Validates the full player missile-combat loop end to end on the EVEmu
Crucible server: a missile-frigate pilot flies station -> asteroid belt,
waits for a rat spawn, locks a rat, onlines her launcher, loads missiles,
and fires; we confirm from server-side ground truth (docker logs) that the
missiles deal damage and/or score a kill.  Reports MISSILE-KILL PASS/FAIL.

    python missile_kill_test.py                     # defaults below
    python missile_kill_test.py --skip-provision    # fly only (already staged)
    python missile_kill_test.py --launcher "Standard Missile Launcher I" \
        --ammo "Caldari Navy Scourge Light Missile"

Pilot / fit (defaults):
    Ilsa Vayne  (account fleet07 / pw "fleet", charID 90000010)
    Kestrel (typeID 602) + 1x Light Missile Launcher I in a hi slot
    + 1000x Scourge Light Missile (kinetic) in cargo (flag 5),
    relocated + homed at Iyen-Oursta (station 60010387, system 30002642).

Launcher choice vs the task note: the task suggested "Standard Missile
Launcher I", but the ammo it specified is a *Light* missile (Scourge Light
Missile).  A launcher only accepts charges of its chargeGroup, so a Light
Missile Launcher I is the charge-compatible pairing that guarantees
LoadAmmoToModules succeeds.  Both --launcher and --ammo are overridable if
the runner wants to force the Standard launcher + a matching Standard
missile instead.

Missile protocol (verified against src/eve-server, do NOT guess):
  * ONLINE  -- dogmaIM.SetModuleOnline(shipID, launcherID).  Modules
               de-online when the ship enters space (COMP-D), so a launcher
               must be re-onlined before it will fire.
  * LOAD    -- dogmaIM.LoadAmmoToModules(shipID, [launcherIDs], chargeTypeID,
               chargeItemID, shipID)  (same shape as turret ammo; see
               combat_loop_test.py + component_qa.py).  Loading a charge IN
               SPACE starts a ~5-10s reload timer and m_chargeLoaded only
               flips true when it completes, so we pump ~13s before firing or
               the launcher errors "doesn't seem to be loaded".
  * FIRE    -- dogmaIM.Activate(launcherID, WStr("useMissiles"), targetID, N)
               via mch.activate_module(...).  For missile launchers the
               activation effect is "useMissiles" (EVEEffectID::useMissiles
               = 101, "use charge's default effectID" -- EVE_Effects.h:41;
               ActiveModule.cpp:1245 dispatches missile fire on it).  The
               effect name MUST be a WStr (COMP-C) or Activate silently
               no-ops -- activate_module wraps it for us.
  WARNING (component_qa): firing "useMissiles" with a NULL target segfaults
  the server (Missile.cpp null-target deref).  This harness only fires after
  a target is locked, so it never hits that path -- but never call it
  target-less.

Kill / damage ground truth (docker logs, read-only):
  * kill   -- "SpawnKilled::Belt - called by <ratID>" (dead rat's own itemID;
              NPC.cpp:305 -> SpawnMgr.cpp:304).
  * damage -- "<name>(<ratID>): DamageUpdate - S:.. A:.. H:.." on the rat
              (SystemEntity.cpp:188).

NOTE (item cache): staging inserts NEW rows into the entity table; a running
server will not see them until item caches reload.  If this run stages fresh
items it prints a RESTART warning and exits; restart the server, then re-run
(staging is idempotent and will be skipped).
"""

import argparse
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))
sys.path.insert(0, HERE)  # provision_fleet.insert_item lives here

import db                                                       # noqa: E402
from machoclient import MachoClient, CallError, log             # noqa: E402
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP  # noqa: E402
import provision_fleet as pf                                    # noqa: E402

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"

STATION = 60010387          # Iyen-Oursta (ratting ground, NOT the Jita home)
SYSTEM = 30002642
BELT = 40168291
FLAG_HISLOT0 = 27           # first hi/launcher slot
FLAG_CARGO = 5

BUGS = []


def bug(msg):
    BUGS.append(msg)
    log(f"BUG: {msg}")


# --------------------------------------------------------------- log reads
def server_log_since(seconds):
    try:
        out = subprocess.run(
            [DOCKER, "logs", "server", "--since", f"{int(seconds)}s"],
            capture_output=True, text=True, timeout=30)
        return (out.stdout or "") + (out.stderr or "")
    except Exception as e:
        log(f"log read failed: {e}")
        return ""


def live_npcs_in_system(system_id):
    rows = db.query(
        f"SELECT itemID FROM entity WHERE itemID >= 750000000"
        f" AND locationID = {int(system_id)}")
    return sorted(int(r["itemID"]) for r in rows)


def wait_for_spawn(deadline, system_id):
    spawn_re = re.compile(r"Spawning NPC type \d+ \((\d+)\)")
    seen = set()
    while time.time() < deadline:
        live = live_npcs_in_system(system_id)
        if live:
            return live
        txt = server_log_since(90)
        for m in spawn_re.finditer(txt):
            seen.add(int(m.group(1)))
        if seen and "MakeSpawn" not in txt[-2000:]:
            time.sleep(5)
            for m in spawn_re.finditer(server_log_since(30)):
                seen.add(int(m.group(1)))
            return sorted(seen)
        time.sleep(10)
    return sorted(seen)


def dead_npcs():
    txt = server_log_since(900)
    return {int(m.group(1)) for m in
            re.finditer(r"SpawnKilled::Belt - called by (\d+)", txt)}


def damaged_npcs(seconds=900):
    txt = server_log_since(seconds)
    return {int(m.group(1)) for m in
            re.finditer(r"\((\d+)\): DamageUpdate", txt)}


# ------------------------------------------------------------- provisioning
def char_online(char_id):
    rows = db.query("SELECT online FROM chrCharacters WHERE characterID = "
                    f"{int(char_id)}")
    return bool(rows and rows[0]["online"] not in ("0", ""))


def provision_missile_pilot(char_id, char_name, hull_name, launcher_name,
                            ammo_name, ammo_qty):
    """Stage a missile frigate for the pilot at Iyen-Oursta, offline.
    Returns True iff freshly staged this run (caller restarts + re-runs)."""
    if char_online(char_id):
        raise SystemExit(f"char {char_id} is online; log out before staging "
                         "(server caches items/skills)")
    hull_tid = int(db.type_id(hull_name))
    launcher_tid = int(db.type_id(launcher_name))
    ammo_tid = int(db.type_id(ammo_name))

    existing = db.query(
        f"SELECT itemID FROM entity WHERE ownerID = {char_id} AND "
        f"typeID = {hull_tid} AND locationID = {STATION} AND flag = 4")
    if existing:
        ship = int(existing[0]["itemID"])
        db.execute(f"UPDATE chrCharacters SET stationID = {STATION}, "
                   f"solarSystemID = {SYSTEM}, shipID = {ship} "
                   f"WHERE characterID = {char_id}")
        db.execute(f"UPDATE entity SET locationID = {STATION}, flag = 4 "
                   f"WHERE itemID = {char_id}")
        log(f"{char_name}: {hull_name} {ship} already staged at Iyen-Oursta")
        return False

    db.execute(f"UPDATE chrCharacters SET stationID = {STATION}, "
               f"solarSystemID = {SYSTEM} WHERE characterID = {char_id}")
    db.execute(f"UPDATE entity SET locationID = {STATION}, flag = 4 "
               f"WHERE itemID = {char_id}")

    ship = pf.insert_item(f"{char_name}'s {hull_name}", hull_tid, char_id,
                          STATION, 4)
    # one launcher in the first hi slot, ammo stack in cargo
    pf.insert_item("", launcher_tid, char_id, ship, FLAG_HISLOT0)
    pf.insert_item("", ammo_tid, char_id, ship, FLAG_CARGO, qty=ammo_qty)

    fitted_types = [hull_tid, launcher_tid, ammo_tid]
    for skill_tid, level in db.skill_closure(fitted_types):
        db.grant_skill(char_id, skill_tid, level)
    db.execute(f"UPDATE chrCharacters SET shipID = {ship} "
               f"WHERE characterID = {char_id}")

    log(f"{char_name}: staged {hull_name} {ship} + {launcher_name} + "
        f"{ammo_qty}x {ammo_name} + skills at Iyen-Oursta")
    return True


# --------------------------------------------------------------- main flow
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=26000)
    ap.add_argument("--user", default="fleet07")
    ap.add_argument("--password", default="fleet")
    ap.add_argument("--char-id", type=int, default=90000010)  # Ilsa Vayne
    ap.add_argument("--char-name", default="Ilsa Vayne")
    ap.add_argument("--hull", default="Kestrel")
    ap.add_argument("--launcher", default="Light Missile Launcher I")
    ap.add_argument("--ammo", default="Scourge Light Missile")
    ap.add_argument("--ammo-qty", type=int, default=1000)
    ap.add_argument("--belt", type=int, default=BELT)
    ap.add_argument("--run-tag", default="MISSILE1")
    ap.add_argument("--skip-provision", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    log(f"===== {args.run_tag} start: {args.char_name} ({args.char_id}) "
        f"{args.hull} + {args.launcher} + {args.ammo}")

    # ---- offline provisioning phase ----
    if not args.skip_provision:
        fresh = provision_missile_pilot(args.char_id, args.char_name,
                                        args.hull, args.launcher, args.ammo,
                                        args.ammo_qty)
        if fresh:
            log("!! Freshly staged items this run.  A running server will "
                "not see them until item caches reload.  RESTART the server, "
                "then re-run this script (staging will be skipped).")
            return finish(t0, args, verdict="STAGED-RESTART-NEEDED")

    # ---- online flight phase ----
    mch = MachoClient(args.host, args.port, args.user, args.password)
    sess = mch.enter_world(args.char_id)
    ship = int(mch.session.get("shipid") or 0)
    if not ship:
        ship = int(db.query(
            f"SELECT shipID FROM chrCharacters WHERE characterID = "
            f"{args.char_id}")[0]["shipID"])
    log(f"in world: station={sess.get('stationid')} system="
        f"{sess.get('solarsystemid2')} ship={ship}")
    if sess.get("solarsystemid2") != SYSTEM:
        bug(f"login placed pilot in system {sess.get('solarsystemid2')}, "
            f"expected {SYSTEM} (Iyen-Oursta) -- staging/relocate not applied?")

    if not ensure_docked(mch, STATION, SYSTEM, ship):
        bug("could not reach docked starting state")
        mch.close()
        return finish(t0, args, verdict="FAIL")

    # find the fitted launcher (hi slots 27-33) and the ammo stack in cargo
    launcher_tid = int(db.type_id(args.launcher))
    ammo_tid = int(db.type_id(args.ammo))
    lnch_rows = db.query(
        f"SELECT itemID FROM entity WHERE locationID = {ship} "
        f"AND typeID = {launcher_tid} AND flag BETWEEN 27 AND 33")
    if not lnch_rows:
        bug(f"no {args.launcher} fitted on ship {ship}")
        mch.close()
        return finish(t0, args, verdict="FAIL")
    launchers = [int(r["itemID"]) for r in lnch_rows]
    log(f"launcher(s): {launchers}")

    # --- undock ---
    ship_ref = mch.bind("ship", (STATION, STATION_GROUP))
    try:
        mch.call_bound(ship_ref, "Undock", ship, False)
    except CallError as e:
        bug(f"Undock rejected: {e}")
        mch.close()
        return finish(t0, args, verdict="FAIL")
    mch.pump(12.0)
    if mch.session.get("stationid"):
        bug("still docked after Undock call")
        mch.close()
        return finish(t0, args, verdict="FAIL")
    log("in space")

    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
    try:
        mch.call_bound(bey, "CmdStop")
    except CallError as e:
        log(f"CmdStop: {e}")

    log("cap/settle wait 30s")
    end = time.time() + 30
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

    # --- wait out the spawn timer ---
    log("loitering for rat spawn (up to 600s)")
    npcs = wait_for_spawn(time.time() + 600, SYSTEM)
    if not npcs:
        bug("no rat spawn within 600s of belt arrival")
        return recover_and_finish(mch, ship, t0, args, verdict="FAIL")
    log(f"rats up: {npcs}")

    # --- close range: warp straight to a rat (SPAWN-13 scatter) ---
    for npc in npcs[:3]:
        try:
            mch.call_bound(bey, "CmdWarpToStuff", "item", npc,
                           byname={"minRange": 0})
            log(f"warping to rat {npc} to close missile range")
            end = time.time() + 45
            while time.time() < end:
                mch.pump(2.0)
            break
        except CallError as e:
            log(f"warp-to-rat {npc}: {str(e)[:100]}")

    # --- lock a target ---
    target = None
    lock_deadline = time.time() + 120
    while target is None and time.time() < lock_deadline:
        for npc in npcs:
            try:
                mch.call_bound(bey, "CmdFollowBall", npc, 1000)
                mch.pump(1.0)
            except CallError as e:
                log(f"CmdFollowBall {npc}: {e}")
            try:
                mch.call_bound(dogma, "AddTarget", npc)
                target = npc
                log(f"locked {npc}")
                break
            except CallError as e:
                msg = str(e)
                if "OtherWarping" in msg:
                    log(f"{npc} still warping in; retry")
                else:
                    log(f"AddTarget {npc} failed: {msg[:120]}")
        if target is None:
            mch.pump(8.0)
    if target is None:
        bug("could not lock any rat within 120s")
        return recover_and_finish(mch, ship, t0, args, verdict="FAIL")

    # --- online launcher (COMP-D: modules de-online on undock) ---
    for lnch in launchers:
        try:
            mch.call_bound(dogma, "SetModuleOnline", ship, lnch)
        except CallError as e:
            log(f"online launcher {lnch}: {e}")
    mch.pump(4.0)

    # --- load missiles, then wait out the in-space reload timer ---
    ammo_rows = db.query(
        f"SELECT itemID FROM entity WHERE locationID = {ship} "
        f"AND typeID = {ammo_tid} AND flag = {FLAG_CARGO} LIMIT 1")
    if not ammo_rows:
        bug(f"no {args.ammo} in cargo of ship {ship}")
        return recover_and_finish(mch, ship, t0, args, verdict="FAIL")
    ammo_item = int(ammo_rows[0]["itemID"])
    try:
        mch.call_bound(dogma, "LoadAmmoToModules", ship, launchers,
                       ammo_tid, ammo_item, ship)
        log(f"loading {args.ammo} ({ammo_tid}) into {len(launchers)} "
            "launcher(s); waiting ~13s reload timer")
        mch.pump(13.0)
    except CallError as e:
        bug(f"LoadAmmoToModules rejected (charge/launcher group mismatch?): {e}")
        return recover_and_finish(mch, ship, t0, args, verdict="FAIL")

    # --- orbit to hold range and fire ---
    try:
        mch.call_bound(bey, "CmdOrbit", target, 5000)
        log(f"orbiting {target} at 5km")
    except CallError as e:
        log(f"CmdOrbit {target}: {e}")

    kills_before = dead_npcs()
    dmg_before = damaged_npcs()
    fired = 0
    for lnch in launchers:
        try:
            # NEVER target-less: null target segfaults the server (Missile.cpp)
            mch.activate_module(dogma, lnch, "useMissiles", target, 1000)
            fired += 1
        except CallError as e:
            bug(f"launcher {lnch} activation rejected: {e}")
    log(f"{fired}/{len(launchers)} launcher(s) firing on {target}")
    if fired == 0:
        return recover_and_finish(mch, ship, t0, args, verdict="FAIL")

    # --- watch for damage / kills ---
    fight_end = time.time() + 180
    first_damage = None
    current = target
    while time.time() < fight_end:
        mch.pump(3.0)
        new_dmg = damaged_npcs() - dmg_before
        rat_dmg = new_dmg & set(npcs)
        if rat_dmg and first_damage is None:
            first_damage = sorted(rat_dmg)
            log(f"missile damage confirmed on rats: {first_damage}")
        killed_now = (dead_npcs() - kills_before) & set(npcs)
        if current in killed_now:
            log(f"KILL confirmed: {current}")
            remaining = [n for n in npcs if n not in killed_now]
            if not remaining:
                break
            current = remaining[0]
            try:
                mch.call_bound(bey, "CmdFollowBall", current, 1000)
                mch.call_bound(dogma, "AddTarget", current)
                mch.pump(2.0)
                for lnch in launchers:
                    try:
                        mch.activate_module(dogma, lnch, "useMissiles",
                                            current, 1000)
                    except CallError:
                        pass
                log(f"next target: {current}")
            except CallError as e:
                log(f"re-engage {current}: {e}")
        # podded?
        cur_ship = int(mch.session.get("shipid") or ship)
        if cur_ship != ship:
            bug(f"pilot lost the hull (now in {cur_ship}) -- podded by rats")
            ship = cur_ship
            break

    killed = sorted((dead_npcs() - kills_before) & set(npcs))
    damaged = sorted((damaged_npcs() - dmg_before) & set(npcs))
    if killed:
        verdict = "PASS"
        log(f"MISSILE-KILL PASS: rats killed {killed} (damage on {damaged})")
    elif damaged or first_damage:
        verdict = "PARTIAL"
        log(f"MISSILE-KILL PARTIAL: missiles dealt damage to "
            f"{damaged or first_damage} but no kill within 180s")
    else:
        verdict = "FAIL"
        bug("no missile damage or kill observed within 180s")

    return recover_and_finish(mch, ship, t0, args, verdict=verdict)


def recover_and_finish(mch, ship, t0, args, verdict):
    log("returning to station")
    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    try:
        mch.call_bound(bey, "CmdWarpToStuff", "item", STATION,
                       byname={"minRange": 0})
    except CallError as e:
        log(f"return warp: {e}")
    end = time.time() + 100
    while time.time() < end:
        mch.pump(2.0)
    mch.session.pop("stationid", None)
    if not ensure_docked(mch, STATION, SYSTEM, ship, patience=240.0):
        bug("could not dock at end of run")
    cur_ship = int(mch.session.get("shipid") or ship)
    if cur_ship != ship:
        bug(f"pilot lost the hull (now in {cur_ship}) -- podded")
    mch.close()
    return finish(t0, args, verdict=verdict)


def finish(t0, args, verdict="?"):
    log(f"===== {args.run_tag} MISSILE-KILL {verdict} in "
        f"{time.time()-t0:.0f}s, {len(BUGS)} bug(s)")
    for b in BUGS:
        log(f"  BUG: {b}")
    return 0 if verdict in ("PASS", "STAGED-RESTART-NEEDED") else 1


if __name__ == "__main__":
    sys.exit(main())

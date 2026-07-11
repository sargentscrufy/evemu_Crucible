#!/usr/bin/env python3
"""
Drone combat validation harness (CAMPAIGN tooling).

Validates the full player drone-combat loop end to end on the EVEmu
Crucible server: a drone-boat pilot flies station -> asteroid belt, waits
for a rat spawn, launches her combat drones, orders them to engage, and we
confirm from server-side ground truth (docker logs) that the drones deal
damage and/or score a kill.  Reports DRONE-KILL PASS/FAIL with evidence.

    python drone_kill_test.py                       # defaults below
    python drone_kill_test.py --skip-provision      # fly only (already staged)
    python drone_kill_test.py --hull Tristan --drone "Warrior I"

Pilot / fit (defaults):
    Dax Herron  (account fleet06 / pw "fleet", charID 90000009)
    Vexor drone cruiser + 5x Hobgoblin I in the drone bay (flag 87),
    relocated + homed at Iyen-Oursta (station 60010387, system 30002642).

Why Vexor over the task's first suggestion (Tristan 593): in the Crucible
data set the Tristan has only a token drone bay/bandwidth, so it cannot
reliably field a flight of light drones; the Vexor (typeID 626) has the
bandwidth to launch all 5.  Both are selectable via --hull.

Drone protocol (verified against src/eve-server, do NOT guess):
  * LAUNCH  -- ShipBound::Drop(PyList toDrop, [ownerID], PyBool ignoreWarning)
               src/eve-server/ship/ShipService.cpp:307 ; the Drone branch at
               :349-408 calls ShipSE::LaunchDrone() per item.  toDrop is a
               list of (itemID, qty) tuples (:341-342).  ownerID is optional
               and "not sent for LaunchDrone()" (:317), so we send
               Drop([(droneID,1),...], False); the False is a real PyBool
               (evemarshal.py:240 encodes bool before int) so it fills
               ignoreWarning and the optional ownerID is skipped.
               Bind: ShipService binds by the client's active ship
               regardless of bind params (ShipService.cpp:50-70), so
               bind("ship",(SYSTEM,SOLARSYSTEM_GROUP)) is valid in space.
  * ENGAGE  -- entity.CmdEngage(droneIDs_list, targetID)
               src/eve-server/npc/EntityService.cpp:118 ; per drone it calls
               DroneAI::Target(pTSE), which locks then attacks (:200-207).
               The "entity" service binds on a BARE INT systemID
               (EntityService.cpp:64-88), NOT a (loc,group) tuple.
  * RETURN  -- entity.CmdReturnBay(droneIDs_list)  (EntityService.cpp:335)
               used for cleanup on exit.
  CHAR-3 (ShipService.cpp:355-369): drone control count derives from the
  pilot's Drones skill level, so the pilot needs Drones V to field 5.

Kill / damage ground truth (docker logs, read-only):
  * kill   -- "SpawnKilled::Belt - called by <ratID>" where <ratID> is the
              dead rat's own itemID (NPC.cpp:305 -> SpawnMgr.cpp:304).
  * damage -- "<name>(<ratID>): DamageUpdate - S:.. A:.. H:.." on the rat
              taking damage (SystemEntity.cpp:188).

NOTE (item cache): staging inserts NEW rows into the entity table.  A
running server will not see them until it reloads item caches, so if this
run stages fresh items it prints a RESTART warning and exits; restart the
server, then re-run (staging is idempotent and will be skipped).
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

# Iyen-Oursta ratting ground (mirrors combat_loop_test.py), NOT the fleet
# home at Jita -- the belt below lives in this system.
STATION = 60010387
SYSTEM = 30002642
BELT = 40168291
FLAG_DRONEBAY = 87

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
    except Exception as e:  # host tooling problem, not a server bug
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
    """Rat itemIDs seen taking damage (DamageUpdate). Evidence that our
    drones are actually hitting even if no kill lands in the window."""
    txt = server_log_since(seconds)
    return {int(m.group(1)) for m in
            re.finditer(r"\((\d+)\): DamageUpdate", txt)}


# ------------------------------------------------------------- provisioning
def char_online(char_id):
    rows = db.query("SELECT online FROM chrCharacters WHERE characterID = "
                    f"{int(char_id)}")
    return bool(rows and rows[0]["online"] not in ("0", ""))


def provision_drone_pilot(char_id, char_name, hull_name, drone_name,
                          drone_count):
    """Stage a drone boat for the pilot at Iyen-Oursta, offline.  Returns
    True iff freshly staged this run (caller should then restart + re-run)."""
    if char_online(char_id):
        raise SystemExit(f"char {char_id} is online; log out before staging "
                         "(server caches items/skills)")
    hull_tid = int(db.type_id(hull_name))
    drone_tid = int(db.type_id(drone_name))

    existing = db.query(
        f"SELECT itemID FROM entity WHERE ownerID = {char_id} AND "
        f"typeID = {hull_tid} AND locationID = {STATION} AND flag = 4")
    if existing:
        ship = int(existing[0]["itemID"])
        # ensure the pilot is parked here and boarding this hull
        db.execute(f"UPDATE chrCharacters SET stationID = {STATION}, "
                   f"solarSystemID = {SYSTEM}, shipID = {ship} "
                   f"WHERE characterID = {char_id}")
        db.execute(f"UPDATE entity SET locationID = {STATION}, flag = 4 "
                   f"WHERE itemID = {char_id}")
        log(f"{char_name}: {hull_name} {ship} already staged at Iyen-Oursta")
        return False

    # relocate the pilot to Iyen-Oursta and stage a fresh hull + drones
    db.execute(f"UPDATE chrCharacters SET stationID = {STATION}, "
               f"solarSystemID = {SYSTEM} WHERE characterID = {char_id}")
    db.execute(f"UPDATE entity SET locationID = {STATION}, flag = 4 "
               f"WHERE itemID = {char_id}")

    ship = pf.insert_item(f"{char_name}'s {hull_name}", hull_tid, char_id,
                          STATION, 4)
    fitted_types = [hull_tid, drone_tid]
    for _ in range(drone_count):
        pf.insert_item("", drone_tid, char_id, ship, FLAG_DRONEBAY)
    db.execute(f"UPDATE chrCharacters SET shipID = {ship} "
               f"WHERE characterID = {char_id}")

    # skills for hull + drones, prerequisites included, then Drones V so the
    # pilot can field a full flight (CHAR-3)
    for skill_tid, level in db.skill_closure(fitted_types):
        db.grant_skill(char_id, skill_tid, level)
    db.grant_skill(char_id, int(db.type_id("Drones")), 5)

    log(f"{char_name}: staged {hull_name} {ship} + {drone_count}x "
        f"{drone_name} + skills (Drones V) at Iyen-Oursta")
    return True


# --------------------------------------------------------------- main flow
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=26000)
    ap.add_argument("--user", default="fleet06")
    ap.add_argument("--password", default="fleet")
    ap.add_argument("--char-id", type=int, default=90000009)  # Dax Herron
    ap.add_argument("--char-name", default="Dax Herron")
    ap.add_argument("--hull", default="Vexor")
    ap.add_argument("--drone", default="Hobgoblin I")
    ap.add_argument("--drone-count", type=int, default=5)
    ap.add_argument("--belt", type=int, default=BELT)
    ap.add_argument("--run-tag", default="DRONE1")
    ap.add_argument("--skip-provision", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    log(f"===== {args.run_tag} start: {args.char_name} ({args.char_id}) "
        f"{args.hull} + {args.drone_count}x {args.drone}")

    # ---- offline provisioning phase ----
    if not args.skip_provision:
        fresh = provision_drone_pilot(args.char_id, args.char_name, args.hull,
                                      args.drone, args.drone_count)
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

    # drone bay contents (same itemIDs become in-space drones after launch;
    # qty-1 stacks are not split, so the IDs are preserved -- Drop :398-402)
    drone_rows = db.query(
        f"SELECT itemID FROM entity WHERE locationID = {ship} "
        f"AND flag = {FLAG_DRONEBAY}")
    drone_ids = [int(r["itemID"]) for r in drone_rows]
    if not drone_ids:
        bug(f"no drones in bay of ship {ship}; nothing to launch")
        mch.close()
        return finish(t0, args, verdict="FAIL")
    log(f"drone bay: {drone_ids}")

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
    # entity (drone control) binds on a BARE INT systemID -- not a tuple
    entity = mch.bind("entity", SYSTEM)
    # ship bound obj is keyed by active ship, so the docked ref is still
    # valid in space; rebind anyway to be explicit
    ship_space = mch.bind("ship", (SYSTEM, SOLARSYSTEM_GROUP))

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
            log(f"warping to rat {npc} to close drone range")
            end = time.time() + 45
            while time.time() < end:
                mch.pump(2.0)
            break
        except CallError as e:
            log(f"warp-to-rat {npc}: {str(e)[:100]}")

    # --- launch drones ---
    # Drop wants a list of (itemID, qty) tuples + a PyBool ignoreWarning.
    to_drop = [(d, 1) for d in drone_ids]
    launched = list(drone_ids)
    try:
        mch.call_bound(ship_space, "Drop", to_drop, False)
        log(f"launched {len(launched)} drones: {launched}")
    except CallError as e:
        bug(f"drone launch (Drop) rejected: {e}")
        return recover_and_finish(mch, ship, t0, args, verdict="FAIL")
    mch.pump(6.0)

    # confirm the drones are in space as entities (they leave the bay)
    still_in_bay = db.query(
        f"SELECT itemID FROM entity WHERE locationID = {ship} "
        f"AND flag = {FLAG_DRONEBAY}")
    if len(still_in_bay) == len(drone_ids):
        bug("drones still in bay after Drop -- launch may not have taken")

    # --- pick a target and engage ---
    target = npcs[0]
    engaged = False
    engage_deadline = time.time() + 90
    while not engaged and time.time() < engage_deadline:
        for npc in npcs:
            try:
                mch.call_bound(entity, "CmdEngage", launched, npc)
                target = npc
                engaged = True
                log(f"CmdEngage accepted vs rat {npc}")
                break
            except CallError as e:
                msg = str(e)
                if "OtherWarping" in msg or "TooDistant" in msg:
                    log(f"engage {npc}: {msg[:100]}; retry")
                else:
                    log(f"CmdEngage {npc} failed: {msg[:140]}")
        if not engaged:
            mch.pump(8.0)
    if not engaged:
        bug("CmdEngage never accepted (drones never reached a target)")

    # --- watch for damage / kills ---
    kills_before = dead_npcs()
    dmg_before = damaged_npcs()
    fight_end = time.time() + 180
    first_damage = None
    while time.time() < fight_end:
        mch.pump(3.0)
        new_dmg = damaged_npcs() - dmg_before
        rat_dmg = new_dmg & set(npcs)
        if rat_dmg and first_damage is None:
            first_damage = sorted(rat_dmg)
            log(f"drone damage confirmed on rats: {first_damage}")
        killed = (dead_npcs() - kills_before) & set(npcs)
        if killed:
            log(f"KILL confirmed on rats: {sorted(killed)}")
            break
        # re-issue engage in case a target died / drones idled
        remaining = [n for n in npcs if n not in (dead_npcs() - kills_before)]
        if remaining:
            try:
                mch.call_bound(entity, "CmdEngage", launched, remaining[0])
            except CallError:
                pass

    killed = sorted((dead_npcs() - kills_before) & set(npcs))
    damaged = sorted((damaged_npcs() - dmg_before) & set(npcs))
    if killed:
        verdict = "PASS"
        log(f"DRONE-KILL PASS: rats killed {killed} (damage seen on {damaged})")
    elif damaged or first_damage:
        verdict = "PARTIAL"
        log(f"DRONE-KILL PARTIAL: drones dealt damage to {damaged or first_damage} "
            "but no kill within 180s (range/DPS/timeout)")
    else:
        verdict = "FAIL"
        bug("no drone damage or kill observed within 180s")

    # recall drones so they are not abandoned, then return + dock
    try:
        mch.call_bound(entity, "CmdReturnBay", launched)
        mch.pump(4.0)
    except CallError as e:
        log(f"CmdReturnBay: {e}")
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
    # if podded, recover the pod-less pilot's ship record while offline later
    cur_ship = int(mch.session.get("shipid") or ship)
    if cur_ship != ship:
        bug(f"pilot lost the hull (now in {cur_ship}) -- podded")
    mch.close()
    return finish(t0, args, verdict=verdict)


def finish(t0, args, verdict="?"):
    log(f"===== {args.run_tag} DRONE-KILL {verdict} in {time.time()-t0:.0f}s, "
        f"{len(BUGS)} bug(s)")
    for b in BUGS:
        log(f"  BUG: {b}")
    return 0 if verdict in ("PASS", "STAGED-RESTART-NEEDED") else 1


if __name__ == "__main__":
    sys.exit(main())

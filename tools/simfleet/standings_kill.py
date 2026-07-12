#!/usr/bin/env python3
"""
STAND-1 kill-path validation via GM /spawn (deterministic, no belt dependency).

Belt rats can't be relied on right now (SPAWN-14: warping in doesn't arm the
belt bubble), so instead of waiting on a natural spawn we use the GM /spawn
command -- which the fleet test accounts hold the DEV role for -- to drop a
faction NPC point-blank next to the bot. Spawned Entity-category items are
owned by the region's rat faction (GMCommands Command_spawn), so killing one
must fire NPC::Killed's STAND-1 path: the killer's standing toward that faction
drops, a repStandingChanges row is logged, and an OnStandingsModified
notification is sent.

    python standings_kill.py
"""

import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import smartbomb_test as sb
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
STATION, SYSTEM = 60010387, 30002642
ACCT, PW, CHAR, TAG = "fleet01", "fleet", 90000004, "Keva"
RAT_TYPE = 29200   # 'Athran Agent', cat-11 frigate, ~150 EHP -> dies fast
# The fitted railguns Keva normally carries are Civilian guns with no charge
# group -- EVEmu gives them 0 damage, so they can never finish the kill. We
# instead fit a smart bomb: 140 EM per pulse, AoE (no lock/tracking), one-shots
# the rat, and its damage path (empWave) is already validated by SMARTBOMB-1.


def sys_entities():
    return {int(r["itemID"]) for r in db.query(
        f"SELECT itemID FROM entity WHERE locationID={SYSTEM}")}


def neg_standings():
    return {(int(r["fromID"]), int(r["toID"])): float(r["standing"])
            for r in db.query(
                f"SELECT fromID,toID,standing FROM repStandings "
                f"WHERE toID={CHAR} AND standing<0")}


def changes():
    return db.query(f"SELECT fromID,toID,ROUND(modification,4) delta,eventTypeID,msg "
                    f"FROM repStandingChanges WHERE toID={CHAR} ORDER BY eventID DESC LIMIT 5")


def srv_log(sec):
    return subprocess.run([DOCKER, "logs", "server", "--since", f"{int(sec)}s"],
                          capture_output=True, text=True, timeout=30).stdout or ""


def wait_stationary(mch, ship, tries=20):
    """Pump until the ship stops warping so a /spawn co-locates with it.

    The rat spawns at the ship's current position; if the ship is mid-warp it
    lands in one bubble while the ship flies to another and can never lock it
    (observed: rat in bubble 48, ship warping to bubble 54). We watch WarpTrace
    for this ship and require two consecutive clean intervals before calling it
    settled, since the post-undock warp is long (~2e9 m).
    """
    tag = str(ship)
    clean = 0
    for _ in range(tries):
        mch.pump(3.0)
        warping = any(("WarpUpdate" in ln and tag in ln) for ln in srv_log(4).splitlines())
        clean = 0 if warping else clean + 1
        if clean >= 2:
            return True
    return False


def run():
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={CHAR}")[0]["online"] not in ("0", ""):
        raise SystemExit(f"char {CHAR} online; cannot stage")

    # clean slate: drop prior negative standings + change log for the char
    db.execute(f"DELETE FROM repStandings WHERE toID={CHAR} AND standing<0")
    db.execute(f"DELETE FROM repStandingChanges WHERE toID={CHAR}")
    before = neg_standings()
    ship = sb.stage_hi(CHAR, TAG, sb.MERLIN, [sb.SMARTBOMB])
    log(f"=== STAND-1 kill path: {TAG} (smartbomb Merlin) spawns+kills rat {RAT_TYPE} ===")

    mch = MachoClient("127.0.0.1", 26000, ACCT, PW)
    mch.enter_world(CHAR)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log("could not stage docked"); return
    sref = mch.bind("ship", (STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", ship, False)
    mch.pump(6)

    bey = mch.bind("beyonce", (SYSTEM, SOLARSYSTEM_GROUP))
    dogma = mch.bind("dogmaIM", (SYSTEM, SOLARSYSTEM_GROUP))
    # Stop and wait until the ship is truly stationary in one bubble, so the
    # spawned rat lands right next to it (else lock fails across bubbles).
    try: mch.call_bound(bey, "CmdStop")
    except CallError: pass
    wait_stationary(mch, ship)
    try: mch.call_bound(bey, "CmdStop")
    except CallError: pass
    mch.pump(3)

    # bring the smart bomb online (COMP-H: activate the "online" effect, since
    # SetModuleOnline reports success but never actually onlines).
    sb_ids = [int(r["itemID"]) for r in db.query(
        f"SELECT itemID FROM entity WHERE locationID={ship} AND flag BETWEEN 27 AND 33")]
    if not sb_ids:
        log("  >>> KILL PATH: FAIL (smart bomb not fitted)"); mch.close(); return
    sb_id = sb_ids[0]
    for _ in range(3):
        try: mch.activate_module(dogma, sb_id, "online", None, 0)
        except CallError: pass
        mch.pump(2)
    # empWave is not warp-safe: for ~25s after undock the ship is still in the
    # post-undock warp/align state and activation is silently denied (the exact
    # settle smartbomb_test waits out).  Pump it down before we pulse.
    log("  settling out of post-undock warp-safe state (~24s)")
    mch.pump(24)

    # /spawn the rat right next to us.  Dynamic NPCs are held in-memory by the
    # SystemManager (not persisted to the `entity` table), so we recover the
    # spawned itemID from the server log rather than a DB diff.
    try:
        rsp = mch.call("slash", "SlashCmd", f"/spawn {RAT_TYPE}")
        log(f"  /spawn response: {repr(rsp)[:120]}")
    except CallError as e:
        log(f"  /spawn FAILED: {str(e)[:160]}")
        mch.close(); return
    mch.pump(5)
    m = re.findall(r"Created dynamic entity (\d+) of type %d" % RAT_TYPE, srv_log(30))
    if not m:
        log("  >>> KILL PATH: FAIL (no dynamic entity in log)"); mch.close(); return
    rat = int(m[-1])
    log(f"  target rat dynamic entity {rat}; pulsing smart bomb {sb_id}")

    # engage: pulse the smart bomb (AoE -- no lock/tracking; the rat is well
    # inside the 3600 m radius) until the standing change fires or it dies.
    dead = False
    deadline = time.time() + 100
    while time.time() < deadline:
        try: mch.activate_module(dogma, sb_id, "empWave", None, 1000)
        except CallError: pass
        mch.pump(4.0)
        if changes():
            dead = True; break
        if re.search(r"(?:Killed|dead|destroyed|Removing).{0,40}%d|%d.{0,40}(?:Killed|dead|destroyed)"
                     % (rat, rat), srv_log(20), re.I):
            dead = True; break

    try: mch.call_bound(bey, "CmdStop")
    except CallError: pass
    mch.pump(4); mch.close()

    time.sleep(1)
    after = neg_standings()
    chg = changes()
    log("=== VERDICT ===")
    log(f"  rat killed (entity gone): {dead}")
    log(f"  negative standings before: {before}")
    log(f"  negative standings after:  {after}")
    log(f"  repStandingChanges: {chg}")
    log("  recent server standing log:")
    for ln in srv_log(120).splitlines():
        if re.search(r"[Ss]tanding|Ship kill|OnStandings", ln):
            log(f"    {ln.strip()[:160]}")
    dropped = bool(after) and after != before
    verdict = "PASS" if (dead and dropped) else ("PARTIAL" if dead else "FAIL")
    log(f"  >>> STAND-1 KILL PATH: {verdict}")


if __name__ == "__main__":
    run()

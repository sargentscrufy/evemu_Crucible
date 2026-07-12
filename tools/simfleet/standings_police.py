#!/usr/bin/env python3
"""
STAND-3 (faction police) + STAND-2 (effective standing) validation.

A pilot who is hostile to an empire and jumps into that empire's space is met
by the empire's navy (SystemManager::CheckFactionPolice -> SpawnFactionResponse).
The trigger is EFFECTIVE standing -- base standing lifted by the Diplomacy skill
-- so this run also proves the STAND-2 math: we seed a base standing and a
Diplomacy level and confirm the server logs the skill-modified value.

Setup: Keva starts docked in Iyen-Oursta (Gallente 500004, 0.78) with her
Gallente standing set hostile, then flies through the gate to Faurent (also
Gallente). Arrival fires the police check.

    python standings_police.py
"""

import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import fittings
import pvp_battle as pvp
import travel
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
STATION, SYSTEM = 60010387, 30002642      # Iyen-Oursta IV - Moon 4 station
DEST = 30002643                           # Faurent, adjacent, also Gallente
GALLENTE = 500004
DIPLOMACY = 3357
ACCT, PW, CHAR, TAG = "fleet01", "fleet", 90000004, "Keva"
BASE_STANDING = -6.0
DIP_LEVEL = 5     # lifts -6 to -6 + (10-6)*0.04*5 = -5.2 (still hostile)


def srv_log(sec):
    return subprocess.run([DOCKER, "logs", "server", "--since", f"{int(sec)}s"],
                          capture_output=True, text=True, timeout=30).stdout or ""


def run():
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={CHAR}")[0]["online"] not in ("0", ""):
        raise SystemExit(f"char {CHAR} online; cannot stage")

    # seed a hostile base standing toward Gallente + a Diplomacy level
    db.execute(f"DELETE FROM repStandings WHERE fromID={GALLENTE} AND toID={CHAR}")
    db.execute(f"INSERT INTO repStandings (fromID,toID,standing) VALUES ({GALLENTE},{CHAR},{BASE_STANDING})")
    db.grant_skill(CHAR, DIPLOMACY, DIP_LEVEL)
    # grant_skill can leave the skillLevel dogma attribute (280) unset, which
    # makes GetSkillLevel read 0; set it explicitly so the STAND-2 lift shows.
    sk = db.query(f"SELECT itemID FROM entity WHERE ownerID={CHAR} AND typeID={DIPLOMACY} AND flag=7")
    if sk:
        sid = int(sk[0]["itemID"])
        db.execute(f"DELETE FROM entity_attributes WHERE itemID={sid} AND attributeID=280")
        db.execute(f"INSERT INTO entity_attributes (itemID,attributeID,valueInt,valueFloat) "
                   f"VALUES ({sid},280,{DIP_LEVEL},{float(DIP_LEVEL)})")
    expected_eff = BASE_STANDING + (10.0 - BASE_STANDING) * 0.04 * DIP_LEVEL if BASE_STANDING >= 0 \
        else BASE_STANDING + (10.0 + BASE_STANDING) * 0.04 * DIP_LEVEL
    log(f"=== STAND-3: {TAG} base Gallente standing {BASE_STANDING}, Diplomacy {DIP_LEVEL} "
        f"-> expected effective {expected_eff:.2f} ===")

    ship = pvp.stage(CHAR, TAG, fittings.ATTACKER_FIT)
    mch = MachoClient("127.0.0.1", 26000, ACCT, PW)
    mch.enter_world(CHAR)
    if not ensure_docked(mch, STATION, SYSTEM, ship):
        log("could not stage docked"); return
    sref = mch.bind("ship", (STATION, STATION_GROUP))
    mch.call_bound(sref, "Undock", ship, False)
    mch.pump(14)
    bey = travel.bind_beyonce(mch)
    try: mch.call_bound(bey, "CmdStop")
    except CallError: pass
    mch.pump(4)

    log(f"  flying Iyen-Oursta -> Faurent ({DEST}) through the gate")
    arrived = travel.goto_system(mch, ship, DEST, min_security=0.4)
    log(f"  goto_system arrived={arrived}")
    # linger so the navy locks and the log flushes
    for _ in range(6):
        mch.pump(3.0)
    try: mch.call_bound(travel.bind_beyonce(mch), "CmdStop")
    except CallError: pass
    mch.pump(3); mch.close()

    # ---- verdict from the server log ----
    logtxt = srv_log(180)
    police = re.search(r"CheckFactionPolice: .*eff standing (-?\d+\.\d+) to faction (\d+).*?(\d+) responders", logtxt)
    dispatched = re.findall(r"SpawnFactionResponse: (.+?)\((\d+)\) faction (\d+) dispatched to hunt", logtxt)
    log("=== VERDICT ===")
    if police:
        eff_logged = float(police.group(1))
        log(f"  CheckFactionPolice fired: eff standing {eff_logged}, faction {police.group(2)}, "
            f"{police.group(3)} responders")
        log(f"  STAND-2 effective-standing math: expected {expected_eff:.2f}, "
            f"server logged {eff_logged:.2f} -> {'PASS' if abs(eff_logged-expected_eff) < 0.05 else 'FAIL'}")
    else:
        log("  CheckFactionPolice did NOT fire (no log line)")
    log(f"  navy dispatched: {len(dispatched)} ships -> {[d[0] for d in dispatched]}")
    for ln in logtxt.splitlines():
        if re.search(r"FactionPolice|SpawnFactionResponse|Police.*Target", ln):
            log(f"    {ln.strip()[:150]}")
    verdict = "PASS" if (police and dispatched) else "FAIL"
    log(f"  >>> STAND-3 FACTION POLICE: {verdict}")


if __name__ == "__main__":
    run()

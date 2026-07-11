#!/usr/bin/env python3
"""
HARDEN-1: malformed-input crash probe.

PI-1 showed that a type-confused RPC arg (a list where a tuple was expected)
tripped an AsTuple() assert and SIGABRT'd the whole node. This probe sends a
battery of deliberately malformed / type-confused arguments to key services
and, after each call, checks whether the server crashed (RestartCount rose).

Untrusted client input must never crash the node -- any hit here is a
hardening bug in the same class as PI-1.

Run:  python malformed_probe.py
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import pvp_battle as pvp
from machoclient import MachoClient, CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP, STATION_GROUP
import provision_fleet as pf

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
STATION, SYSTEM = pvp.STATION, pvp.SYSTEM
PILOT = ("fleet01", "fleet", 90000004, "Keva")


def restart_count():
    out = subprocess.run([DOCKER, "inspect", "--format", "{{.RestartCount}}", "server"],
                         capture_output=True, text=True, timeout=20)
    try:
        return int(out.stdout.strip())
    except ValueError:
        return -1


def wait_online(timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        out = subprocess.run([DOCKER, "logs", "server", "--since", "20s"],
                             capture_output=True, text=True, timeout=20)
        if "EVEmu Server is Online" in (out.stdout or ""):
            return True
        time.sleep(3)
    return False


# each case: (service, method, args, note).  bound services are marked by a
# leading "@" and bind param.
CASES = [
    # (bind_service, bind_param, method, args, note)
    ("ramProxy", None, "InstallJob",
     ["not-a-list", 1, 2, 3, 4, 5, 6, False, "x"], "InstallJob: string where AssemblyLineData expected"),
    ("ramProxy", None, "InstallJob",
     [1, 2, 3, 4, 5, 6, 7, 8, 9], "InstallJob: all ints"),
    ("ramProxy", None, "CompleteJob",
     [42, "notint", False], "CompleteJob: string jobID"),
    ("reprocessingSvc", STATION, "Reprocess",
     ["notalist", STATION, None, None, False, []], "Reprocess: string itemIDs"),
    ("reprocessingSvc", STATION, "GetQuotes",
     [42, "notint"], "GetQuotes: int where list expected"),
    ("planetMgr", 40168289, "UserUpdateNetwork",
     [42], "PI UUN: int where list expected (post PI-1)"),
    ("planetMgr", 40168289, "UserUpdateNetwork",
     [["still-a-list-not-tuple"]], "PI UUN: list command element (PI-1 regression)"),
]


def run():
    acct, pw, char, tag = PILOT
    if db.query(f"SELECT online FROM chrCharacters WHERE characterID={char}")[0]["online"] not in ("0", ""):
        raise SystemExit(f"char {char} online; cannot stage")
    ship = pf.insert_item(f"{char}'s Ibis", 601, char, STATION, 4)
    db.execute(f"UPDATE chrCharacters SET stationID={STATION}, solarSystemID={SYSTEM}, shipID={ship} WHERE characterID={char}")

    results = []
    for svc, bind_param, method, args, note in CASES:
        rc_before = restart_count()
        try:
            mch = MachoClient("127.0.0.1", 26000, acct, pw)
            mch.enter_world(char)
            ensure_docked(mch, STATION, SYSTEM, ship)
            if bind_param is not None:
                ref = mch.bind(svc, bind_param)
                try:
                    mch.call_bound(ref, method, *args)
                except CallError as e:
                    pass  # a clean UserError is the GOOD outcome
            else:
                try:
                    mch.call(svc, method, *args)
                except CallError:
                    pass
            mch.pump(1)
            mch.close()
        except Exception as e:
            # a dropped connection here usually means the node crashed
            log(f"  [{note}] client exception: {type(e).__name__}: {str(e)[:80]}")
        time.sleep(3)
        rc_after = restart_count()
        crashed = rc_after > rc_before
        results.append((note, crashed))
        # NOTE: a crash here is attributed to this case's WINDOW, not
        # necessarily the malformed RPC -- the crash may occur in the
        # per-case reconnect/ensure_docked (Undock) setup. Confirm the actual
        # frame from the gdb backtrace (RUN_GDB) before blaming the RPC.
        log(f"  {'CRASH' if crashed else 'ok   '}  {note}")
        if crashed:
            wait_online(90)   # let the node respawn before the next case

    crashes = [n for n, c in results if c]
    log("=== VERDICT ===")
    log(f"  cases: {len(results)}  crashes: {len(crashes)}")
    for n in crashes:
        log(f"    CRASH: {n}")
    log(f"  >>> MALFORMED-INPUT HARDENING: {'PASS (no crashes)' if not crashes else 'FAIL ('+str(len(crashes))+' crash-inducing inputs)'}")
    return results


if __name__ == "__main__":
    run()

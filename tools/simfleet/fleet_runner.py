#!/usr/bin/env python3
"""
Fleet supervisor: launches a mission-loop process per pilot whose role
has a runnable mission (currently hauler_shuttle), tags and merges
their output into one stream, and restarts loops that die -- the
scaffold that will eventually run 1000+ sim players in static roles.

    python fleet_runner.py [--duration 3600] [--max-restarts 5]
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FLEET = json.load(open(os.path.join(HERE, "fleet.json")))

RESTARTS = {}
LOCK = threading.Lock()


def out(tag, line):
    with LOCK:
        print(f"{time.strftime('%H:%M:%S')} [{tag}] {line}", flush=True)


def run_pilot(pilot, stop_at, max_restarts):
    m = pilot["mission"]
    tag = pilot["account"]
    while time.time() < stop_at:
        cmd = [sys.executable, os.path.join(HERE, "hauler_loop.py"),
               "--account", pilot["account"],
               "--char-name", pilot["name"],
               "--home-station", str(FLEET["home_station"]),
               "--system", str(FLEET["home_system"]),
               "--clear-m", str(m.get("clear_m", 3000)),
               "--dwell-s", str(m.get("dwell_s", 30))]
        out(tag, f"launching mission loop for {pilot['name']}")
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            out(tag, line.rstrip())
            if time.time() > stop_at:
                p.terminate()
                break
        rc = p.wait()
        if time.time() >= stop_at:
            break
        RESTARTS[tag] = RESTARTS.get(tag, 0) + 1
        out(tag, f"loop exited rc={rc}; restart #{RESTARTS[tag]}")
        if RESTARTS[tag] >= max_restarts:
            out(tag, "KINK: max restarts reached; pilot grounded")
            break
        time.sleep(30)
    out(tag, "supervisor done")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=3600,
                    help="seconds to run the fleet (default 1h)")
    ap.add_argument("--max-restarts", type=int, default=5)
    args = ap.parse_args()

    stop_at = time.time() + args.duration
    threads = []
    stagger = 0
    for pilot in FLEET["pilots"]:
        if pilot["mission"]["type"] != "hauler_shuttle":
            continue
        t = threading.Thread(target=run_pilot,
                             args=(pilot, stop_at, args.max_restarts),
                             daemon=True)
        threads.append((t, stagger))
        stagger += 20   # don't storm the login server

    for t, delay in threads:
        time.sleep(delay and 20 or 0)
        t.start()
    for t, _ in threads:
        t.join()
    out("fleet", f"fleet run complete. restarts: {RESTARTS}")


if __name__ == "__main__":
    sys.exit(main())

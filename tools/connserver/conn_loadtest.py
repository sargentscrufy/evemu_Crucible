#!/usr/bin/env python3
"""
Connection-server load probe: open N concurrent client sessions THROUGH
the connserver (login + character select + a few pumps), hold them, and
report success rate + connserver stats.  Validates the relay under fan-out
and exercises the login path the scale plan flags as the #2 bottleneck.

    python conn_loadtest.py --n 40 --port 26005

Uses the qatest account family; every session logs in the SAME account
(the server does not bind char-to-account on select), selecting distinct
sim chars so sessions are independent.  This is a CONNECTION stress test,
not a gameplay test -- sessions idle after entering world.
"""

import argparse
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

from machoclient import MachoClient, log  # noqa: E402

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
# provisioned sim chars that exist (fleet + qa families)
CHARS = list(range(90000004, 90000015))

results = {"ok": 0, "fail": 0}
lock = threading.Lock()
sessions = []


def one(idx, host, port, hold, user, pw, char):
    try:
        mch = MachoClient(host, port, user, pw)
        mch.enter_world(char)
        with lock:
            results["ok"] += 1
            sessions.append(mch)
        end = time.time() + hold
        while time.time() < end:
            mch.pump(3.0)
        mch.close()
    except Exception as e:
        with lock:
            results["fail"] += 1
        if idx < 5:
            log(f"session {idx} failed: {type(e).__name__}: {str(e)[:150]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=26005)
    ap.add_argument("--hold", type=float, default=60.0)
    ap.add_argument("--stagger", type=float, default=0.25)
    args = ap.parse_args()

    log(f"opening {args.n} sessions through {args.host}:{args.port} "
        f"(hold {args.hold}s, stagger {args.stagger}s)")
    threads = []
    t0 = time.time()
    for i in range(args.n):
        char = CHARS[i % len(CHARS)]
        # all on qatest account; server doesn't bind char->account on select
        t = threading.Thread(target=one,
                             args=(i, args.host, args.port, args.hold,
                                   "qatest", "fleet", char),
                             daemon=True)
        threads.append(t)
        t.start()
        time.sleep(args.stagger)
    login_done = time.time()
    log(f"all {args.n} launched in {login_done - t0:.1f}s; "
        f"connected so far ok={results['ok']} fail={results['fail']}")

    for t in threads:
        t.join(timeout=args.hold + 60)

    # connserver stats + server health
    stats = subprocess.run([DOCKER, "logs", "connserver", "--since", "180s"],
                           capture_output=True, text=True, timeout=30)
    for line in (stats.stdout or "").strip().splitlines():
        if "STATS" in line or "REFUSED" in line:
            log(line)
    up = subprocess.run([DOCKER, "ps", "--format", "{{.Names}} {{.Status}}"],
                        capture_output=True, text=True, timeout=30)
    log("containers:\n" + up.stdout.strip())

    peak = results["ok"]
    log(f"RESULT: ok={results['ok']} fail={results['fail']} "
        f"of {args.n} (peak concurrent ~{peak})")
    return 0 if results["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

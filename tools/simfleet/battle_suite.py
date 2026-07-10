#!/usr/bin/env python3
"""
Run the 50-battle tank matrix: each defender fit fought several times by
the fixed civilian-gun attacker; results to CSV for analysis.

    python battle_suite.py [--runs 5] [--window 100]
"""

import argparse
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "simchars"))

import db
import fittings
import pvp_battle
from machoclient import log

CSV_PATH = os.path.join(HERE, "battle_results.csv")


def both_offline():
    n = db.query("SELECT COUNT(*) n FROM chrCharacters WHERE characterID IN "
                 "(90000004, 90000006) AND online = 1")[0]["n"]
    return int(n) == 0


def wait_offline(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if both_offline():
            return True
        time.sleep(4)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--window", type=float, default=100.0)
    args = ap.parse_args()

    fits = sorted(fittings.DEFENDER_FITS)
    total = len(fits) * args.runs
    log(f"===== TANK BATTLE SUITE: {len(fits)} fits x {args.runs} = {total} battles")

    new = not os.path.exists(CSV_PATH)
    f = open(CSV_PATH, "a", newline="")
    w = csv.writer(f)
    if new:
        w.writerow(["ts", "battle", "fit", "hull", "ehp", "raw_hp",
                    "killed", "survival_s", "final_shield", "final_armor",
                    "final_hull", "first_dmg_s"])
        f.flush()

    n = 0
    for run in range(args.runs):
        for fit in fits:
            n += 1
            if not wait_offline():
                log(f"battle {n}: chars still online; skipping")
                continue
            log(f"----- battle {n}/{total}: {fit} (run {run+1})")
            try:
                r = pvp_battle.run_battle(fit, window=args.window)
            except Exception as e:
                log(f"battle {n} EXCEPTION {type(e).__name__}: {str(e)[:200]}")
                wait_offline()
                continue
            w.writerow([int(time.time()), n, r["fit"], r["hull"], r["ehp"],
                        r["raw_hp"], int(r["killed"]), r["survival_s"],
                        r["final_s"], r["final_a"], r["final_h"],
                        r["first_dmg_s"]])
            f.flush()
            time.sleep(6)   # let both log out
    f.close()
    log(f"===== SUITE COMPLETE: {n} battles -> {CSV_PATH}")


if __name__ == "__main__":
    main()

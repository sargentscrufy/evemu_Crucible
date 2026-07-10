#!/usr/bin/env python3
"""
Analyze battle_results.csv: per-fit tank effectiveness, and validate that
observed survival tracks computed EHP.

    python battle_analyze.py
"""

import csv
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "battle_results.csv")


def main():
    rows = []
    with open(CSV_PATH) as f:
        for r in csv.DictReader(f):
            rows.append(r)
    if not rows:
        print("no results yet")
        return

    by_fit = {}
    for r in rows:
        by_fit.setdefault(r["fit"], []).append(r)

    print(f"{len(rows)} battles across {len(by_fit)} fits\n")
    hdr = (f"{'fit':<26}{'n':>3}{'EHP':>7}{'kills':>6}"
           f"{'avg_shield%':>12}{'avg_armor%':>11}{'avg_hull%':>10}"
           f"{'tank_lost%':>11}")
    print(hdr)
    print("-" * len(hdr))

    summary = []
    for fit in sorted(by_fit, key=lambda k: -tank_lost(by_fit[k])):
        rs = by_fit[fit]
        n = len(rs)
        ehp = int(float(rs[0]["ehp"]))
        kills = sum(int(r["killed"]) for r in rs)
        avg_s = st.mean(float(r["final_shield"]) for r in rs) * 100
        avg_a = st.mean(float(r["final_armor"]) for r in rs) * 100
        avg_h = st.mean(float(r["final_hull"]) for r in rs) * 100
        lost = tank_lost(rs)
        print(f"{fit:<26}{n:>3}{ehp:>7}{kills:>6}"
              f"{avg_s:>11.1f}%{avg_a:>10.1f}%{avg_h:>9.1f}%{lost:>10.1f}%")
        summary.append((fit, ehp, lost))

    # correlation check: higher EHP should mean less tank lost
    print("\nValidation: EHP vs tank-lost (higher EHP should lose less)")
    ehps = [s[1] for s in summary]
    losts = [s[2] for s in summary]
    if len(ehps) > 2:
        try:
            r = correlation(ehps, losts)
            print(f"  Pearson r(EHP, tank_lost%) = {r:+.2f} "
                  f"({'expected negative — consistent' if r < -0.3 else 'weak/unexpected — investigate'})")
        except Exception:
            pass


def tank_lost(rs):
    # average total tank fraction lost = 3 - (S+A+H) over 3 layers, %
    vals = []
    for r in rs:
        rem = (float(r["final_shield"]) + float(r["final_armor"])
               + float(r["final_hull"])) / 3.0
        vals.append((1 - rem) * 100)
    return st.mean(vals)


def correlation(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (sx * sy) if sx and sy else 0.0


if __name__ == "__main__":
    main()

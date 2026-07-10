#!/usr/bin/env python3
"""
verify_completion.py
Mechanical gate for Caldari mission research goal.
Run from workspace root: python KB/missions/caldari/verify_completion.py

Checks:
- For each security row in MANIFEST marked 'exact': atomic .md exists, sources/<slug>.txt >200 bytes, md has Encounters/Objectives with numeric ship count.
- exact security count >= 8
- Entrepreneur has 10 numbered steps (no summaries)
- Chain has no "or similar" or "e.g."
Writes report to {SCRATCH}/verification-report.txt (canonical implementer scratch)
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # G:\Claude\Evemu or equiv
KB = ROOT / "KB" / "missions" / "caldari"
SECURITY_DIR = KB / "security"
SOURCES_DIR = KB / "sources"
CAREER_DIR = KB / "career"
CHAIN_FILE = KB / "chains" / "spies-to-corporate-records.md"
MANIFEST = KB / "MANIFEST.md"

# Canonical scratch for report (per plan)
SCRATCH = Path(r"C:\Users\RAM\AppData\Local\Temp\grok-goal-f9ac4721bef3\implementer")
REPORT = SCRATCH / "verification-report.txt"

# Mapping from MANIFEST mission name (approx) to slug used for files
# Derived from current files and MANIFEST table
EXACT_SLUGS = [
    ("The Guristas Spies", "the-guristas-spies-l4"),
    ("Guristas Extravaganza", "guristas-extravaganza-l4"),
    ("The Assault", "the-assault-l4"),
    ("Vengeance", "vengeance-l4"),
    ("The Mordus Headhunters / Head Hunter Threat", "the-mordus-headhunters-l4"),
    ("Corporate Records", "corporate-records-l1"),
    ("The Hidden Stash", "the-hidden-stash-l1"),
    ("Gone Berserk", "gone-berserk-l4"),
    ("The Blockade", "the-blockade-l3-guristas"),
    ("Eliminate a Pirate Nuisance (Guristas)", "eliminate-a-pirate-nuisance-l1"),
]

def slugify(name: str, level: str = "") -> str:
    s = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if level:
        s += f"-{level}"
    return s

def parse_manifest_exact():
    """Parse MANIFEST table for security rows marked exact. Return list of (mission, slug, level)"""
    text = MANIFEST.read_text(encoding="utf-8", errors="ignore")
    rows = []
    in_table = False
    for line in text.splitlines():
        if line.strip().startswith("| # | Mission"):
            in_table = True
            continue
        if in_table and line.strip().startswith("##"):
            break
        if in_table and line.strip().startswith("|") and "exact" in line.lower():
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 4:
                mission = parts[1]
                level = parts[2].split()[0] if parts[2] else ""
                status = parts[4] if len(parts) > 4 else ""
                if "exact" in status.lower():
                    # derive slug
                    slug = None
                    for m, s in EXACT_SLUGS:
                        if m.lower() in mission.lower() or mission.lower() in m.lower():
                            slug = s
                            break
                    if not slug:
                        slug = slugify(mission, level.lower() if level else "")
                    rows.append((mission, slug, level))
    return rows

def has_numeric_ship_count(md_path: Path) -> bool:
    if not md_path.exists():
        return False
    txt = md_path.read_text(encoding="utf-8", errors="ignore")
    # Require section header + concrete ship counts or explicit TRIGGER mentions (no loose \d+ fallback)
    if not re.search(r'##\s*(Encounters|Objectives|Pocket|Group|Wave|Single|Initial)', txt, re.I):
        if not re.search(r'(Pocket|Group|Wave|Single|Initial|Spawn)\s*:', txt, re.I):
            return False
    # Must have explicit x ship or TRIGGER with context for full table fidelity
    if re.search(r'\b\d+[xX]?\s*(x\s*)?(Frigate|Cruiser|Battlecruiser|Battleship|Destroyer|Interceptor|Drone|Battery|Sentry|Pithi|Pith)', txt, re.I):
        return True
    if re.search(r'\d+\s*(x\s*)?(frig|crui|bs|bc|des|int|pithi|pith)', txt, re.I):
        return True
    if re.search(r'\*\*TRIGGER\*\*|\*\*Highest Bounty TRIGGER\*\*|\*\*Completes Mission\*\*', txt, re.I):
        return True
    return False

def check_sources_raw(slug: str) -> bool:
    p = SOURCES_DIR / f"{slug}.txt"
    if not p.exists():
        return False
    try:
        return p.stat().st_size > 200
    except:
        return False

def check_career_entrepreneur():
    p = CAREER_DIR / "entrepreneur-balancing-books-1-10.md"
    if not p.exists():
        return False, "missing file"
    txt = p.read_text(encoding="utf-8", errors="ignore")
    steps = re.findall(r'\*\*Balancing the Books \((\d+) of 10\)\*\*', txt)
    nums = [int(x) for x in steps]
    if len(nums) >= 10 and all(i in nums for i in range(1,11)):
        return True, "10 steps found"
    # fallback count numbered
    numbered = len(re.findall(r'^\d+\.\s+\*\*Balancing', txt, re.M))
    return numbered >= 10, f"found {numbered} numbered"

def check_chain_no_hedges():
    if not CHAIN_FILE.exists():
        return False, "missing chain"
    txt = CHAIN_FILE.read_text(encoding="utf-8", errors="ignore").lower()
    if "or similar" in txt or re.search(r'\be\.g\.', txt):
        return False, "contains hedge"
    return True, "no hedges"

def main():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    report_lines = []
    security_exact = parse_manifest_exact()
    report_lines.append(f"Parsed {len(security_exact)} security rows marked exact from MANIFEST")

    fails = []
    for mission, slug, level in security_exact:
        atomic = SECURITY_DIR / f"{slug}.md"
        has_atomic = atomic.exists()
        has_raw = check_sources_raw(slug)
        has_numbers = has_numeric_ship_count(atomic) if has_atomic else False
        ok = has_atomic and has_raw and has_numbers
        line = f"  {mission} ({slug}): atomic={has_atomic} raw>200={has_raw} numeric_ship={has_numbers} -> {'PASS' if ok else 'FAIL'}"
        report_lines.append(line)
        if not ok:
            fails.append((mission, slug, has_atomic, has_raw, has_numbers))

    exact_count = len(security_exact)
    report_lines.append(f"exact security count: {exact_count} (>=8 required)")

    # Career
    ok_ent, msg_ent = check_career_entrepreneur()
    report_lines.append(f"Entrepreneur 10 steps: {ok_ent} ({msg_ent})")
    if not ok_ent:
        fails.append(("Entrepreneur", "", False, False, False))

    # Chain
    ok_chain, msg_chain = check_chain_no_hedges()
    report_lines.append(f"Chain no hedges: {ok_chain} ({msg_chain})")
    if not ok_chain:
        fails.append(("Chain", "", False, False, False))

    overall = (exact_count >= 8 and not fails and ok_ent and ok_chain)
    status = "PASS" if overall else "FAIL"
    report_lines.insert(0, f"VERIFICATION {status}")
    report_lines.append(f"OVERALL: {status}")
    if fails:
        report_lines.append("FAILS:")
        for f in fails:
            report_lines.append(f"  {f}")

    REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("\n".join(report_lines))
    print(f"\nReport written to {REPORT}")
    sys.exit(0 if overall else 1)

if __name__ == "__main__":
    main()

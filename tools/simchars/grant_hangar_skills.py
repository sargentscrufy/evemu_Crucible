#!/usr/bin/env python3
"""
Grant a character every skill needed to use everything in their hangar:
all ships (flag 4) at their station(s) plus every item fitted or carried
inside those ships. Recursive prerequisite closure via db.skill_closure.

    python grant_hangar_skills.py --char-id 90000003

Character must be OFFLINE; restart the server afterwards if the
character was logged in since boot (ItemFactory caches loaded items).
"""

import argparse

import db
from machoclient import log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--char-id", type=int, required=True)
    args = ap.parse_args()

    rows = db.query("SELECT online FROM chrCharacters WHERE characterID = "
                    f"{args.char_id}")
    if not rows:
        raise SystemExit("character not found")
    if rows[0]["online"] not in ("0", ""):
        raise SystemExit("character is online; log out first")

    ships = db.query(
        "SELECT itemID, typeID FROM entity WHERE ownerID = "
        f"{args.char_id} AND flag = 4 AND typeID IN "
        "(SELECT typeID FROM invTypes JOIN invGroups USING (groupID) "
        "WHERE categoryID = 6)")
    type_ids = {int(s["typeID"]) for s in ships}
    for s in ships:
        for it in db.query("SELECT DISTINCT typeID FROM entity WHERE "
                           f"locationID = {int(s['itemID'])}"):
            type_ids.add(int(it["typeID"]))

    log(f"{len(ships)} ships, {len(type_ids)} distinct types in hangar")
    granted = raised = 0
    for skill_tid, level in db.skill_closure(sorted(type_ids)):
        if db.grant_skill(args.char_id, skill_tid, level):
            granted += 1
            name = db.query("SELECT typeName FROM invTypes WHERE typeID = "
                            f"{skill_tid}")
            log(f"  granted {name[0]['typeName']} "
                f"{'I' * level if level <= 3 else level}")
    log(f"done: {granted} skills granted/raised")


if __name__ == "__main__":
    main()

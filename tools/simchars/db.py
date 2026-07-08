"""
Director-side database access for sim characters.

Tier-1 actors and the future AI Director legitimately own DB access
(plan.md); sim-character provisioning uses it for the things no client
protocol exists for: funding wallets, finding freshly purchased item IDs,
resolving type names, and reading slot layouts.

Uses `docker exec db mariadb` so it works anywhere the compose stack runs.
"""

import json
import subprocess

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"


def query(sql):
    """Run SQL, return list of dict rows."""
    out = subprocess.run(
        [DOCKER, "exec", "db", "mariadb", "-uevemu", "-pevemu", "evemu",
         "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"db query failed: {out.stderr.strip()}")
    lines = out.stdout.strip().splitlines()
    if len(lines) < 2:
        return []
    headers = lines[0].split("\t")
    return [dict(zip(headers, ln.split("\t"))) for ln in lines[1:]]


def execute(sql):
    out = subprocess.run(
        [DOCKER, "exec", "db", "mariadb", "-uevemu", "-pevemu", "evemu",
         "-e", sql],
        capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"db execute failed: {out.stderr.strip()}")


def type_id(type_name):
    rows = query("SELECT typeID FROM invTypes WHERE typeName = "
                 f"{sql_str(type_name)} LIMIT 1")
    if not rows:
        raise KeyError(f"unknown type name: {type_name}")
    return int(rows[0]["typeID"])


def slot_layout(ship_type_id):
    """(lowSlots, medSlots, hiSlots) from dogma attributes 12/13/14."""
    rows = query(
        "SELECT attributeID, valueInt, valueFloat FROM dgmTypeAttributes "
        f"WHERE typeID = {int(ship_type_id)} AND attributeID IN (12,13,14)")
    slots = {12: 0, 13: 0, 14: 0}
    for r in rows:
        v = r["valueInt"] if r["valueInt"] not in ("NULL", "", None) \
            else r["valueFloat"]
        slots[int(r["attributeID"])] = int(float(v))
    return slots[12], slots[13], slots[14]


def station_ask(station_id, type_id_):
    """Cheapest sell order (price, volRemaining) at a station, or None."""
    rows = query(
        "SELECT price, volRemaining FROM mktOrders WHERE bid = 0 AND "
        f"stationID = {int(station_id)} AND typeID = {int(type_id_)} "
        "AND volRemaining > 0 ORDER BY price LIMIT 1")
    if not rows:
        return None
    return float(rows[0]["price"]), int(rows[0]["volRemaining"])


def wallet_balance(char_id):
    rows = query("SELECT balance FROM chrCharacters WHERE characterID = "
                 f"{int(char_id)}")
    return float(rows[0]["balance"]) if rows else 0.0


def fund_wallet(char_id, amount):
    """Set balance. Character must be OFFLINE (server caches balances)."""
    rows = query("SELECT online FROM chrCharacters WHERE characterID = "
                 f"{int(char_id)}")
    if rows and rows[0]["online"] not in ("0", ""):
        raise RuntimeError(f"char {char_id} is online; log out before "
                           f"funding (server caches wallet)")
    execute(f"UPDATE chrCharacters SET balance = {float(amount)} "
            f"WHERE characterID = {int(char_id)}")


def hangar_items(char_id, station_id, type_id_=None):
    """Items owned by char in a station hangar (flag 4)."""
    cond = f"AND typeID = {int(type_id_)}" if type_id_ else ""
    return [
        {"itemID": int(r["itemID"]), "typeID": int(r["typeID"]),
         "quantity": int(r["quantity"]), "singleton": int(r["singleton"])}
        for r in query(
            "SELECT itemID, typeID, quantity, singleton FROM entity "
            f"WHERE ownerID = {int(char_id)} AND "
            f"locationID = {int(station_id)} AND flag = 4 {cond} "
            "ORDER BY itemID DESC")
    ]


def ship_fitting(ship_item_id):
    """Items located in a ship, with flags (fitted modules + cargo)."""
    return [
        {"itemID": int(r["itemID"]), "typeID": int(r["typeID"]),
         "flag": int(r["flag"]), "typeName": r["typeName"]}
        for r in query(
            "SELECT e.itemID, e.typeID, e.flag, t.typeName FROM entity e "
            "JOIN invTypes t USING (typeID) WHERE e.locationID = "
            f"{int(ship_item_id)} ORDER BY e.flag")
    ]


def sql_str(s):
    return "'" + str(s).replace("\\", "\\\\").replace("'", "''") + "'"


# ------------------------------------------------------------- skills
# entity_attributes: 276 skillPoints, 280 skillLevel; requirements on
# any type: 182/183/184 required skill typeIDs, 277/278/279 levels;
# 275 skillTimeConstant (rank).

def _attr_val(row):
    v = row.get("valueInt")
    if v in (None, "", "NULL"):
        v = row.get("valueFloat")
    return float(v)


def required_skills(type_id_):
    """[(skillTypeID, level)] directly required to use a type."""
    rows = query(
        "SELECT attributeID, valueInt, valueFloat FROM dgmTypeAttributes "
        f"WHERE typeID = {int(type_id_)} AND attributeID IN "
        "(182,183,184,277,278,279)")
    attrs = {int(r["attributeID"]): int(_attr_val(r)) for r in rows}
    out = []
    for skill_attr, lvl_attr in ((182, 277), (183, 278), (184, 279)):
        if attrs.get(skill_attr):
            out.append((attrs[skill_attr], attrs.get(lvl_attr, 1)))
    return out


def skill_closure(type_ids):
    """All (skillTypeID, level) needed for the given types, recursively
    (skills' own prerequisites included). Highest level wins."""
    need = {}
    frontier = list(type_ids)
    seen = set()
    while frontier:
        tid = frontier.pop()
        if tid in seen:
            continue
        seen.add(tid)
        for skill_tid, level in required_skills(tid):
            if need.get(skill_tid, 0) < level:
                need[skill_tid] = level
            frontier.append(skill_tid)
    return sorted(need.items())


def skill_rank(skill_tid):
    rows = query(
        "SELECT valueInt, valueFloat FROM dgmTypeAttributes WHERE "
        f"typeID = {int(skill_tid)} AND attributeID = 275")
    return int(_attr_val(rows[0])) if rows else 1


def sp_for_level(rank, level):
    return int(250 * rank * (32 ** ((level - 1) / 2.0)))


def grant_skill(char_id, skill_tid, level):
    """Ensure char has the skill at >= level. Char must be OFFLINE."""
    rows = query(
        "SELECT e.itemID, IFNULL(a.valueInt, 0) AS lvl FROM entity e "
        "LEFT JOIN entity_attributes a ON a.itemID = e.itemID AND "
        "a.attributeID = 280 WHERE e.ownerID = "
        f"{int(char_id)} AND e.locationID = {int(char_id)} AND "
        f"e.typeID = {int(skill_tid)} AND e.flag = 7")
    sp = sp_for_level(skill_rank(skill_tid), level)
    if rows:
        if int(rows[0]["lvl"]) >= level:
            return False  # already there
        item_id = int(rows[0]["itemID"])
    else:
        name_rows = query("SELECT typeName FROM invTypes WHERE typeID = "
                          f"{int(skill_tid)}")
        name = name_rows[0]["typeName"] if name_rows else f"skill{skill_tid}"
        execute(
            "INSERT INTO entity (itemName, typeID, ownerID, locationID, "
            "flag, singleton, quantity) VALUES "
            f"({sql_str(name)}, {int(skill_tid)}, {int(char_id)}, "
            f"{int(char_id)}, 7, 1, 1)")
        item_id = int(query("SELECT LAST_INSERT_ID() AS id")[0]["id"])
    execute(
        "INSERT INTO entity_attributes (itemID, attributeID, valueInt) "
        f"VALUES ({item_id}, 280, {int(level)}), ({item_id}, 276, {sp}) "
        "ON DUPLICATE KEY UPDATE valueInt = VALUES(valueInt), "
        "valueFloat = NULL")
    return True


def recover_ship_to_station(char_id, ship_item_id, station_id):
    """Move a stranded (offline) ship to the station's dock perimeter.

    Director-side recovery for sim characters left in space by crashes or
    interrupted runs — the same trust level as funding wallets.
    """
    rows = query("SELECT online FROM chrCharacters WHERE characterID = "
                 f"{int(char_id)}")
    if rows and rows[0]["online"] not in ("0", ""):
        raise RuntimeError("char online; cannot recover position")
    st = query(f"SELECT x, y, z FROM staStations WHERE stationID = "
               f"{int(station_id)}")[0]
    # ~1km off the station center, inside any docking perimeter
    execute(f"UPDATE entity SET x = {float(st['x']) + 800}, "
            f"y = {float(st['y']) + 400}, z = {float(st['z']) + 400} "
            f"WHERE itemID = {int(ship_item_id)}")


def char_station(char_id):
    rows = query("SELECT stationID FROM chrCharacters WHERE characterID = "
                 f"{int(char_id)}")
    return int(rows[0]["stationID"]) if rows and rows[0]["stationID"] else 0


if __name__ == "__main__":
    import sys
    print(json.dumps(query(" ".join(sys.argv[1:])), indent=2))

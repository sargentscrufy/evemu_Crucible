"""
Multi-system travel layer for sim characters (phase-1 M2).

Route planning over the static jump graph (mapDenormalize groupID 10 +
mapJumps) and execution: warp to gate -> CmdStargateJump -> absorb the
system session change -> rebind beyonce -> repeat, then dock.

Wire facts:
  - CmdStargateJump(fromStargateID, toStargateID, shipID) on the beyonce
    bound object; server does not yet range-check the gate (BeyonceService
    line ~800), but we warp to 0 on the gate first anyway for realism.
  - Arrival in the new system is detected by session solarsystemid2
    changing; the old beyonce bind is dead after that.
"""

import time

import db
from machoclient import CallError, log
from provision import ensure_docked, SOLARSYSTEM_GROUP

_GRAPH = None       # systemID -> list of (gateID, destGateID, destSystemID)
_SECURITY = None    # systemID -> security float


def _load_static():
    global _GRAPH, _SECURITY
    if _GRAPH is not None:
        return
    gates = db.query(
        "SELECT itemID, solarSystemID FROM mapDenormalize WHERE groupID = 10")
    gate_system = {int(g["itemID"]): int(g["solarSystemID"]) for g in gates}
    jumps = db.query("SELECT stargateID, celestialID FROM mapJumps")
    graph = {}
    for j in jumps:
        gate = int(j["stargateID"])
        dest_gate = int(j["celestialID"])
        src = gate_system.get(gate)
        dst = gate_system.get(dest_gate)
        if src is None or dst is None:
            continue
        graph.setdefault(src, []).append((gate, dest_gate, dst))
    _GRAPH = graph
    secs = db.query("SELECT solarSystemID, security FROM mapSolarSystems")
    _SECURITY = {int(r["solarSystemID"]): float(r["security"]) for r in secs}


def security(system_id):
    _load_static()
    return _SECURITY.get(int(system_id), 0.0)


def route(from_system, to_system, min_security=0.45):
    """BFS shortest gate route.  Returns [(gateID, destGateID, destSystemID),
    ...] hops, or None.  Intermediate systems must satisfy min_security
    (end points are exempt so a trader can leave/enter any home)."""
    _load_static()
    from_system, to_system = int(from_system), int(to_system)
    if from_system == to_system:
        return []
    seen = {from_system}
    frontier = [(from_system, [])]
    while frontier:
        nxt = []
        for sysid, path in frontier:
            for hop in _GRAPH.get(sysid, ()):  # (gate, destGate, destSys)
                dest = hop[2]
                if dest in seen:
                    continue
                if dest == to_system:
                    return path + [hop]
                if _SECURITY.get(dest, 0.0) >= min_security:
                    seen.add(dest)
                    nxt.append((dest, path + [hop]))
        frontier = nxt
    return None


def jumps_between(from_system, to_system, min_security=0.45):
    r = route(from_system, to_system, min_security)
    return None if r is None else len(r)


def _pump_until(mch, cond, timeout, step=2.0):
    end = time.time() + timeout
    while time.time() < end:
        mch.pump(step)
        if cond():
            return True
    return False


def bind_beyonce(mch):
    return mch.bind("beyonce",
                    (int(mch.session.get("solarsystemid2")), SOLARSYSTEM_GROUP))


def goto_system(mch, ship_id, dest_system, min_security=0.45,
                warp_wait=150.0, kink=None):
    """Fly the current (undocked, in-space) ship to dest_system via gates.
    Returns the fresh beyonce ref in the destination system, or None."""
    note = kink or (lambda m: log(f"TRAVEL-KINK: {m}"))
    cur = int(mch.session.get("solarsystemid2"))
    hops = route(cur, dest_system, min_security)
    if hops is None:
        note(f"no route {cur} -> {dest_system} at minsec {min_security}")
        return None
    bey = bind_beyonce(mch)
    for n, (gate, dest_gate, dest_sys) in enumerate(hops, 1):
        log(f"hop {n}/{len(hops)}: warp gate {gate} -> jump to {dest_sys}")
        try:
            mch.call_bound(bey, "CmdWarpToStuff", "item", gate,
                           byname={"minRange": 0})
        except CallError as e:
            note(f"gate warp rejected: {str(e)[:150]}")
            return None
        mch.pump(warp_wait)     # ride the warp out
        try:
            mch.call_bound(bey, "CmdStargateJump", gate, dest_gate, ship_id)
        except CallError as e:
            note(f"StargateJump {gate}->{dest_gate} failed: {str(e)[:200]}")
            return None
        if not _pump_until(
                mch,
                lambda: int(mch.session.get("solarsystemid2") or 0) == dest_sys,
                60.0):
            note(f"session never moved to {dest_sys} after jump")
            return None
        log(f"in {dest_sys}")
        bey = bind_beyonce(mch)
        try:
            mch.call_bound(bey, "CmdStop")
        except CallError:
            pass
        mch.pump(8)     # gate-cloak settle; jump-in cap is fine post-CAP-1
    return bey


def goto_station(mch, ship_id, station_id, min_security=0.45, kink=None):
    """Travel to the station's system, warp to it, dock."""
    note = kink or (lambda m: log(f"TRAVEL-KINK: {m}"))
    row = db.query(f"SELECT solarSystemID FROM staStations WHERE stationID = {int(station_id)}")
    if not row:
        note(f"unknown station {station_id}")
        return False
    dest_sys = int(row[0]["solarSystemID"])
    cur = int(mch.session.get("solarsystemid2") or 0)
    if cur != dest_sys:
        bey = goto_system(mch, ship_id, dest_sys, min_security, kink=note)
        if bey is None:
            return False
    else:
        bey = bind_beyonce(mch)
    try:
        mch.call_bound(bey, "CmdWarpToStuff", "item", int(station_id),
                       byname={"minRange": 0})
    except CallError as e:
        note(f"station warp rejected: {str(e)[:150]}")
    mch.pump(90)
    mch.session.pop("stationid", None)
    return ensure_docked(mch, int(station_id), dest_sys, ship_id,
                         patience=240.0)

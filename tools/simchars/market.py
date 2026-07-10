"""
Market protocol layer for sim characters (phase-1 M1).

Wraps the marketProxy service (MarketProxyService.cpp) and decodes the
CRowset/PyPackedRow wire format so trader bots can read order books as
plain dicts.

Key wire facts (mirrored from server source):
  - GetOrders(typeID) returns an objectCaching.CachedMethodCallResult;
    the actual rowsets must be fetched from the objectCaching service
    (GetCachedObject) and the blob may be zlib-compressed marshal.
  - GetStationAsks/GetSystemAsks/GetRegionBest return plain (uncached)
    rowsets keyed by typeID.
  - PlaceCharOrder(stationID, typeID, price, qty, bid, orderRange,
    itemID?, minVolume, duration, useCorp, located?); duration=0 means
    fill immediately against standing orders.
  - PyPackedRow: DBRowDescriptor + RLE(zero-compressed) fixed fields
    (columns iterated in descending bit-size order), booleans and null
    flags bit-packed after the byte data, strings as trailing reps
    (EVEUnmarshal.cpp LoadPackedRow / LoadRLE).
"""

import os
import sys
import zlib

_SMOKE_BOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "smoke-bot")
if _SMOKE_BOT not in sys.path:
    sys.path.insert(0, _SMOKE_BOT)

import evemarshal
from evemarshal import PackedRow, PyObj, SubStream, ObjectEx

# DBTYPE -> size in bits (dbtype.cpp)
_SIZE_BITS = {
    20: 64, 21: 64, 5: 64, 6: 64, 64: 64,     # I8 UI8 R8 CY FILETIME
    3: 32, 19: 32, 4: 32,                     # I4 UI4 R4
    2: 16, 18: 16,                            # I2 UI2
    16: 8, 17: 8,                             # I1 UI1
    11: 1,                                    # BOOL
    128: 0, 129: 0, 130: 0,                   # BYTES STR WSTR
}
_SIGNED = {2, 3, 16, 20}
_FLOATS = {4, 5}
_CY = {6}
_STRINGS = {128, 129, 130}


def _descriptor_columns(header):
    """[(name, dbtype), ...] from a blue.DBRowDescriptor ObjectEx."""
    args = header.header[1]
    cols = []
    for col in args[0]:
        name = col[0]
        if hasattr(name, "s"):      # WStr wrapper
            name = name.s
        cols.append((str(name), int(col[1])))
    return cols


def _rle_decode(data, out_size):
    """EVEUnmarshal.cpp LoadRLE: read a run byte, process its two nibbles
    low-first; count = nibble - 8; count >= 0 emits count+1 zero bytes,
    count < 0 copies -count bytes from the input stream (which interleaves
    with the run bytes).  Output zero-padded to out_size."""
    out = bytearray()
    ix = 0
    while ix < len(data):
        run = data[ix]
        ix += 1
        for count in ((run & 0x0F) - 8, (run >> 4) - 8):
            if count >= 0:
                out += b"\x00" * (count + 1)
            else:
                take = -count
                out += data[ix:ix + take]
                ix += take
    out += b"\x00" * max(0, out_size - len(out))
    return bytes(out)


def packedrow_to_dict(row):
    """Decode a PackedRow into {column: value}."""
    cols = _descriptor_columns(row.header)
    ncols = len(cols)

    byte_bits = sum(_SIZE_BITS[t] for _, t in cols if _SIZE_BITS[t] >= 8)
    bool_cols = [i for i, (_, t) in enumerate(cols) if t == 11]
    bool_bits = len(bool_cols)
    expected = (byte_bits >> 3) + ((bool_bits + ncols) >> 3) + 1

    unpacked = _rle_decode(row.raw, expected)

    # iterate columns in descending bit-size (stable by index for ties),
    # exactly like the server's multimap<greater>
    order = sorted(range(ncols), key=lambda i: (-_SIZE_BITS[cols[i][1]], i))

    out = {}
    pos = 0                     # byte cursor into fixed-field data
    str_iter = iter(row.trailing)
    for index in order:
        name, dbtype = cols[index]
        bits = _SIZE_BITS[dbtype]

        # null bitmap: bit (byte_bits + bool_bits + index)
        null_bit = byte_bits + bool_bits + index
        is_null = bool(unpacked[null_bit >> 3] & (1 << (null_bit & 7))) \
            if (null_bit >> 3) < len(unpacked) else False

        if dbtype in _STRINGS:
            val = next(str_iter, None)
            if hasattr(val, "s"):
                val = val.s
            out[name] = None if is_null else val
            continue
        if dbtype == 11:    # bool
            bool_bit = byte_bits + bool_cols.index(index)
            out[name] = None if is_null else \
                bool(unpacked[bool_bit >> 3] & (1 << (bool_bit & 7)))
            continue

        nbytes = bits >> 3
        chunk = unpacked[pos:pos + nbytes]
        pos += nbytes
        if is_null:
            out[name] = None
            continue
        if dbtype in _FLOATS:
            import struct
            out[name] = struct.unpack("<f" if bits == 32 else "<d", chunk)[0]
        else:
            v = int.from_bytes(chunk, "little",
                               signed=(dbtype in _SIGNED))
            if dbtype in _CY:
                v = v / 10000.0
            out[name] = v
    return out


def collect_rows(tree):
    """Walk any response tree; return every PackedRow decoded to a dict."""
    found = []

    def walk(node):
        if isinstance(node, PackedRow):
            found.append(packedrow_to_dict(node))
        elif isinstance(node, (tuple, list)):
            for el in node:
                walk(el)
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(k)
                walk(v)
        elif isinstance(node, PyObj):
            walk(node.state)
        elif isinstance(node, SubStream):
            walk(node.obj)
        elif isinstance(node, ObjectEx):
            walk(node.header)
            walk(node.items)
            walk(node.kw)
    walk(tree)
    return found


def rowset_rows(tree):
    """Decode util.Rowset PyObjs (header + RowClass + lines) to dicts."""
    found = []

    def walk(node):
        if isinstance(node, PyObj) and node.type_name == "util.Rowset":
            state = node.state
            if isinstance(state, dict):
                hdr = state.get("header")
                lines = state.get("lines")
                if hdr and lines is not None:
                    names = [h.s if hasattr(h, "s") else str(h) for h in hdr]
                    for line in lines:
                        found.append(dict(zip(names, line)))
                    return
        if isinstance(node, PyObj) and node.type_name == "util.IndexRowset":
            state = node.state
            if isinstance(state, dict):
                hdr = state.get("header")
                items = state.get("items")
                if hdr and isinstance(items, dict):
                    names = [h.s if hasattr(h, "s") else str(h) for h in hdr]
                    for line in items.values():
                        found.append(dict(zip(names, line)))
                    return
        if isinstance(node, (tuple, list)):
            for el in node:
                walk(el)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, PyObj):
            walk(node.state)
        elif isinstance(node, SubStream):
            walk(node.obj)
        elif isinstance(node, ObjectEx):
            walk(node.header)
            walk(node.items)
            walk(node.kw)
    walk(tree)
    return found


def all_rows(tree):
    rows = collect_rows(tree)
    rows.extend(rowset_rows(tree))
    return rows


# ------------------------------------------------------------- cache flow

def _find_cached_blobs(tree):
    """Collect (compressed?, bytes) cache payload candidates."""
    blobs = []

    def walk(node):
        if isinstance(node, (bytes, bytearray)) and len(node) > 8:
            blobs.append(bytes(node))
        elif isinstance(node, (tuple, list)):
            for el in node:
                walk(el)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, PyObj):
            walk(node.state)
        elif isinstance(node, SubStream):
            walk(node.obj)
        elif isinstance(node, ObjectEx):
            walk(node.header)
            walk(node.items)
            walk(node.kw)
    walk(tree)
    return blobs


def _find_cachedobject_hints(tree):
    """Collect util.CachedObject hints: state is
    (objectID, nodeID, (timestamp, version), shared)."""
    hits = []

    def walk(node):
        if isinstance(node, PyObj):
            if node.type_name == "util.CachedObject" \
            and isinstance(node.state, tuple) and len(node.state) == 4:
                hits.append(node.state)
            walk(node.state)
        elif isinstance(node, (tuple, list)):
            for el in node:
                walk(el)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, SubStream):
            walk(node.obj)
        elif isinstance(node, ObjectEx):
            walk(node.header)
            walk(node.items)
            walk(node.kw)
    walk(tree)
    return hits


def unwrap_cached(mch, rsp):
    """If rsp is an objectCaching.CachedMethodCallResult, fetch the real
    payload via objectCaching.GetCachableObject and unmarshal the (possibly
    zlib-compressed) cache blob; otherwise return rsp unchanged."""
    txt = repr(rsp)[:200]
    if "CachedMethodCallResult" not in txt and "CachedObject" not in txt:
        return rsp
    # inline blob (server may inline small payloads)
    for blob in _find_cached_blobs(rsp):
        payload = _try_unmarshal_blob(blob)
        if payload is not None:
            return payload
    # fetch by hint: GetCachableObject(shared, objectID, (ts, ver), nodeID)
    for object_id, node_id, version, shared in _find_cachedobject_hints(rsp):
        try:
            cached = mch.call("objectCaching", "GetCachableObject",
                              shared, object_id, version, node_id)
        except Exception:
            continue
        for blob in _find_cached_blobs(cached):
            payload = _try_unmarshal_blob(blob)
            if payload is not None:
                return payload
    return rsp


def _try_unmarshal_blob(blob):
    for candidate in (blob,):
        for data in (candidate, _try_zlib(candidate)):
            if data is None:
                continue
            try:
                return evemarshal.loads(data)
            except Exception:
                continue
    return None


def _try_zlib(data):
    try:
        return zlib.decompress(data)
    except Exception:
        return None


# ------------------------------------------------------------- market API

def get_orders(mch, type_id):
    """Full order book (sell, buy) for a type in the pilot's region."""
    rsp = mch.call("marketProxy", "GetOrders", int(type_id))
    rsp = unwrap_cached(mch, rsp)
    rows = all_rows(rsp)
    sells = [r for r in rows if not r.get("bid")]
    buys = [r for r in rows if r.get("bid")]
    return sells, buys


def get_region_best(mch):
    rsp = mch.call("marketProxy", "GetRegionBest")
    return all_rows(rsp) or rsp


def get_station_asks(mch):
    rsp = mch.call("marketProxy", "GetStationAsks")
    return rsp


def get_system_asks(mch):
    rsp = mch.call("marketProxy", "GetSystemAsks")
    return rsp


def get_char_orders(mch):
    rsp = mch.call("marketProxy", "GetCharOrders")
    return all_rows(rsp) or rsp


def buy_immediate(mch, station_id, type_id, price, qty):
    """Instant fill against standing sell orders at this station."""
    return mch.call("marketProxy", "PlaceCharOrder",
                    int(station_id), int(type_id), float(price), int(qty),
                    1, 0, None, 1, 0, False, None)


def sell_immediate(mch, station_id, type_id, price, qty):
    """Instant fill against standing buy orders at this station."""
    return mch.call("marketProxy", "PlaceCharOrder",
                    int(station_id), int(type_id), float(price), int(qty),
                    0, 0, None, 1, 0, False, None)


def place_sell_order(mch, station_id, type_id, price, qty, duration=14):
    return mch.call("marketProxy", "PlaceCharOrder",
                    int(station_id), int(type_id), float(price), int(qty),
                    0, 0, None, 1, int(duration), False, None)


def place_buy_order(mch, station_id, type_id, price, qty,
                    order_range=0, min_volume=1, duration=14):
    return mch.call("marketProxy", "PlaceCharOrder",
                    int(station_id), int(type_id), float(price), int(qty),
                    1, int(order_range), None, int(min_volume),
                    int(duration), False, None)


def cancel_order(mch, order_id):
    return mch.call("marketProxy", "CancelCharOrder", int(order_id), 0)


def wallet_balance(mch):
    """Cash balance via the account service."""
    rsp = mch.call("account", "GetCashBalance", False)
    try:
        return float(repr(rsp).strip("PyObj()' ")) if not isinstance(
            rsp, (int, float)) else float(rsp)
    except (TypeError, ValueError):
        return rsp

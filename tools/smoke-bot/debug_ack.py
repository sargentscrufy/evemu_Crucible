"""Replay login and hex-dump the CryptoHandshakeAck payload on failure."""
import struct
import zlib

import evemarshal
from evemarshal import WStr
from netclient import EVEConnection
import login as L


def recv_raw(conn):
    header = conn._recv_exact(4)
    (length,) = struct.unpack("<I", header)
    return conn._recv_exact(length)


conn = EVEConnection("127.0.0.1", 26000)
ve = conn.recv_rep()
conn.send_rep((L.EVE_BIRTHDAY, L.MACHONET_VERSION, ve[2],
               L.EVE_VERSION_NUMBER, L.EVE_BUILD_VERSION,
               L.EVE_PROJECT_VERSION))
conn.send_rep((None, "VK", "smoke-bot"))
conn.send_rep(("placebo", {}))
assert conn.recv_rep() == "OK CC"
conn.send_rep(("", {
    "macho_version": L.MACHONET_VERSION,
    "boot_version": L.EVE_VERSION_NUMBER,
    "boot_build": L.EVE_BUILD_VERSION,
    "boot_codename": L.EVE_PROJECT_CODENAME,
    "boot_region": L.EVE_PROJECT_REGION,
    "user_name": WStr("smokebot"),
    "user_password": WStr("smokebot"),
    "user_password_hash": "",
    "user_languageid": WStr("EN"),
    "user_affiliateid": 0,
}))
rep = conn.recv_rep()
if rep in (1, 2):
    rep = conn.recv_rep()
print("handshake type:", type(rep).__name__)
conn.send_rep(("55087", "", None))

raw = recv_raw(conn)
if raw[:1] == b"\x78":
    raw = zlib.decompress(raw)
print(f"ack payload: {len(raw)} bytes")
print(raw.hex())
try:
    print(evemarshal.loads(raw))
except Exception as e:
    print("DECODE FAILED:", e)
conn.close()

"""
EVE marshal decoding for the debug listener.

This module is now an adapter over the verified codec in
tools/smoke-bot/evemarshal.py — the implementation that has been
validated against a live EVEmu server (full login handshake, PackedRows,
string table). The previous standalone decoder had wire-format bugs that
made real frames undecodable:

  - no 0x7E stream-header / map-count handling (every frame rejected)
  - PyDict read key-then-value; the wire is value-then-key (LoadDict)
  - u8 sizes instead of SizeEx (0xFF + u32 extension)
  - PyPackedRow consumed the remainder of the stream
  - save-bit (0x40) not masked off opcodes
  - 1-based string table lookups unimplemented

Keep protocol logic in the shared codec; keep proxy/filter/printer UX
here. See tools/smoke-bot/README.md for the wire-format notes.
"""

import sys
from pathlib import Path

# tools/smoke-bot sits next to tools/debug-listener
_SMOKE_BOT = Path(__file__).resolve().parents[2] / "smoke-bot"
if str(_SMOKE_BOT) not in sys.path:
    sys.path.insert(0, str(_SMOKE_BOT))

import evemarshal as _codec  # noqa: E402  (tools/smoke-bot/evemarshal.py)

# Canonical API
loads = _codec.loads
dumps = _codec.dumps
MarshalError = _codec.MarshalError
WStr = _codec.WStr
Token = _codec.Token
SubStream = _codec.SubStream
ObjectEx = _codec.ObjectEx
PackedRow = _codec.PackedRow
STRING_TABLE = _codec.STRING_TABLE

# Legacy names used elsewhere in the debug listener
PyObject = _codec.PyObj
EVEUnmarshalError = _codec.MarshalError

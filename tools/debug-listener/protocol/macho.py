"""
MachoNet / PyPacket layer for EVE.

This module takes a decoded top-level PyRep (usually a tuple) and turns it
into a more readable PyPacket-like structure when possible.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Dict

from .evemarshal import PyObject, PackedRow


MACHONETMSG_TYPE_NAMES = {
    0: "AUTHENTICATION_REQ",
    1: "AUTHENTICATION_RSP",
    2: "IDENTIFICATION_REQ",
    3: "IDENTIFICATION_RSP",
    6: "CALL_REQ",
    7: "CALL_RSP",
    8: "TRANSPORTCLOSED",
    10: "RESOLVE_REQ",
    11: "RESOLVE_RSP",
    12: "NOTIFICATION",
    15: "ERRORRESPONSE",
    16: "SESSIONCHANGENOTIFICATION",
    18: "SESSIONINITIALSTATENOTIFICATION",
    20: "PING_REQ",
    21: "PING_RSP",
    100: "MOVEMENTNOTIFICATION",
}


@dataclass
class PyAddress:
    type: str
    object_id: Optional[int] = None
    call_id: Optional[int] = None
    service: Optional[str] = None
    raw: Any = None


@dataclass
class PyPacket:
    type: int
    type_name: str
    source: PyAddress
    dest: PyAddress
    userid: int = 0
    payload: Any = None
    named_payload: Dict[str, Any] = field(default_factory=dict)
    raw: Any = None   # original PyRep for debugging

    @property
    def is_call(self) -> bool:
        return self.type in (6, 7)

    @property
    def is_notification(self) -> bool:
        return self.type == 12

    def service_method(self) -> Optional[str]:
        """Try to extract 'service.method' for CALL packets."""
        if not self.is_call or not isinstance(self.payload, (list, tuple)):
            return None

        # Common layout for CALL_REQ:
        # payload[0] is often a tuple like (service, method, ...)
        # or the service is in dest.service
        if self.dest and self.dest.service:
            # Try to find method name in payload
            if len(self.payload) > 1 and isinstance(self.payload[1], (list, tuple)):
                method = self.payload[1][0] if self.payload[1] else "?"
                return f"{self.dest.service}.{method}"
            return self.dest.service

        # Fallback: look inside the tuple
        if self.payload and len(self.payload) > 0:
            first = self.payload[0]
            if isinstance(first, (list, tuple)) and len(first) >= 2:
                return f"{first[0]}.{first[1]}"
        return None


def _decode_address(rep: Any) -> PyAddress:
    if not isinstance(rep, (list, tuple)) or not rep:
        return PyAddress(type="Invalid", raw=rep)

    addr_type = rep[0]

    if addr_type == 2:  # Client
        return PyAddress(
            type="Client",
            object_id=rep[1] if len(rep) > 1 else None,
            call_id=rep[2] if len(rep) > 2 else None,
            service=rep[3] if len(rep) > 3 else None,
            raw=rep,
        )
    if addr_type == 1:  # Node
        return PyAddress(
            type="Node",
            object_id=rep[1] if len(rep) > 1 else None,
            service=rep[2] if len(rep) > 2 else None,
            call_id=rep[3] if len(rep) > 3 else None,
            raw=rep,
        )
    if addr_type == 4:  # Broadcast
        return PyAddress(
            type="Broadcast",
            service=str(rep[1]) if len(rep) > 1 else None,
            raw=rep,
        )
    if addr_type == 8:  # Any
        return PyAddress(
            type="Any",
            service=rep[1] if len(rep) > 1 else None,
            raw=rep,
        )

    return PyAddress(type=f"Unknown({addr_type})", raw=rep)


def decode_py_packet(top_level: Any) -> Optional[PyPacket]:
    """
    Try to interpret a decoded top-level object as a PyPacket.

    On the wire a PyPacket is PyObject(type_string, 7-tuple), optionally
    wrapped in a PySubStream (PyPacket::Encode/Decode in eve-common).
    The 7-tuple is (type, source, dest, userid, payload, named, contextKey).
    This function is intentionally tolerant.
    """
    # Unwrap SubStream and the macho.* PyObject envelope
    from .evemarshal import SubStream as _SubStream
    if isinstance(top_level, _SubStream):
        top_level = top_level.obj
    if isinstance(top_level, PyObject):
        top_level = top_level.state

    if not isinstance(top_level, (list, tuple)) or len(top_level) < 6:
        return None

    try:
        pkt_type = top_level[0]
        if not isinstance(pkt_type, int):
            return None

        source = _decode_address(top_level[1])
        dest = _decode_address(top_level[2])
        userid = top_level[3] if len(top_level) > 3 else 0
        payload = top_level[4] if len(top_level) > 4 else None
        named = top_level[5] if len(top_level) > 5 else {}

        return PyPacket(
            type=pkt_type,
            type_name=MACHONETMSG_TYPE_NAMES.get(pkt_type, f"UNKNOWN_{pkt_type}"),
            source=source,
            dest=dest,
            userid=userid,
            payload=payload,
            named_payload=named if isinstance(named, dict) else {},
            raw=top_level,
        )
    except Exception:
        return None


def summarize_packet(pkt: PyPacket) -> str:
    """Produce a short one-line summary suitable for logging."""
    if pkt.is_call:
        method = pkt.service_method() or "CALL"
        return f"{pkt.type_name}  {method}"
    if pkt.is_notification:
        # Try to guess notification name
        name = "?"
        if isinstance(pkt.payload, (list, tuple)) and pkt.payload:
            name = str(pkt.payload[0])[:60]
        return f"NOTIFICATION  {name}"
    return pkt.type_name
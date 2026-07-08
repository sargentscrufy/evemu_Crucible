"""
Pretty printing for decoded EVE packets.
"""

import pprint
from typing import Any

from .macho import PyPacket, summarize_packet
from .filter import PacketFilter


def format_direction(direction: str) -> str:
    # ASCII arrows: Windows consoles on legacy codepages can't print U+2192,
    # and a print() UnicodeEncodeError must never kill the proxy pipe.
    if direction.upper().startswith("C"):
        return "C->S"
    return "S->C"


def pretty_print_packet(
    direction: str,
    pkt: PyPacket,
    filter_engine: PacketFilter,
    max_arg_len: int = 120,
) -> str:
    direction_str = format_direction(direction)
    summary = summarize_packet(pkt)

    highlight = filter_engine.is_highlight(pkt)
    prefix = ">>> " if highlight else "    "

    lines = [f"{prefix}[{direction_str}] {summary}"]

    # Add a bit of payload context for interesting calls
    if pkt.is_call and pkt.payload:
        try:
            args = pkt.payload
            if isinstance(args, (list, tuple)) and len(args) > 1:
                # Try to show first few arguments nicely
                arg_summary = str(args[1])[:max_arg_len]
                lines.append(f"        args: {arg_summary}")
        except Exception:
            pass

    return "\n".join(lines)


def dump_tree(obj: Any, max_depth: int = 3) -> str:
    """Safe pretty print of a raw decoded tree."""
    try:
        return pprint.pformat(obj, depth=max_depth, compact=True, width=100)
    except Exception:
        return str(obj)[:500]
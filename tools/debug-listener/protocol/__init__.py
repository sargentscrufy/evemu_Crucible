"""
EVE Crucible Protocol Decoding Package

This package contains the low-level decoding logic for the EVE Online
MachoNet protocol as used by EvEmu (Crucible era).

Modules:
- framing: TCP length prefix + zlib handling
- evemarshal: EVE's custom Python marshal format
- macho: PyPacket / MachoNet layer
"""

from . import framing
from . import evemarshal
from . import macho

__all__ = ["framing", "evemarshal", "macho"]
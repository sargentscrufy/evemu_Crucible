"""
Framing layer for the EVE MachoNet protocol.

EVE uses a very simple length-prefixed framing on top of TCP:

    [ uint32 little-endian length ] [ length bytes of payload ]

The payload is usually zlib-compressed, followed by EVE's custom Python marshal.

This module provides:
- Frame extraction from a byte stream
- Compression / decompression helpers
"""

import struct
import zlib
from typing import Optional, Tuple


class EVEFramer:
    """
    Handles the EVE length-prefixed framing.

    Usage:
        framer = EVEFramer()
        framer.feed(data_from_socket)
        while True:
            frame = framer.pop_frame()
            if frame is None:
                break
            # process frame (usually compressed marshal data)
    """

    # EVEmu's PACKET_SIZE_LIMIT is 10MB; anything bigger means we lost
    # frame sync (bad length prefix), not a real frame.
    MAX_FRAME = 10 * 1024 * 1024

    def __init__(self):
        self._buffer = bytearray()
        self._min_header = 4
        self.desynced = False

    def feed(self, data: bytes) -> None:
        """Add new data received from the network."""
        if data:
            self._buffer.extend(data)

    def pop_frame(self) -> Optional[bytes]:
        """
        Try to extract one complete frame.

        Returns the raw payload (without the length prefix) or None if
        we don't have a complete frame yet.
        """
        if self.desynced or len(self._buffer) < self._min_header:
            return None

        # Read length (little endian uint32)
        length = struct.unpack_from("<I", self._buffer, 0)[0]

        if length > self.MAX_FRAME:
            # Lost sync — stop decoding this direction rather than waiting
            # forever for a frame that will never complete. Forwarding is
            # unaffected; the caller should log this once.
            self.desynced = True
            return None

        if length == 0:
            # Empty frame (rare but seen in some keepalives)
            del self._buffer[:4]
            return b""

        total_needed = 4 + length
        if len(self._buffer) < total_needed:
            return None

        # Extract payload
        payload = bytes(self._buffer[4:total_needed])
        del self._buffer[:total_needed]
        return payload

    def has_data(self) -> bool:
        return len(self._buffer) > 0

    def clear(self) -> None:
        self._buffer.clear()


def compress_payload(data: bytes, level: int = 6) -> bytes:
    """Compress using the same zlib settings EVE uses."""
    # EVE typically uses zlib with default window bits
    return zlib.compress(data, level)


def decompress_payload(data: bytes) -> bytes:
    """
    Decompress an EVE payload.

    EVE uses standard zlib. Some very small packets may be sent uncompressed.
    """
    if not data:
        return b""

    # Heuristic: if it doesn't look compressed, return as-is
    # (zlib compressed data usually starts with 0x78)
    if data[0] != 0x78:
        # Could be uncompressed or a different format (rare after handshake)
        return data

    try:
        return zlib.decompress(data)
    except zlib.error:
        # Fallback: return raw data so caller can still log hex
        return data


def is_likely_compressed(data: bytes) -> bool:
    """Quick check if data looks zlib compressed."""
    return len(data) > 2 and data[0] == 0x78
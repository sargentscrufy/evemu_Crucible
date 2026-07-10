"""
TCP transport for the EVE wire protocol.

Framing (EVETCPConnection.cpp): uint32 little-endian length + payload.
The payload is an EVE marshal stream, optionally zlib-deflated — the
server inflates only when the payload starts with the zlib magic
(IsDeflated / InflateUnmarshal), so sending uncompressed is valid.
"""

import socket
import struct
import zlib

import evemarshal


class ConnectionClosed(Exception):
    pass


class EVEConnection:
    def __init__(self, host: str, port: int, timeout: float = 15.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._rx = b""

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def send_rep(self, obj, compress: bool = False):
        payload = evemarshal.dumps(obj)
        if compress:
            deflated = zlib.compress(payload)
            if len(deflated) < len(payload):
                payload = deflated
        self.sock.sendall(struct.pack("<I", len(payload)) + payload)

    def recv_rep(self):
        header = self._recv_exact(4)
        (length,) = struct.unpack("<I", header)
        payload = self._recv_exact(length)
        return evemarshal.loads(payload)

    def _recv_exact(self, n: int) -> bytes:
        while len(self._rx) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionClosed("server closed connection")
            self._rx += chunk
        out, self._rx = self._rx[:n], self._rx[n:]
        return out

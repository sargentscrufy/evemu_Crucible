"""
Async MITM proxy for EVE traffic.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from .framing import EVEFramer, decompress_payload
from .evemarshal import loads
from .macho import decode_py_packet, PyPacket
from .filter import PacketFilter
from .printer import pretty_print_packet, dump_tree

logger = logging.getLogger("eve-debug-proxy")


class EveDebugProxy:
    def __init__(
        self,
        listen_host: str,
        listen_port: int,
        target_host: str,
        target_port: int,
        packet_filter: PacketFilter,
        log_raw_tree: bool = False,
        capture_dir: Optional[str] = None,
    ):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        self.packet_filter = packet_filter
        self.log_raw_tree = log_raw_tree
        self.capture_dir = Path(capture_dir) if capture_dir else None
        self._session_seq = 0

    async def handle_client(self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter):
        peer = client_writer.get_extra_info("peername")
        logger.info(f"Client connected from {peer}")

        try:
            server_reader, server_writer = await asyncio.open_connection(
                self.target_host, self.target_port
            )
        except Exception as e:
            logger.error(f"Failed to connect to target {self.target_host}:{self.target_port}: {e}")
            client_writer.close()
            return

        # Optional raw byte capture: everything is replayable offline even
        # if live decoding hits a bug.
        cap_c2s = cap_s2c = None
        if self.capture_dir:
            self.capture_dir.mkdir(parents=True, exist_ok=True)
            self._session_seq += 1
            stamp = time.strftime("%Y%m%d-%H%M%S")
            base = f"session-{stamp}-{self._session_seq:03d}"
            cap_c2s = open(self.capture_dir / f"{base}.c2s.bin", "wb")
            cap_s2c = open(self.capture_dir / f"{base}.s2c.bin", "wb")
            logger.info(f"Raw capture: {self.capture_dir / base}.*.bin")

        # Two tasks: client -> server and server -> client
        task1 = asyncio.create_task(
            self._pipe("C->S", client_reader, server_writer, cap_c2s)
        )
        task2 = asyncio.create_task(
            self._pipe("S->C", server_reader, client_writer, cap_s2c)
        )

        done, pending = await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()

        for cap in (cap_c2s, cap_s2c):
            if cap:
                cap.close()

        client_writer.close()
        server_writer.close()
        logger.info(f"Connection from {peer} closed")

    async def _pipe(self, direction: str, reader: asyncio.StreamReader,
                    writer: asyncio.StreamWriter, capture=None):
        framer = EVEFramer()
        desync_reported = False

        while True:
            try:
                data = await reader.read(65536)
                if not data:
                    break

                if capture:
                    capture.write(data)
                    capture.flush()

                framer.feed(data)
                if framer.desynced and not desync_reported:
                    desync_reported = True
                    logger.warning(
                        f"({direction}) frame desync — live decoding stopped "
                        f"for this direction; forwarding and raw capture "
                        f"continue")

                while True:
                    frame = framer.pop_frame()
                    if frame is None:
                        break

                    # Observation only — never let decode/print errors
                    # break the forwarding pipe.
                    try:
                        self._process_frame(direction, frame, writer)
                    except Exception as e:
                        logger.warning(f"frame processing error "
                                       f"({direction}): {e!r}")

                # Forward the original (possibly partial) data
                writer.write(data)
                await writer.drain()

            except Exception as e:
                # Visible at default log level: a broken pipe ends the
                # session, so the reason must not hide behind DEBUG.
                logger.warning(f"Pipe error ({direction}): {e!r}")
                break

    def _process_frame(self, direction: str, frame: bytes, writer: asyncio.StreamWriter):
        if not frame:
            return

        # Decompress
        try:
            decompressed = decompress_payload(frame)
        except Exception:
            decompressed = frame

        # Unmarshal. Decode failures must never break forwarding — log and
        # move on so the client session stays alive.
        try:
            tree = loads(decompressed)
        except Exception as e:
            logger.debug(f"[{direction}] undecodable frame "
                         f"({len(frame)} bytes): {e}")
            print(f"    [{direction}] <undecodable frame: {len(frame)} "
                  f"bytes> head={decompressed[:16].hex()}")
            return

        # Try to recognize as PyPacket
        pkt = decode_py_packet(tree)

        if pkt:
            if self.packet_filter.should_log(pkt, tree):
                print(pretty_print_packet(direction, pkt, self.packet_filter))
                if self.log_raw_tree:
                    print("    tree:", dump_tree(tree))
        else:
            # Unknown top-level structure — only log if we are in verbose/raw mode
            if self.log_raw_tree:
                print(f"[{direction}] <raw frame>")
                print("    ", dump_tree(tree)[:400])


async def run_proxy(
    listen_host: str,
    listen_port: int,
    target_host: str,
    target_port: int,
    packet_filter: PacketFilter,
    log_raw_tree: bool = False,
    capture_dir: Optional[str] = None,
):
    proxy = EveDebugProxy(
        listen_host, listen_port, target_host, target_port, packet_filter,
        log_raw_tree, capture_dir
    )

    server = await asyncio.start_server(
        proxy.handle_client, listen_host, listen_port
    )

    addr = server.sockets[0].getsockname()
    logger.info(f"EVE Debug Listener listening on {addr}")
    logger.info(f"Forwarding to {target_host}:{target_port}")

    async with server:
        await server.serve_forever()

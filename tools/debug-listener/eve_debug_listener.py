#!/usr/bin/env python3
"""
EVE Crucible Debug Listener

A purpose-built MITM proxy and decoder for the EVE Online network protocol
as used by EvEmu (Crucible era).

See README.md for full documentation and usage.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add local protocol directory to path when run directly
sys.path.insert(0, str(Path(__file__).parent))

from protocol.filter import FilterConfig, PacketFilter
from protocol.proxy import run_proxy


def load_filter_config(path: str) -> PacketFilter:
    """Load filter rules. Falls back to sensible defaults."""
    try:
        import yaml
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        cfg = FilterConfig(**data)
        return PacketFilter(cfg)
    except Exception as e:
        print(f"[!] Could not load filter config '{path}': {e}")
        print("[!] Using built-in default filters.")
        return PacketFilter(FilterConfig.default())


def main():
    parser = argparse.ArgumentParser(
        description="EVE Crucible Protocol Debug Listener (MITM proxy + decoder)"
    )
    parser.add_argument("--listen", default="127.0.0.1:26001",
                        help="Address to listen on (default 127.0.0.1:26001)")
    parser.add_argument("--target", default="127.0.0.1:26000",
                        help="Real EvEmu server address (default 127.0.0.1:26000)")
    parser.add_argument("--filter-config", default="config/filter_rules.yaml",
                        help="Path to filter rules YAML")
    parser.add_argument("--log-raw-tree", action="store_true",
                        help="Also dump raw decoded trees (very verbose)")
    parser.add_argument("--capture-dir", default=None,
                        help="Write raw per-session byte captures "
                             "(*.c2s.bin / *.s2c.bin) to this directory")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Parse host:port
    def parse_addr(s):
        host, port = s.rsplit(":", 1)
        return host, int(port)

    listen_host, listen_port = parse_addr(args.listen)
    target_host, target_port = parse_addr(args.target)

    # Filters
    packet_filter = load_filter_config(args.filter_config)

    print("=== EVE Crucible Debug Listener ===")
    print(f"Listening on {listen_host}:{listen_port}")
    print(f"Forwarding to  {target_host}:{target_port}")
    print("Press Ctrl+C to stop.\n")

    try:
        asyncio.run(
            run_proxy(
                listen_host, listen_port,
                target_host, target_port,
                packet_filter,
                log_raw_tree=args.log_raw_tree,
                capture_dir=args.capture_dir,
            )
        )
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()

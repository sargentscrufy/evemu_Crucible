#!/usr/bin/env python3
"""
EVEmu smoke test — Phase 1 CI harness.

Connects to a running EVEmu server, performs the full Crucible login
handshake, and verifies the session reaches PyPacket mode. Exits 0 on
pass, 1 on failure, so it can gate CI and docker healthchecks.

Usage:
    python smoke_test.py [--host 127.0.0.1] [--port 26000]
                         [--user smokebot] [--password smokebot]

Account note: EVEmu auto-creates unknown accounts when
sConfig.account.autoAccountRole > 0 (the default docker config enables
this), so the bot account appears on first run.
"""

import argparse
import sys
import time

import login as eve_login


def main() -> int:
    ap = argparse.ArgumentParser(description="EVEmu login smoke test")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=26000)
    ap.add_argument("--user", default="smokebot")
    ap.add_argument("--password", default="smokebot")
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--retries", type=int, default=1,
                    help="connection attempts (server may still be booting)")
    ap.add_argument("--retry-delay", type=float, default=10.0)
    args = ap.parse_args()

    last_err = None
    for attempt in range(1, args.retries + 1):
        try:
            return run(args)
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            last_err = e
            print(f"[..] attempt {attempt}/{args.retries} failed: {e}")
            if attempt < args.retries:
                time.sleep(args.retry_delay)
    print(f"FAIL: could not connect: {last_err}")
    return 1


def run(args) -> int:
    print(f"[->] connecting to {args.host}:{args.port} as {args.user!r}")
    try:
        conn, info = eve_login.login(args.host, args.port,
                                     args.user, args.password,
                                     timeout=args.timeout)
    except eve_login.LoginRefused as e:
        print(f"FAIL: server refused login: {e}")
        return 1
    except eve_login.LoginError as e:
        print(f"FAIL: handshake error: {e}")
        return 1

    with_conn = True
    try:
        if info.user_id <= 0:
            print(f"FAIL: no userid in handshake ack: {info.raw_ack!r}")
            return 1
        print(f"PASS: authenticated as userid {info.user_id} "
              f"(role 0x{info.role:X}); session reached packet mode")
        return 0
    finally:
        if with_conn:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())

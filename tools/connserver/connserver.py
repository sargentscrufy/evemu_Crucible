#!/usr/bin/env python3
"""
EVEmu connection server -- the single publicly exposed contact point of
the server stack.  Terminates client TCP and relays raw bytes to the
internal game server (and image server), so the game server itself never
faces the internet.

Deliberately protocol-agnostic in v1 (pure byte relay): zero coupling to
the wire format means the game server can change freely behind it.  The
separation seam is configuration only -- point UPSTREAM_HOST at any
reachable game server and run this container anywhere (same compose, a
different box, a DMZ) with no code change.  v2 evolution path: become
the protocol-aware reactor that terminates thousands of client sockets
and multiplexes them to the game server over a few internal pipes
(the thread-per-connection scale fix in doc/transport-population-plan.md).

Env:
  UPSTREAM_HOST      internal game server host   (default: server)
  GAME_PORT          game port                    (default: 26000)
  IMAGE_PORT         image/portrait http port     (default: 26001)
  LISTEN_HOST        bind address                 (default: 0.0.0.0)
  MAX_CONNS          global concurrent cap        (default: 1500)
  MAX_CONNS_PER_IP   per-address cap              (default: 60)
  IDLE_TIMEOUT_S     drop silent connections      (default: 900)

Stats line every 60s; one log line per connect/disconnect.
"""

import asyncio
import collections
import os
import time

UPSTREAM = os.environ.get("UPSTREAM_HOST", "server")
GAME_PORT = int(os.environ.get("GAME_PORT", "26000"))
IMAGE_PORT = int(os.environ.get("IMAGE_PORT", "26001"))
LISTEN = os.environ.get("LISTEN_HOST", "0.0.0.0")
MAX_CONNS = int(os.environ.get("MAX_CONNS", "1500"))
MAX_PER_IP = int(os.environ.get("MAX_CONNS_PER_IP", "60"))
IDLE_TIMEOUT = float(os.environ.get("IDLE_TIMEOUT_S", "900"))

BUF = 65536

conns = 0
per_ip = collections.Counter()
totals = {"accepted": 0, "refused": 0, "bytes_in": 0, "bytes_out": 0}


def log(msg):
    print(f"[connsrv] {time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


async def pipe(reader, writer, counter_key, activity):
    try:
        while True:
            data = await reader.read(BUF)
            if not data:
                break
            activity[0] = time.time()
            totals[counter_key] += len(data)
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError, OSError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def handle(client_r, client_w, port, label):
    global conns
    peer = client_w.get_extra_info("peername") or ("?", 0)
    ip = peer[0]
    if conns >= MAX_CONNS or per_ip[ip] >= MAX_PER_IP:
        totals["refused"] += 1
        log(f"REFUSED {ip} ({label}) conns={conns} ip_conns={per_ip[ip]}")
        client_w.close()
        return
    try:
        up_r, up_w = await asyncio.wait_for(
            asyncio.open_connection(UPSTREAM, port), timeout=10)
    except (OSError, asyncio.TimeoutError) as e:
        log(f"UPSTREAM DOWN for {ip} ({label}): {e}")
        client_w.close()
        return

    conns += 1
    per_ip[ip] += 1
    totals["accepted"] += 1
    log(f"OPEN {ip} -> {label} (conns={conns})")
    activity = [time.time()]
    t1 = asyncio.create_task(pipe(client_r, up_w, "bytes_in", activity))
    t2 = asyncio.create_task(pipe(up_r, client_w, "bytes_out", activity))
    try:
        while not (t1.done() and t2.done()):
            await asyncio.sleep(5)
            if time.time() - activity[0] > IDLE_TIMEOUT:
                log(f"IDLE-DROP {ip} ({label})")
                break
    finally:
        for t in (t1, t2):
            t.cancel()
        for w in (client_w, up_w):
            try:
                w.close()
            except Exception:
                pass
        conns -= 1
        per_ip[ip] -= 1
        if per_ip[ip] <= 0:
            del per_ip[ip]
        log(f"CLOSE {ip} ({label}) (conns={conns})")


async def stats():
    while True:
        await asyncio.sleep(60)
        log(f"STATS conns={conns} accepted={totals['accepted']} "
            f"refused={totals['refused']} in={totals['bytes_in']} "
            f"out={totals['bytes_out']}")


async def main():
    game = await asyncio.start_server(
        lambda r, w: handle(r, w, GAME_PORT, "game"), LISTEN, GAME_PORT)
    image = await asyncio.start_server(
        lambda r, w: handle(r, w, IMAGE_PORT, "image"), LISTEN, IMAGE_PORT)
    log(f"listening on {LISTEN}:{GAME_PORT} (game) and :{IMAGE_PORT} "
        f"(image), upstream {UPSTREAM}")
    asyncio.create_task(stats())
    async with game, image:
        await asyncio.gather(game.serve_forever(), image.serve_forever())


if __name__ == "__main__":
    asyncio.run(main())

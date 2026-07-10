# EVEmu Smoke Bot

Headless protocol client for EVEmu (Crucible v1.6.5, build 360229). Phase 1
artifact from [plan.md](../../plan.md): it is both the CI stability harness
and the foundation for Tier-2 NPC player characters (Phase 3).

Pure Python 3 stdlib — no dependencies.

## What it does today

Performs the complete login handshake against a running server and verifies
the session reaches PyPacket mode:

```
version exchange → VK command → placebo crypto → credential challenge
→ server handshake → handshake result → ack (session established)
```

Exit code 0 on pass, 1 on any failure, so it can gate CI.

```
python smoke_test.py [--host 127.0.0.1] [--port 26000]
                     [--user smokebot] [--password smokebot]
                     [--retries 3] [--retry-delay 10]
```

The account is auto-created on first login (requires
`sConfig.account.autoAccountRole > 0`, enabled in the default docker config).
Auth uses the plain-password path of `Client::_VerifyLogin`.

## Files

- `evemarshal.py` — EVE marshal codec (encode + decode), written from the
  server source. Notable wire facts encoded here:
  - stream prelude `0x7E` + uint32 map-count (always 0)
  - `PyDict` entries marshal **value first, then key** (`LoadDict`)
  - `PyObjectEx` inner dict is **key first** (`LoadObjectEx`) — opposite
  - sizes are u8, or `0xFF` + u32 ("SizeEx")
  - `PyPackedRow` = descriptor + SizeEx RLE buffer + one trailing rep per
    BYTES/STR/WSTR column (fixed fields are consumed, not yet unpacked)
  - 195-entry marshal string table, 1-based indices
- `netclient.py` — uint32-LE length framing over TCP; zlib inflation
- `login.py` — handshake state machine (mirrors `EVESession.cpp`)
- `smoke_test.py` — CLI entry point / CI gate
- `debug_ack.py` — replays login and hex-dumps the handshake ack; keep for
  protocol debugging

## Roadmap (Phase 1 → 3)

1. ~~Login handshake~~ ✅
2. Character creation + character select (macho CallReq to services)
3. Undock → warp → dock loop (the Tier-1 exit criterion in the feature matrix)
4. Long-running soak mode (repeat loop, report crashes/disconnects)
5. Generalize into the bot framework the AI Director drives (Phase 3)

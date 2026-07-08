# EVE Crucible Debug Listener

**Purpose-built network traffic debugger for EvEmu + Crucible client.**

This tool sits between the EVE Online Crucible client and an EvEmu server. It decodes the MachoNet + Python-marshaled protocol and produces clean, filterable logs focused on *game-relevant* traffic.

## Goals

- Only log traffic that is meaningful for reverse-engineering, feature implementation, or debugging EvEmu.
- Suppress "well understood" / noisy traffic (bulk cache loads, object caching, pings, many keep-alive style calls, etc.).
- Be a **standalone** tool — does not require building the full EvEmu project.
- Excellent documentation and easy to extend.

## How It Works (High Level)

The EVE wire protocol has these layers:

1. **TCP framing** — `uint32 length | payload`
2. **Compression + Marshal** — zlib + EVE's custom Python marshal format (`PyRep`)
3. **MachoNet** — `PyPacket` containing `type`, `source`, `dest`, and a `payload`
4. **Game layer** — `CALL_REQ` / `CALL_RSP` to named services, `NOTIFICATION`s, `SESSIONCHANGENOTIFICATION`, Destiny updates, etc.

This tool:
- Acts as a transparent TCP MITM proxy.
- Parses the framing.
- Decompresses.
- Unmarshals into a Python representation of the PyRep tree.
- Recognizes `PyPacket` structure when possible.
- Applies smart filters.
- Pretty-prints the interesting parts (service name + method for calls, important arguments, etc.).

## Usage

### Basic Proxy Mode (Recommended)

```bash
python eve_debug_listener.py \
    --listen 0.0.0.0:26001 \
    --target 127.0.0.1:26000 \
    --config config/filter_rules.yaml
```

Then point your Crucible client at `127.0.0.1:26001` instead of the normal server port.

### Command Line Options

- `--listen HOST:PORT` — where clients should connect (default 127.0.0.1:26001)
- `--target HOST:PORT` — the real EvEmu server (default 127.0.0.1:26000)
- `--log-dir logs/` — where to write session logs
- `--filter-config path/to/rules.yaml`
- `--raw` — also dump raw hex for every packet (very noisy)
- `--no-color`
- `--verbose` / `--quiet`

### Filtering Philosophy

The default configuration is tuned to be **quiet but useful**:

**Ignored by default (well-understood / high volume):**
- Most `ObjectCaching` calls
- Bulk data / cache loads (`GetCachableObject`, many `Get` methods on cache services)
- Ping / keepalive traffic
- Low-level session maintenance after initial handshake
- Many `dogmaim` attribute queries during fitting (can be re-enabled when working on dogma)
- Large `util.Rowset` / `util.Row` dumps unless they look like interesting game data

**Highlighted / Always Logged:**
- Market orders, transactions
- Agent interactions / missions
- Destiny movement and state
- Ship module activations (`Activate`, `Deactivate`, `Overload`, etc.)
- LSC (Local, corp, fleet chat)
- Inventory changes that are not pure cache
- Fleet operations
- Sovereignty, POS, PI when relevant
- Any error responses
- Session changes that affect the player state

You control this via `config/filter_rules.yaml`.

## Configuration (`filter_rules.yaml`)

Example structure (see `config/filter_rules.yaml` for the real one):

```yaml
ignore_services:
  - objectCaching
  - bulkMgr
  - photo
  - ".*Cache"

always_log_services:
  - marketProxy
  - agentMgr
  - beyonce
  - dogma

interesting_methods:
  - PlaceBuyOrder
  - PlaceSellOrder
  - Activate
  - WarpTo
  - GetMyJournalDetails

ignore_if_contains:
  - GetInventory
  - GetItem

highlight_keywords:
  - "error"
  - "exception"
```

Rules are applied in order. The tool is designed so you can quickly add new ignores/highlights while debugging a specific feature.

## Output Example

```
[ C→S ] CALL_REQ  marketProxy.PlaceBuyOrder
    stationID: 60003760
    typeID: 34
    quantity: 10000
    price: 4.20
    ...

[ S→C ] NOTIFICATION  OnOwnOrderChanged
    ...

[ S→C ] NOTIFICATION  OnGodmaUpdate
    (dogma attribute change - truncated unless --verbose)
```

## Architecture of the Tool

```
eve_debug_listener.py
├── proxy.py                 # asyncio MITM proxy
├── framing.py               # length-prefixed + zlib handling
├── evemarshal.py            # EVE Python marshal unmarshaler (core)
├── macho.py                 # PyPacket + PyAddress decoding
├── filter.py                # service/method based filtering engine
├── printer.py               # pretty, colored, structured output
└── config.py
```

The marshal decoder (`evemarshal.py`) is the most important piece for correctness. It implements the opcodes from `EVEMarshalOpcodes.h`.

## Development Notes

### Adding Support for New Packet Types

1. Look at the raw decoded PyRep tree (run with `--raw-tree` during development).
2. Add recognition logic in `macho.py` or a higher layer.
3. Add filter rules.

### Reusing Knowledge from EvEmu

- `src/eve-common/marshal/EVEMarshalOpcodes.h`
- `src/eve-common/python/PyPacket.h` + `PyPacket.cpp`
- `src/eve-common/packets/*.xmlp` (service definitions)
- `src/eve-server/services/` (what methods actually exist)

### Limitations (v1)

- Full MachoNet crypto handshake is passed through but not deeply interpreted (decoding usually becomes reliable after `SESSIONINITIALSTATENOTIFICATION`).
- Some complex `PyObjectEx` / `PyPackedRow` structures are shown as raw trees until more visitors are written.
- Does not currently do live modification (only logging).

## Why Not Just Use Wireshark / tcpdump?

Because:
- Everything after the handshake is compressed + custom marshaled.
- You need deep understanding of the PyRep format + MachoNet to make sense of it.
- Filtering "well understood" traffic at the semantic level (by service/method) is extremely valuable when implementing features.

This tool turns the firehose into something usable.

## Running Against a Real EvEmu Instance

1. Start your EvEmu server normally (`docker compose up` or native).
2. Run this listener pointing at the server's port.
3. Configure the EVE client to connect to the listener's port (edit `common.ini` or use a launcher that supports custom server).
4. Log in and play. Watch the interesting traffic only.

## Contributing / Extending

When you discover a new "noisy but boring" call while working on a feature, add it to the filter rules and commit the updated config. This benefits everyone doing protocol work.

---

**This is a purpose-built tool for EvEmu development on the Crucible era client.** Keep it focused, keep the noise low, and make reverse engineering pleasant.
# Admin API Seam — Technical Design (Phase 2)

**Status:** Draft for review. No code yet.
**Goal:** One small, privileged HTTP + WebSocket surface inside `eve-server` that the external web GUI (and later the AI Director) uses for control and observation. Everything else — dashboards, maps, history — lives in the separate web app reading MariaDB directly.

## Constraints discovered in the code

1. **`CommandDispatcher::Execute(Client* from, const char* msg)` requires a live `Client*`** (`src/eve-server/admin/CommandDispatcher.h`). GM command handlers dereference `who` for system context, target resolution, and reply notifications. There is no null-client path today.
2. **The stdin console (`ConsoleCommands`) does not use CommandDispatcher** for game commands — it implements its own small hardcoded set (status, broadcast, shutdown, etc.) and only calls `ListCommands()`. So there is no existing "command without a client" precedent to copy; the console's own command set is the precedent for *client-free* server controls.
3. The server is single-threaded; anything the API touches must either be done on the main loop thread or be trivially thread-safe.

## Architecture

```
web GUI / AI Director
        │  HTTPS/WS (token auth)
        ▼
AdminAPI listener (own thread, small embedded HTTP+WS lib)
        │  lock-free queue of AdminRequest
        ▼
AdminAPI::Process()  ← called once per tick from the main loop
        │                (same pattern as sConsole.Process())
        ├── console-class commands (status, broadcast, config, shutdown)
        ├── CommandDispatcher commands (require an executor Client*)
        └── responses posted back to the listener thread
```

- **Threading rule:** the listener thread only parses/authenticates and enqueues. All game-state access happens inside `AdminAPI::Process()` on the main thread. Responses go back over a queue. This keeps the fragile core single-threaded semantics intact.
- **Library:** one small embedded HTTP/WS library (civetweb or similar, vendored under `dep/`). No boost::beast — keep the dependency tiny and auditable.

## Command execution: the Client* problem

Three classes of command, phased:

| Class | Executor | Availability |
|---|---|---|
| **A. Console-class** (status, broadcast, live config set, halt) | none needed | Phase 2, day one |
| **B. Dispatcher commands** (`/spawn`, `/tp`, standing changes, ...) | an **online GM client** — the API executes `Execute(gmClient, msg)` where `gmClient` is a designated logged-in character | Phase 2, works whenever a GM character is online |
| **C. Dispatcher commands, always-on** | a **persistent headless GM session**: the Phase 1/3 bot framework keeps one GM bot logged in as the standard executor | Phase 3 |

Class B/C requests name the executor character; if it is not online the API returns a clear error rather than attempting a null-client call. We do **not** audit/patch every command for null safety — that is the expensive, crash-prone path.

## Endpoints (v1)

- `GET /admin/v1/health` — liveness + tick metrics `{uptime, tickMs, players, systemsLoaded}`. Unauthenticated-safe subset for docker healthcheck.
- `GET /admin/v1/status` — full snapshot: what `ConsoleCommands::UpdateStatus()` + `StatisticMgr` collect.
- `GET /admin/v1/commands` — dump `CommandDispatcher::GetCommandList()` (name, description, required role) so the GUI self-populates.
- `POST /admin/v1/command` — `{class: "console"|"dispatcher", executor?: charID, cmd: "/spawn ..."}` → result or structured error.
- `GET /admin/v1/config` / `PATCH /admin/v1/config` — read and live-tune the `sConfig` values already supported by `LiveUpdateDB`.
- `WS /admin/v1/logs` — streaming log tail (tap the `sLog` sinks; ring buffer on the listener thread).
- `WS /admin/v1/events` — server events (client connect/disconnect, system load/unload, crash-relevant warnings) for the GUI and the Director.

## Auth

- Static bearer token from `eve-server.xml` (new `<adminApi>` block: enabled flag, bind address, port, token). Bind to `127.0.0.1`/docker network by default; the web GUI's backend is the only intended caller. TLS optional (private LAN); do not expose to WAN.

## Tick-budget exposure (for the AI Director)

`/health` includes rolling average and p95 of main-loop tick duration. The Director's contract: if `tickMs.p95` exceeds a configured budget, it must reduce live bot count. This is the backpressure mechanism named in plan.md's risks.

## Non-goals

- Serving the GUI's static assets from the C++ process.
- A general RPC surface into game internals — only the enumerated endpoints.
- Multi-user/RBAC — one token, private server.

## Open questions for implementation

1. Which log sink to tap for the WS stream — `sLog` writes to console/file; cleanest is an additional registered sink with its own ring buffer.
2. Whether `LiveUpdateDB` covers enough of `sConfig` for useful live tuning, or needs extending (audit during Phase 2).
3. civetweb vs. alternatives — decide at implementation start; requirement is HTTP/1.1 + WS + no heavyweight transitive deps.

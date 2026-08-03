# Docker ops (this machine only)

**Not product. Not shipping.** Host scaffolding for a Windows box whose only
job is running EVEmu under Docker Desktop while we sort Desktop/WSL stability.

**Privacy:** never commit personal account names/passwords. See [PRIVACY.md](PRIVACY.md).
`backup/` and `logs/` are gitignored (dumps can contain password hashes).

| Keep | Remove when stable |
|---|---|
| `start-docker.ps1` — bring stack up after a reboot | Watchdog + scheduled task |
| `docker-lib.ps1` / `recover-docker.ps1` — manual recover if needed | Continuous poll loop |
| `backup/` — DB dumps | Chatty “heartbeat” logs (already removed) |

## Do we need a continuous monitor?

**No — not for diagnosis, and not long term.**

| Need | How |
|---|---|
| **Diagnose** a death | Failure lines in `logs/docker-ops.log` + Desktop backend log under `%LOCALAPPDATA%\Docker\log\host\` at the timestamp of the drop. Heartbeats add nothing. |
| **Recover** after death | One-shot: `recover-docker.ps1 -Level full` or `start-docker.ps1`. |
| **While Desktop is still flaky** | Optional watchdog (below) so the stack comes back without babysitting — temporary external guardrail only. |

The watchdog is **not** an EVEmu feature, not a production HA design, and not a
substitute for fixing or leaving Docker Desktop. It is a **dev-host safety net**
until the runtime is trustworthy (stable Desktop, or engine-in-WSL / Linux host).

## Temporary watchdog (optional, now)

- Polls quietly; **logs only on failure / recovery** (no periodic “all ok” spam).
- L1 (proxy) inline; L2/L3 in a **separate process** so the loop never blocks.
- Scheduled task `EvemuDockerWatchdog` (logon + every 15 min) only restarts the
  loop if it died; single-instance.

```powershell
# Optional while diagnosing Desktop flakiness
pwsh -File tools\ops\start-watchdog.ps1
pwsh -File tools\ops\install-watchdog-task.ps1

# When Docker is solid — tear the scaffold down
pwsh -File tools\ops\install-watchdog-task.ps1 -Remove
# stop any running loop via Task Manager or delete logs\docker-watchdog.lock after killing the process
```

## Bring-up / one-shot recover

```powershell
pwsh -File tools\ops\start-docker.ps1              # stack only
pwsh -File tools\ops\start-docker.ps1 -Watchdog    # stack + temp loop
pwsh -File tools\ops\recover-docker.ps1 -Level full
pwsh -File tools\ops\recover-docker.ps1 -Level full-wsl
```

Client: `serverName` = `127.0.0.1` (capture proxy **26000** → game **26010**).

## 2026-08-02 reset (context)

Uninstalled Desktop 4.83, wiped WSL/Docker data, installed **4.84.0 (234817)**,
`compose build --no-cache`, restored DB. Details: `backup/REBUILD-NOTES.md`.

## Logs (when something dies)

| File | Use |
|---|---|
| `logs/docker-ops.log` | What recovery did (stop/clear/start/compose) |
| `logs/docker-watchdog.log` | When the loop noticed failure / spawned recover |
| Desktop backend log | Root-cause timestamps (`%LOCALAPPDATA%\Docker\log\host\`) |

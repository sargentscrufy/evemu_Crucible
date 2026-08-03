# start-docker.ps1 -- repair-and-launch for Docker Desktop on this dev box.
#
# See docker-lib.ps1 for the failure modes we defend against (AF_UNIX socket
# crash-loop, stuck auto-update prepare, WSL remount flakes, dead :26000 proxy).
#
#   powershell -ExecutionPolicy Bypass -File tools\ops\start-docker.ps1
#   powershell -ExecutionPolicy Bypass -File tools\ops\start-docker.ps1 -Watchdog

param(
    [switch]$Watchdog,  # start non-blocking heal loop after recovery
    [switch]$InstallTask  # also register the logon/15min scheduled task
)

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "docker-lib.ps1")

Write-Host "== EVEmu Docker start (hardened, non-blocking watchdog available)"
$ok = Repair-DockerFull -EngineTimeoutSec 240
if (-not $ok) {
    Write-Host "first full recovery failed; retrying with wsl --shutdown"
    $ok = Repair-DockerFull -EngineTimeoutSec 240 -UseWslShutdown
}
if (-not $ok) {
    Write-Host "FAILED: full recovery did not bring engine + stack + proxy healthy"
    Write-Host "  check tools\ops\logs\docker-ops.log and Docker Desktop UI"
    exit 1
}

$report = Get-DockerHealthReport
Write-Host "== health: engine=$($report.EngineOk) server=$($report.ServerUp) proxy26000=$($report.Proxy26000) game26010=$($report.GamePort26010)"
if ($report.Containers) {
    foreach ($k in @($report.Containers.Keys)) {
        Write-Host ("   {0}: {1}" -f $k, $report.Containers[$k])
    }
}

if ($Watchdog) {
    Write-Host "== starting background watchdog"
    & (Join-Path $PSScriptRoot "start-watchdog.ps1")
}
if ($InstallTask) {
    Write-Host "== registering scheduled task"
    & (Join-Path $PSScriptRoot "install-watchdog-task.ps1")
}

Write-Host "== done -- client connects to 127.0.0.1:26000 (proxy -> 26010)"
exit 0

# recover-docker.ps1 -- one-shot recovery worker (spawned by the watchdog).
#
# Levels: soft | full | full-wsl
# Writes tools/ops/logs/recovery.lock while running; removed on exit.
#
#   pwsh -File tools\ops\recover-docker.ps1 -Level soft
#   pwsh -File tools\ops\recover-docker.ps1 -Level full
#   pwsh -File tools\ops\recover-docker.ps1 -Level full-wsl

param(
    [ValidateSet("soft","full","full-wsl")]
    [string]$Level = "full"
)

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "docker-lib.ps1")

$lockPath = Join-Path $PSScriptRoot "logs\recovery.lock"
try {
    if (-not (Test-Path (Split-Path $lockPath))) {
        New-Item -ItemType Directory -Path (Split-Path $lockPath) -Force | Out-Null
    }
    Set-Content -Path $lockPath -Value ("{0}|{1}|{2}" -f $PID, $Level, (Get-Date -Format o)) -Encoding ASCII
} catch {}

$ok = $false
try {
    Write-DockerLog "recover-docker worker start level=$Level pid=$PID"
    switch ($Level) {
        "soft"     { $ok = Repair-DockerSoft }
        "full"     { $ok = Repair-DockerFull -UseWslShutdown:$false }
        "full-wsl" { $ok = Repair-DockerFull -UseWslShutdown }
    }
    Write-DockerLog "recover-docker worker done level=$Level ok=$ok"
} catch {
    Write-DockerLog "recover-docker worker exception: $($_.Exception.Message)" "ERROR"
    $ok = $false
} finally {
    try { Remove-Item $lockPath -Force -ErrorAction SilentlyContinue } catch {}
}

if ($ok) { exit 0 } else { exit 2 }

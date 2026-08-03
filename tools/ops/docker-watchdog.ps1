# docker-watchdog.ps1 -- TEMPORARY host-side scaffold (NOT product / not shipping).
#
# Purpose: keep this single-purpose Windows Docker Desktop install usable while
# we diagnose Desktop/WSL flakiness. Logs failures and recoveries only — not a
# "heartbeat product". Remove the scheduled task + this loop once Desktop is
# stable or EVEmu moves off Docker Desktop.
#
# Design: L2/L3 recovery runs in a separate process (recover-docker.ps1) so this
# loop never freezes for minutes. Stale recovery locks are abandoned.
#
#   pwsh -File tools\ops\docker-watchdog.ps1
#   pwsh -File tools\ops\docker-watchdog.ps1 -IntervalSec 5

param(
    [int]$IntervalSec = 5,
    [int]$ConfirmDeadSec = 2,         # second sample before L3
    [int]$MinSecondsBetweenFull = 60,
    [int]$RecoveryStaleSec = 300,     # abandon hung recovery worker
    [switch]$Once
)

$ErrorActionPreference = "Continue"
trap {
    try {
        $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $line = "[$ts] [TRAP] $($_.Exception.Message)"
        Write-Host $line
        $logDir = Join-Path $PSScriptRoot "logs"
        if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
        Add-Content -Path (Join-Path $logDir "docker-watchdog.log") -Value $line -ErrorAction SilentlyContinue
    } catch {}
    continue
}

. (Join-Path $PSScriptRoot "docker-lib.ps1")

$lockPath     = Join-Path $PSScriptRoot "logs\docker-watchdog.lock"
$recoveryLock = Join-Path $PSScriptRoot "logs\recovery.lock"
$wdLog        = Join-Path $PSScriptRoot "logs\docker-watchdog.log"
$shell        = (Get-Process -Id $PID).Path
if (-not $shell) { $shell = "C:\Program Files\PowerShell\7\pwsh.exe" }

function Write-WatchLog {
    param([string]$Message, [string]$Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"
    try { Write-Host $line } catch {}
    try {
        $dir = Split-Path $wdLog
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Add-Content -Path $wdLog -Value $line -ErrorAction SilentlyContinue
        $item = Get-Item $wdLog -ErrorAction SilentlyContinue
        if ($item -and $item.Length -gt 2MB) {
            Move-Item $wdLog (Join-Path $dir ("docker-watchdog.{0}.log" -f (Get-Date -Format yyyyMMdd-HHmmss))) -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}

function Test-WatchdogLock {
    try {
        if (-not (Test-Path $lockPath)) { return $false }
        $pidText = (Get-Content $lockPath -Raw -ErrorAction SilentlyContinue).Trim()
        $otherId = 0
        if (-not [int]::TryParse($pidText, [ref]$otherId)) {
            Remove-Item $lockPath -Force -ErrorAction SilentlyContinue
            return $false
        }
        if ($otherId -eq $PID) { return $false }
        if (Get-Process -Id $otherId -ErrorAction SilentlyContinue) {
            Write-WatchLog "another watchdog already running (pid $otherId); exiting"
            return $true
        }
        Remove-Item $lockPath -Force -ErrorAction SilentlyContinue
        return $false
    } catch { return $false }
}

function Set-WatchdogLock {
    try {
        $dir = Split-Path $lockPath
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Set-Content -Path $lockPath -Value "$PID" -Encoding ASCII
    } catch {}
}

function Clear-WatchdogLock {
    try {
        if (Test-Path $lockPath) {
            $t = (Get-Content $lockPath -Raw -ErrorAction SilentlyContinue).Trim()
            if ($t -eq "$PID") { Remove-Item $lockPath -Force -ErrorAction SilentlyContinue }
        }
    } catch {}
}

function Get-RecoveryState {
    # Returns: None | Running | Stale
    try {
        if (-not (Test-Path $recoveryLock)) { return "None" }
        $raw = (Get-Content $recoveryLock -Raw -ErrorAction SilentlyContinue).Trim()
        $parts = $raw -split '\|'
        $rid = 0
        [void][int]::TryParse($parts[0], [ref]$rid)
        if ($rid -gt 0 -and (Get-Process -Id $rid -ErrorAction SilentlyContinue)) {
            return "Running"
        }
        # Process gone: check age
        $age = ((Get-Date) - (Get-Item $recoveryLock).LastWriteTime).TotalSeconds
        if ($age -gt $RecoveryStaleSec) {
            Remove-Item $recoveryLock -Force -ErrorAction SilentlyContinue
            return "Stale"
        }
        # Worker finished very recently; treat as None so we re-evaluate health.
        Remove-Item $recoveryLock -Force -ErrorAction SilentlyContinue
        return "None"
    } catch {
        try { Remove-Item $recoveryLock -Force -ErrorAction SilentlyContinue } catch {}
        return "None"
    }
}

function Start-RecoveryWorker {
    param([ValidateSet("soft","full","full-wsl")][string]$Level)
    $state = Get-RecoveryState
    if ($state -eq "Running") {
        Write-WatchLog "recovery already running; skip spawn level=$Level"
        return
    }
    $recover = Join-Path $PSScriptRoot "recover-docker.ps1"
    Write-WatchLog "spawning recovery worker level=$Level"
    try {
        Start-Process -FilePath $shell `
            -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-File",$recover,"-Level",$Level) `
            -WorkingDirectory $PSScriptRoot `
            -WindowStyle Minimized | Out-Null
    } catch {
        Write-WatchLog "spawn recovery failed: $($_.Exception.Message)" "ERROR"
    }
}

if (Test-WatchdogLock) { exit 0 }
Set-WatchdogLock

Write-WatchLog "watchdog start pid=$PID interval=${IntervalSec}s nonblocking-recovery ps=$($PSVersionTable.PSVersion)"
try { Disable-DockerAutoUpdateAndBloat } catch {}

$lastFullSpawn = [datetime]::MinValue
$fullFailCount = 0
$cycle = 0
$wasUnhealthy = $false
$loggedRecoveryInProgress = $false

try {
    while ($true) {
        $cycle++
        $recState = Get-RecoveryState
        if ($recState -eq "Running") {
            # Log once when recovery starts being observed; not every poll.
            if (-not $loggedRecoveryInProgress) {
                Write-WatchLog "recovery worker in progress..."
                $loggedRecoveryInProgress = $true
            }
            if ($Once) { Start-Sleep 5; continue }
            Start-Sleep -Seconds $IntervalSec
            continue
        }
        if ($loggedRecoveryInProgress -and $recState -eq "None") {
            $loggedRecoveryInProgress = $false
        }
        if ($recState -eq "Stale") {
            Write-WatchLog "cleared stale recovery lock" "WARN"
        }

        $report = $null
        try { $report = Get-DockerHealthReport } catch {
            Write-WatchLog "health exception: $($_.Exception.Message)" "WARN"
            $report = [pscustomobject]@{
                EngineOk=$false; BackendProcess=$false; Proxy26000=$false; GamePort26010=$false; ServerUp=$false
            }
        }

        $engineOk = [bool]$report.EngineOk
        $serverOk = [bool]$report.ServerUp
        $proxyOk  = [bool]$report.Proxy26000
        $gameOk   = [bool]$report.GamePort26010

        if ($engineOk -and $serverOk -and $proxyOk -and $gameOk) {
            if ($fullFailCount -gt 0 -or $wasUnhealthy) {
                Write-WatchLog "healthy again (after failure/recovery)"
                $wasUnhealthy = $false
            }
            $fullFailCount = 0
            if ($Once) { Write-WatchLog "Once: healthy"; break }
            Start-Sleep -Seconds $IntervalSec
            continue
        }

        # Edge-trigger: one failure line per outage, not every poll.
        if (-not $wasUnhealthy) {
            Write-WatchLog ("unhealthy engine={0} backend={1} server={2} proxy={3} game26010={4}" -f `
                $engineOk, $report.BackendProcess, $serverOk, $proxyOk, $gameOk) "WARN"
        }
        $wasUnhealthy = $true

        # L1: proxy only (inline — must be fast, no separate process needed)
        if ($engineOk -and $gameOk -and -not $proxyOk) {
            Write-WatchLog "L1: restart proxy (inline)"
            try {
                $ok = Start-EveCaptureProxy -ForceRestart
                Write-WatchLog "L1 result=$ok"
            } catch {
                Write-WatchLog "L1 exception: $($_.Exception.Message)" "ERROR"
            }
            if ($Once) { break }
            Start-Sleep -Seconds $IntervalSec
            continue
        }

        # L2: engine up, stack bad
        if ($engineOk -and (-not $serverOk -or -not $gameOk)) {
            Write-WatchLog "L2: spawn soft recovery"
            Start-RecoveryWorker -Level soft
            if ($Once) { break }
            Start-Sleep -Seconds $IntervalSec
            continue
        }

        # L3: engine down — confirm, then spawn full recovery
        if (-not $engineOk) {
            Start-Sleep -Seconds $ConfirmDeadSec
            $again = $false
            try { $again = Test-DockerEngine } catch {}
            if ($again) {
                Write-WatchLog "engine recovered during confirm window; skip L3"
                Start-Sleep -Seconds $IntervalSec
                continue
            }

            $since = ((Get-Date) - $lastFullSpawn).TotalSeconds
            if ($lastFullSpawn -ne [datetime]::MinValue -and $since -lt $MinSecondsBetweenFull) {
                Write-WatchLog ("L3 rate-limited ({0:N0}s < {1}s)" -f $since, $MinSecondsBetweenFull) "WARN"
            } else {
                $fullFailCount++
                # After two full recoveries still failing, force WSL shutdown path.
                $level = if ($fullFailCount -ge 2) { "full-wsl" } else { "full" }
                Write-WatchLog "L3: spawn $level recovery (failCount=$fullFailCount)"
                Start-RecoveryWorker -Level $level
                $lastFullSpawn = Get-Date
            }
        }

        if ($Once) { break }
        Start-Sleep -Seconds $IntervalSec
    }
} finally {
    Clear-WatchdogLock
    Write-WatchLog "watchdog stop pid=$PID"
}

exit 0

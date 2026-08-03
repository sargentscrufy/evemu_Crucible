# docker-lib.ps1 -- shared Docker Desktop recovery helpers for this dev box.
#
# Failure modes (Desktop 4.8x / WSL2):
#   1. Backend dies; AF_UNIX sockets under %LOCALAPPDATA%\Docker\run block restart.
#   2. Stuck auto-update "preparing to install" thrash.
#   3. WSL VHD remount flakes (exit 0xffffffff).
#   4. Capture proxy :26000 dies while game server is on :26010.
#   5. Recovery that blocks the watchdog loop for minutes (fixed by async recover).
#
# Every public function is best-effort + try/catch.

$script:DockerLib_Docker   = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
$script:DockerLib_Desktop  = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$script:DockerLib_Repo     = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$script:DockerLib_Settings = Join-Path $env:APPDATA "Docker\settings-store.json"
$script:DockerLib_LogDir   = Join-Path $PSScriptRoot "logs"

function Write-DockerLog {
    param([string]$Message, [string]$Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"
    try { Write-Host $line } catch {}
    try {
        if (-not (Test-Path $script:DockerLib_LogDir)) {
            New-Item -ItemType Directory -Path $script:DockerLib_LogDir -Force | Out-Null
        }
        $logFile = Join-Path $script:DockerLib_LogDir "docker-ops.log"
        Add-Content -Path $logFile -Value $line -ErrorAction SilentlyContinue
        $item = Get-Item $logFile -ErrorAction SilentlyContinue
        if ($item -and $item.Length -gt 2MB) {
            $bak = Join-Path $script:DockerLib_LogDir ("docker-ops.{0}.log" -f (Get-Date -Format yyyyMMdd-HHmmss))
            Move-Item $logFile $bak -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}

function Invoke-WithTimeout {
    param(
        [scriptblock]$Script,
        [int]$TimeoutSec = 30,
        [object]$ArgumentList = $null
    )
    try {
        $job = if ($null -ne $ArgumentList) {
            Start-Job -ScriptBlock $Script -ArgumentList $ArgumentList
        } else {
            Start-Job -ScriptBlock $Script
        }
        $done = Wait-Job $job -Timeout $TimeoutSec
        if (-not $done) {
            Stop-Job $job -ErrorAction SilentlyContinue
            Remove-Job $job -Force -ErrorAction SilentlyContinue
            return @{ Ok = $false; TimedOut = $true; Result = $null }
        }
        $result = Receive-Job $job -ErrorAction SilentlyContinue
        Remove-Job $job -Force -ErrorAction SilentlyContinue
        return @{ Ok = $true; TimedOut = $false; Result = $result }
    } catch {
        return @{ Ok = $false; TimedOut = $false; Result = $null; Error = $_.Exception.Message }
    }
}

function Test-DockerEngine {
    # Short wall-clock bound: hung docker CLI must not freeze the watchdog.
    try {
        if (-not (Test-Path $script:DockerLib_Docker)) { return $false }
        $docker = $script:DockerLib_Docker
        $r = Invoke-WithTimeout -TimeoutSec 8 -Script {
            param($exe)
            & $exe info --format '{{.ServerVersion}}' 2>$null | Out-Null
            return ($LASTEXITCODE -eq 0)
        } -ArgumentList $docker
        if ($r.TimedOut) {
            Write-DockerLog "Test-DockerEngine: docker info timed out (8s)" "WARN"
            return $false
        }
        return [bool]$r.Result
    } catch {
        return $false
    }
}

function Test-DockerBackendProcess {
    try {
        return [bool](Get-Process -Name "com.docker.backend" -ErrorAction SilentlyContinue)
    } catch { return $false }
}

function Test-PortListening {
    param([int]$Port)
    try {
        $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return [bool]$c
    } catch {
        return $false
    }
}

function Test-TcpConnect {
    param([string]$HostName = "127.0.0.1", [int]$Port, [int]$TimeoutMs = 1500)
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $iar = $tcp.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        $connected = $ok -and $tcp.Connected
        try { $tcp.Close() } catch {}
        return $connected
    } catch {
        return $false
    }
}

function Get-EvemuContainerStatus {
    try {
        if (-not (Test-DockerEngine)) { return $null }
        $docker = $script:DockerLib_Docker
        $r = Invoke-WithTimeout -TimeoutSec 10 -Script {
            param($exe)
            & $exe ps -a --format '{{.Names}}|{{.Status}}' 2>$null
        } -ArgumentList $docker
        if (-not $r.Ok -or $r.TimedOut) { return $null }
        $map = @{}
        foreach ($row in @($r.Result)) {
            if ($row -match '^([^|]+)\|(.+)$') { $map[$Matches[1]] = $Matches[2] }
        }
        return $map
    } catch {
        return $null
    }
}

function Disable-DockerAutoUpdateAndBloat {
    $settings = $script:DockerLib_Settings
    if (-not (Test-Path $settings)) {
        Write-DockerLog "settings-store.json missing; skip patch" "WARN"
        return
    }
    try {
        $j = Get-Content $settings -Raw -ErrorAction Stop | ConvertFrom-Json
        $j | Add-Member -NotePropertyName AutoDownloadUpdates -NotePropertyValue $false -Force
        $j | Add-Member -NotePropertyName DisableUpdate -NotePropertyValue $true -Force
        $j | Add-Member -NotePropertyName AutoUpdate -NotePropertyValue $false -Force
        $j | Add-Member -NotePropertyName UpdateInstallTime -NotePropertyValue 0 -Force
        $j | Add-Member -NotePropertyName EnableDockerAI -NotePropertyValue $false -Force
        $j | Add-Member -NotePropertyName ExtensionsEnabled -NotePropertyValue $false -Force
        $j | Add-Member -NotePropertyName DesktopTerminalEnabled -NotePropertyValue $false -Force
        $j | Add-Member -NotePropertyName AutoStart -NotePropertyValue $false -Force
        $j | Add-Member -NotePropertyName AutoPauseTimeoutSeconds -NotePropertyValue 0 -Force
        $j | Add-Member -NotePropertyName UseResourceSaver -NotePropertyValue $false -Force
        $j | Add-Member -NotePropertyName UseContainerdSnapshotter -NotePropertyValue $true -Force
        $j | Add-Member -NotePropertyName OpenUIOnStartupDisabled -NotePropertyValue $true -Force
        $j | Add-Member -NotePropertyName AnalyticsEnabled -NotePropertyValue $false -Force
        $j | ConvertTo-Json -Depth 20 | Set-Content $settings -Encoding UTF8 -ErrorAction Stop
        Write-DockerLog "patched settings: no-update, no-AI, no-extensions, no-autopause, no-analytics-ui"
    } catch {
        Write-DockerLog "settings patch failed: $($_.Exception.Message)" "WARN"
    }
}

function Clear-DockerUpdateStaging {
    foreach ($d in @(
        (Join-Path $env:LOCALAPPDATA "Temp\DockerDesktopUpdates"),
        (Join-Path $env:LOCALAPPDATA "Temp\DockerDesktopInstallers")
    )) {
        if (-not (Test-Path $d)) { continue }
        try {
            Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction Stop
            Write-DockerLog "removed update staging $d"
        } catch {
            try {
                $ts = Get-Date -Format yyyyMMdd-HHmmss
                Rename-Item -LiteralPath $d -NewName ("{0}.stale.{1}" -f (Split-Path $d -Leaf), $ts) -Force -ErrorAction Stop
                Write-DockerLog "renamed update staging aside: $d"
            } catch {
                Write-DockerLog "could not clear $d : $($_.Exception.Message)" "WARN"
            }
        }
    }
}

function Clear-DockerStaleSockets {
    $ts = Get-Date -Format yyyyMMdd-HHmmss
    foreach ($d in @(
        (Join-Path $env:LOCALAPPDATA "Docker\run"),
        (Join-Path $env:LOCALAPPDATA "docker-secrets-engine")
    )) {
        try {
            if ((Test-Path $d) -and (Get-ChildItem $d -Force -ErrorAction SilentlyContinue)) {
                Rename-Item -LiteralPath $d -NewName ("{0}.stale.{1}" -f (Split-Path $d -Leaf), $ts) -Force -ErrorAction Stop
                New-Item -ItemType Directory -Path $d -Force | Out-Null
                Write-DockerLog "cleared socket dir $d"
            } elseif (-not (Test-Path $d)) {
                New-Item -ItemType Directory -Path $d -Force | Out-Null
            }
        } catch {
            Write-DockerLog "socket clear failed for $d : $($_.Exception.Message)" "WARN"
            try { New-Item -ItemType Directory -Path $d -Force | Out-Null } catch {}
        }
    }
    try {
        Get-ChildItem "$env:LOCALAPPDATA\Docker", "$env:LOCALAPPDATA" -Directory -Filter "*.stale.*" -ErrorAction SilentlyContinue |
            ForEach-Object {
                try { Remove-Item -LiteralPath $_.FullName -Recurse -Force -Confirm:$false -ErrorAction Stop } catch {}
            }
    } catch {}
}

function Stop-DockerDesktopHard {
    param([switch]$SkipIfAlreadyDead)

    $alive = Get-Process -Name "Docker Desktop","com.docker.backend","com.docker.build" -ErrorAction SilentlyContinue
    if ($SkipIfAlreadyDead -and -not $alive) {
        Write-DockerLog "hard-stop skipped: no Desktop processes"
        return
    }

    Write-DockerLog "hard-stopping Docker Desktop processes"
    try {
        if ((Test-Path $script:DockerLib_Docker) -and $alive) {
            # Bound the CLI stop so a hung CLI cannot stall recovery.
            $null = Invoke-WithTimeout -TimeoutSec 15 -Script {
                param($exe)
                & $exe desktop stop 2>$null | Out-Null
            } -ArgumentList $script:DockerLib_Docker
        }
    } catch {}

    foreach ($n in @("Docker Desktop","com.docker.backend","com.docker.build","com.docker.diagnose","Docker Desktop Installer","InstallerCli")) {
        try {
            Get-Process -Name $n -ErrorAction SilentlyContinue |
                Stop-Process -Force -Confirm:$false -ErrorAction SilentlyContinue
        } catch {}
    }
    try {
        Get-Process -ErrorAction SilentlyContinue |
            Where-Object { $_.ProcessName -match 'Docker Desktop Updater|vpnkit' } |
            Stop-Process -Force -Confirm:$false -ErrorAction SilentlyContinue
    } catch {}

    try {
        $svc = Get-Service com.docker.service -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -eq 'Running') {
            Stop-Service com.docker.service -Force -ErrorAction SilentlyContinue
        }
    } catch {}

    Start-Sleep -Seconds 2
}

function Invoke-WslShutdown {
    # Clean slate for wedged docker-desktop distro / VHD mount flakes.
    try {
        Write-DockerLog "wsl --shutdown"
        $null = Invoke-WithTimeout -TimeoutSec 45 -Script {
            & wsl.exe --shutdown 2>&1 | Out-Null
        }
        Start-Sleep -Seconds 3
    } catch {
        Write-DockerLog "wsl --shutdown failed: $($_.Exception.Message)" "WARN"
    }
}

function Start-DockerDesktopProcess {
    try {
        $svc = Get-Service com.docker.service -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -ne 'Running') {
            Start-Service com.docker.service -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
    } catch {}
    try {
        if (-not (Test-Path $script:DockerLib_Desktop)) {
            Write-DockerLog "Docker Desktop.exe missing" "ERROR"
            return $false
        }
        # Prefer CLI start when available (less UI thrash).
        if (Test-Path $script:DockerLib_Docker) {
            $cli = Invoke-WithTimeout -TimeoutSec 20 -Script {
                param($exe)
                & $exe desktop start 2>&1 | Out-Null
                return $LASTEXITCODE
            } -ArgumentList $script:DockerLib_Docker
            if ($cli.Ok -and -not $cli.TimedOut) {
                Write-DockerLog "docker desktop start CLI invoked (exit=$($cli.Result))"
            }
        }
        if (-not (Test-DockerBackendProcess)) {
            Start-Process $script:DockerLib_Desktop -ErrorAction Stop
            Write-DockerLog "launched Docker Desktop.exe"
        }
        return $true
    } catch {
        Write-DockerLog "failed to launch Desktop: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

function Wait-DockerEngine {
    param([int]$TimeoutSec = 240, [int]$PollSec = 4)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $i = 0
    while ((Get-Date) -lt $deadline) {
        $i++
        if (Test-DockerEngine) {
            Write-DockerLog "engine up (poll $i)"
            return $true
        }
        if (($i % 5) -eq 0) { Write-DockerLog "still waiting for engine (poll $i)..." }
        Start-Sleep -Seconds $PollSec
    }
    Write-DockerLog "engine not up after ${TimeoutSec}s" "ERROR"
    return $false
}

function Start-EvemuCompose {
    try {
        if (-not (Test-DockerEngine)) {
            Write-DockerLog "compose skipped: engine down" "WARN"
            return $false
        }
        $repo = $script:DockerLib_Repo
        $docker = $script:DockerLib_Docker
        $r = Invoke-WithTimeout -TimeoutSec 90 -Script {
            param($exe, $cwd)
            Set-Location $cwd
            & $exe compose up -d 2>&1 | Out-String
        } -ArgumentList $docker, $repo
        if ($r.TimedOut) {
            Write-DockerLog "compose up timed out (90s)" "ERROR"
            return $false
        }
        $flat = ("$($r.Result)").Trim() -replace '\s+', ' '
        if ($flat.Length -gt 200) { $flat = $flat.Substring(0, 200) }
        if ([string]::IsNullOrWhiteSpace($flat)) { $flat = "(no output)" }
        Write-DockerLog "compose up: $flat"

        foreach ($n in 1..18) {
            Start-Sleep -Seconds 4
            try {
                $h = & $docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' server 2>$null
                if ($h -eq 'healthy' -or $h -eq 'running') {
                    Write-DockerLog "server container status=$h"
                    return $true
                }
                if (($n % 3) -eq 0) { Write-DockerLog "server status=$h (wait $n)" }
            } catch {}
        }
        Write-DockerLog "server never healthy after compose" "WARN"
        # Containers may still be usable mid-start.
        return (Test-TcpConnect -Port 26010)
    } catch {
        Write-DockerLog "compose failed: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

function Get-PythonExe {
    foreach ($name in @("python", "python3", "py")) {
        try {
            $cmd = Get-Command $name -ErrorAction SilentlyContinue
            if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source) -and ($cmd.Source -notmatch 'WindowsApps')) {
                return $cmd.Source
            }
        } catch {}
    }
    foreach ($cand in @(
        "$env:USERPROFILE\.local\bin\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
    )) {
        if (Test-Path $cand) { return $cand }
    }
    return $null
}

function Stop-EveCaptureProxy {
    try {
        $owners = @(Get-NetTCPConnection -LocalPort 26000 -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
        foreach ($procId in $owners) {
            if (-not $procId -or $procId -eq 0) { continue }
            try {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-DockerLog "killed port-26000 owner pid $procId"
            } catch {}
        }
    } catch {
        Write-DockerLog "Stop-EveCaptureProxy: $($_.Exception.Message)" "WARN"
    }
}

function Start-EveCaptureProxy {
    param([switch]$ForceRestart)
    try {
        if ($ForceRestart) { Stop-EveCaptureProxy; Start-Sleep -Seconds 1 }
        if ((Test-PortListening -Port 26000) -and (Test-TcpConnect -Port 26000)) {
            Write-DockerLog "proxy already listening on 26000"
            return $true
        }
        if (Test-PortListening -Port 26000) {
            Stop-EveCaptureProxy
            Start-Sleep -Seconds 1
        }
        $proxyDir = Join-Path $script:DockerLib_Repo "tools\debug-listener"
        $scriptPath = Join-Path $proxyDir "eve_debug_listener.py"
        if (-not (Test-Path $scriptPath)) {
            Write-DockerLog "proxy script missing" "ERROR"
            return $false
        }
        $py = Get-PythonExe
        if (-not $py) {
            Write-DockerLog "no python.exe for capture proxy" "ERROR"
            return $false
        }
        Start-Process -FilePath $py `
            -ArgumentList @("eve_debug_listener.py","--listen","0.0.0.0:26000","--target","127.0.0.1:26010","--capture-dir","captures") `
            -WorkingDirectory $proxyDir `
            -WindowStyle Hidden `
            -ErrorAction Stop
        Start-Sleep -Seconds 2
        if (Test-TcpConnect -Port 26000) {
            Write-DockerLog "proxy started on 26000 -> 26010 (python=$py)"
            return $true
        }
        Write-DockerLog "proxy launched but 26000 not accepting" "WARN"
        return $false
    } catch {
        Write-DockerLog "proxy start failed: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

function Repair-DockerSoft {
    Write-DockerLog "=== SOFT REPAIR begin ==="
    try {
        if (-not (Test-DockerEngine)) {
            Write-DockerLog "soft repair escalates: engine down"
            return (Repair-DockerFull)
        }
        $composeOk = Start-EvemuCompose
        $proxyOk = $true
        if (-not (Test-TcpConnect -Port 26000)) {
            $proxyOk = Start-EveCaptureProxy -ForceRestart
        }
        Write-DockerLog "=== SOFT REPAIR done compose=$composeOk proxy=$proxyOk ==="
        return ($composeOk -and $proxyOk)
    } catch {
        Write-DockerLog "SOFT REPAIR exception: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

function Repair-DockerFull {
    param(
        [int]$EngineTimeoutSec = 240,
        [switch]$UseWslShutdown
    )
    Write-DockerLog "=== FULL RECOVERY begin (wslShutdown=$UseWslShutdown) ==="
    try {
        Disable-DockerAutoUpdateAndBloat
        Clear-DockerUpdateStaging

        $alreadyDead = -not (Test-DockerBackendProcess) -and -not (Test-DockerEngine)
        Stop-DockerDesktopHard -SkipIfAlreadyDead:$alreadyDead

        if ($UseWslShutdown -or $alreadyDead) {
            # When the engine is already gone, WSL shutdown clears wedged
            # docker-desktop distro / VHD state that causes 0xffffffff remounts.
            Invoke-WslShutdown
        }

        Clear-DockerStaleSockets

        if (-not (Start-DockerDesktopProcess)) { return $false }
        if (-not (Wait-DockerEngine -TimeoutSec $EngineTimeoutSec)) {
            # One more try with forced WSL reset.
            Write-DockerLog "engine wait failed; retry with wsl --shutdown" "WARN"
            Stop-DockerDesktopHard
            Invoke-WslShutdown
            Clear-DockerStaleSockets
            if (-not (Start-DockerDesktopProcess)) { return $false }
            if (-not (Wait-DockerEngine -TimeoutSec $EngineTimeoutSec)) { return $false }
        }

        Start-Sleep -Seconds 2
        $composeOk = Start-EvemuCompose
        $proxyOk = Start-EveCaptureProxy -ForceRestart
        $ok = ($composeOk -and $proxyOk -and (Test-DockerEngine))
        Write-DockerLog "=== FULL RECOVERY done ok=$ok compose=$composeOk proxy=$proxyOk ==="
        return $ok
    } catch {
        Write-DockerLog "FULL RECOVERY exception: $($_.Exception.Message)" "ERROR"
        return $false
    }
}

function Get-DockerHealthReport {
    $engine = Test-DockerEngine
    $backend = Test-DockerBackendProcess
    $p26000 = Test-TcpConnect -Port 26000
    $p26010 = Test-TcpConnect -Port 26010
    $containers = $null
    $serverHealthy = $false
    if ($engine) {
        $containers = Get-EvemuContainerStatus
        if ($containers -and $containers.ContainsKey('server')) {
            $serverHealthy = ($containers['server'] -match 'healthy|Up')
        }
    }
    # If the game port answers, treat server as up even when inspect is flaky.
    if ($p26010) { $serverHealthy = $true }

    [pscustomobject]@{
        EngineOk       = $engine
        BackendProcess = $backend
        Proxy26000     = $p26000
        GamePort26010  = $p26010
        ServerUp       = $serverHealthy
        Containers     = $containers
        Timestamp      = Get-Date
    }
}

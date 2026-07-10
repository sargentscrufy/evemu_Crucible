# start-docker.ps1 -- repair-and-launch for Docker Desktop on this dev box.
#
# Docker Desktop 4.81 has a chronic startup crash: if the backend ever dies
# uncleanly it leaves AF_UNIX socket files (dockerInference, engine.sock, ...)
# that Windows refuses to delete (error 1920, "The file cannot be accessed by
# the system"). The next launch tries os.Remove() on them, fails, and the
# backend crash-loops forever. The only reliable cleanup is renaming the
# containing directories aside and recreating them empty.
#
# This script: stops Docker, clears the socket dirs, relaunches, waits for the
# engine, brings the evemu compose stack up, and restarts the capture proxy
# (client port 26000 -> container 26010).
#
#   powershell -ExecutionPolicy Bypass -File tools\ops\start-docker.ps1

$ErrorActionPreference = "Continue"
$docker  = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
$desktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$repo    = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

Write-Host "== stopping Docker Desktop processes"
Get-Process -Name "Docker Desktop","com.docker.backend","com.docker.build","com.docker.diagnose" `
    -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
Start-Sleep -Seconds 3

Write-Host "== clearing stale unix-socket dirs"
$ts = Get-Date -Format yyyyMMdd-HHmmss
foreach ($d in "$env:LOCALAPPDATA\Docker\run", "$env:LOCALAPPDATA\docker-secrets-engine") {
    if ((Test-Path $d) -and (Get-ChildItem $d -Force -ErrorAction SilentlyContinue)) {
        Rename-Item -LiteralPath $d -NewName "$(Split-Path $d -Leaf).stale.$ts" -Force
        New-Item -ItemType Directory -Path $d | Out-Null
        Write-Host "   cleared $d"
    }
}
# Old .stale dirs are undeletable until reboot; sweep any that have become deletable.
Get-ChildItem "$env:LOCALAPPDATA\Docker", "$env:LOCALAPPDATA" -Directory -Filter "*.stale.*" -ErrorAction SilentlyContinue |
    ForEach-Object { try { Remove-Item -LiteralPath $_.FullName -Recurse -Force -Confirm:$false -ErrorAction Stop } catch {} }

Write-Host "== launching Docker Desktop"
Start-Process $desktop

Write-Host "== waiting for engine (up to 5 min)"
$up = $false
foreach ($i in 1..50) {
    Start-Sleep -Seconds 6
    & $docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $up = $true; break }
    $crash = Get-Content "$env:LOCALAPPDATA\Docker\log\host\com.docker.backend.exe.log" -Tail 30 -ErrorAction SilentlyContinue |
        Select-String "backend crashed" | Select-Object -Last 1
    if ($crash -and $crash.Line -match "T$((Get-Date).ToUniversalTime().ToString('HH'))") {
        Write-Host "!! backend crashed again: $($crash.Line.Substring(0,[Math]::Min(180,$crash.Line.Length)))"
    }
}
if (-not $up) { Write-Host "FAILED: engine not up after 5 min -- check Docker Desktop window"; exit 1 }
Write-Host "== engine up"

Write-Host "== ensuring evemu stack is up"
Push-Location $repo
& $docker compose up -d 2>&1 | Select-Object -Last 2
Pop-Location

Write-Host "== ensuring capture proxy on 26000"
$listening = Get-NetTCPConnection -LocalPort 26000 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Start-Process -FilePath "python" `
        -ArgumentList "eve_debug_listener.py","--listen","0.0.0.0:26000","--target","127.0.0.1:26010","--capture-dir","captures" `
        -WorkingDirectory "$repo\tools\debug-listener" -WindowStyle Hidden
    Write-Host "   proxy started"
} else {
    Write-Host "   proxy already listening"
}

Write-Host "== done -- server containers:"
& $docker ps --format '{{.Names}}  {{.Status}}'

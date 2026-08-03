# start-watchdog.ps1 -- launch non-blocking docker-watchdog detached.
#
#   powershell -ExecutionPolicy Bypass -File tools\ops\start-watchdog.ps1

$ErrorActionPreference = "Continue"
$ops = $PSScriptRoot
$logs = Join-Path $ops "logs"
if (-not (Test-Path $logs)) { New-Item -ItemType Directory -Path $logs -Force | Out-Null }

$lock = Join-Path $logs "docker-watchdog.lock"
if (Test-Path $lock) {
    $oldText = (Get-Content $lock -Raw -ErrorAction SilentlyContinue).Trim()
    $oldId = 0
    if ([int]::TryParse($oldText, [ref]$oldId)) {
        if (Get-Process -Id $oldId -ErrorAction SilentlyContinue) {
            Write-Host "watchdog already running pid=$oldId"
            exit 0
        }
    }
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}

$shell = "C:\Program Files\PowerShell\7\pwsh.exe"
if (-not (Test-Path $shell)) {
    $shell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
}
if (-not (Test-Path $shell)) {
    Write-Host "ERROR: no powershell host found"
    exit 1
}

$wd = Join-Path $ops "docker-watchdog.ps1"
$arg = "-NoProfile -ExecutionPolicy Bypass -File `"$wd`" -IntervalSec 5"

$p = Start-Process -FilePath $shell `
    -ArgumentList $arg `
    -WorkingDirectory $ops `
    -WindowStyle Minimized `
    -PassThru

Start-Sleep -Seconds 3
if ($p -and -not $p.HasExited) {
    Write-Host "watchdog started pid=$($p.Id) shell=$shell interval=5s nonblocking"
    Write-Host "  logs: $(Join-Path $logs 'docker-watchdog.log')"
    exit 0
}

Write-Host "watchdog failed to stay up (HasExited=$($p.HasExited) Exit=$($p.ExitCode))"
Get-Content (Join-Path $logs "docker-watchdog.log") -Tail 20 -ErrorAction SilentlyContinue
exit 1

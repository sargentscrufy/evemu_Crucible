# install-watchdog-task.ps1 -- register a per-user Scheduled Task so the
# Docker heal loop comes back after logon / crashes of the watchdog process.
#
#   powershell -ExecutionPolicy Bypass -File tools\ops\install-watchdog-task.ps1
#   powershell -ExecutionPolicy Bypass -File tools\ops\install-watchdog-task.ps1 -Remove

param([switch]$Remove)

$ErrorActionPreference = "Stop"
$taskName = "EvemuDockerWatchdog"
$ops = $PSScriptRoot
$starter = Join-Path $ops "start-watchdog.ps1"
$pwsh = "C:\Program Files\PowerShell\7\pwsh.exe"
if (-not (Test-Path $pwsh)) {
    $pwsh = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
}

if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "removed scheduled task $taskName"
    exit 0
}

if (-not (Test-Path $starter)) {
    Write-Host "missing $starter"
    exit 1
}

$arg = "-NoProfile -ExecutionPolicy Bypass -File `"$starter`""
$action = New-ScheduledTaskAction -Execute $pwsh -Argument $arg -WorkingDirectory $ops
# At logon for current user; also restart every 15 min if not running (watchdog self-exits if already up).
$t1 = New-ScheduledTaskTrigger -AtLogOn
$t2 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($t1, $t2) `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "registered scheduled task: $taskName"
Write-Host "  triggers: AtLogOn + every 15 min (start-watchdog is single-instance)"
Write-Host "  action: $pwsh $arg"
# Kick once now
try { Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue } catch {}
Write-Host "started task once"
exit 0

# Register Windows Task Scheduler job for daily_run (07:00 Asia/Shanghai local time).
# Run in PowerShell (Admin optional):  .\scripts\setup_windows_task.ps1
param(
    [string]$Time = "07:00",
    [string]$TaskName = "NewMovieTracker-Daily"
)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Bat = Join-Path $Root "scripts\daily_run.bat"

if (-not (Test-Path $Bat)) {
    Write-Error "Not found: $Bat"
    exit 1
}

$Action = New-ScheduledTaskAction -Execute $Bat -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Scan sehuatang + PikPak new downloads (new-movie-tracker-skill)" `
    -Force | Out-Null

Write-Host "[ok] Task '$TaskName' registered: daily at $Time"
Write-Host "     Program: $Bat"
Write-Host "     Log:     $Root\data\daily_run.log"
Write-Host ""
Write-Host "Test now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "History:   Task Scheduler -> Task Scheduler Library -> $TaskName -> History"

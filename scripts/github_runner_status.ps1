param(
    [string]$RunnerRoot = 'E:\finance agent\finance\github-actions-runner-richard-daily',
    [string]$TaskName = 'RichardDailyDone-GitHubRunner'
)
$ErrorActionPreference = 'Stop'
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$Info = if ($Task) { Get-ScheduledTaskInfo -TaskName $TaskName } else { $null }
[pscustomobject]@{
    Configured = Test-Path -LiteralPath (Join-Path $RunnerRoot '.runner')
    ScheduledTask = if ($Task) { $Task.State.ToString() } else { 'NOT_REGISTERED' }
    LastResult = if ($Info) { $Info.LastTaskResult } else { $null }
    LastRunTime = if ($Info) { $Info.LastRunTime } else { $null }
    NextRunTime = if ($Info) { $Info.NextRunTime } else { $null }
    ProcessRunning = [bool](Get-Process -Name Runner.Listener -ErrorAction SilentlyContinue)
} | ConvertTo-Json

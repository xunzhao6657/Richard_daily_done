param([string]$TaskName = 'RichardDailyDone-GitHubRunner')
$ErrorActionPreference = 'Stop'
Enable-ScheduledTask -TaskName $TaskName | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Output 'GitHub runner startup task enabled and started.'

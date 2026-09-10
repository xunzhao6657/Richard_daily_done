param([string]$TaskName = 'RichardDailyDone-GitHubRunner')
$ErrorActionPreference = 'Stop'
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Disable-ScheduledTask -TaskName $TaskName | Out-Null
Write-Output 'GitHub runner startup task disabled.'

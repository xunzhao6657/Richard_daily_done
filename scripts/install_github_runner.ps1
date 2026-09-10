param(
    [string]$RepositoryUrl = 'https://github.com/xunzhao6657/Richard_daily_done',
    [string]$RunnerRoot = 'E:\finance agent\finance\github-actions-runner-richard-daily',
    [string]$RunnerVersion = '2.337.0',
    [Parameter(Mandatory=$true)]
    [string]$PackageSha256,
    [string]$RunnerName = $env:COMPUTERNAME + '-richard-daily',
    [string]$TaskName = 'RichardDailyDone-GitHubRunner'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if (Test-Path -LiteralPath (Join-Path $RunnerRoot '.runner')) { throw 'Runner is already configured.' }
New-Item -ItemType Directory -Path $RunnerRoot -Force | Out-Null
$Archive = Join-Path $RunnerRoot ('actions-runner-win-x64-' + $RunnerVersion + '.zip')
$Uri = 'https://github.com/actions/runner/releases/download/v' + $RunnerVersion + '/actions-runner-win-x64-' + $RunnerVersion + '.zip'
Invoke-WebRequest -Uri $Uri -OutFile $Archive
$ActualHash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash
if ($ActualHash -ne $PackageSha256) { Remove-Item -LiteralPath $Archive -Force; throw 'Runner package SHA256 mismatch.' }
Expand-Archive -LiteralPath $Archive -DestinationPath $RunnerRoot -Force
$SecureToken = Read-Host 'Enter the one-time GitHub runner registration token' -AsSecureString
$Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureToken)
try {
    $PlainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
    Set-Location -LiteralPath $RunnerRoot
    & (Join-Path $RunnerRoot 'config.cmd') --url $RepositoryUrl --token $PlainToken --name $RunnerName --labels post-market-review --work _work --unattended --replace
    if ($LASTEXITCODE -ne 0) { throw 'Runner registration failed.' }
} finally {
    if ($Pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer) }
    $PlainToken = $null
}
$Starter = (Resolve-Path (Join-Path $PSScriptRoot 'start_github_runner.ps1')).Path
$Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $Starter + '" -RunnerRoot "' + $RunnerRoot + '"'
$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $Arguments
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
$Principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Output 'Runner registered and started. The host must remain powered on, online, and logged in.'

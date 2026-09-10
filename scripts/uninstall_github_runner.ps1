param(
    [string]$RunnerRoot = 'E:\github-actions-runner-richard-daily',
    [string]$TaskName = 'RichardDailyDone-GitHubRunner'
)
$ErrorActionPreference = 'Stop'
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$Config = Join-Path $RunnerRoot 'config.cmd'
if (Test-Path -LiteralPath $Config -PathType Leaf) {
    $SecureToken = Read-Host 'Enter a one-time GitHub runner removal token' -AsSecureString
    $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureToken)
    try {
        $PlainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
        Set-Location -LiteralPath $RunnerRoot
        & $Config remove --token $PlainToken
    } finally {
        if ($Pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer) }
        $PlainToken = $null
    }
}
Write-Output 'Runner registration and startup task removed. Files were retained for audit and manual cleanup.'

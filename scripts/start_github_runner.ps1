param(
    [string]$RunnerRoot = 'E:\github-actions-runner-richard-daily'
)
$ErrorActionPreference = 'Stop'
$RunCommand = Join-Path $RunnerRoot 'run.cmd'
if (-not (Test-Path -LiteralPath $RunCommand -PathType Leaf)) { throw 'GitHub runner is not installed.' }
Set-Location -LiteralPath $RunnerRoot
& $RunCommand
exit $LASTEXITCODE

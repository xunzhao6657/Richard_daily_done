param(
    [string]$ReportDate = '',
    [ValidateSet('shadow','production')]
    [string]$Mode = 'shadow',
    [ValidateSet('collect','prepare','publish','watchdog','run','status','reconcile')]
    [string]$Action = 'run'
)
$ErrorActionPreference = 'Stop'
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Run scripts\bootstrap.ps1 first.' }
$Arguments = @('-m','post_market_review','--config',(Join-Path $ProjectRoot 'config\runtime.json'),$Action)
if ($Action -ne 'collect') { $Arguments += @('--mode',$Mode) }
if ($ReportDate) { $Arguments += @('--date',$ReportDate) }
& $Python @Arguments
exit $LASTEXITCODE

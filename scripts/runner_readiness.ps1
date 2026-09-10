$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Run scripts\bootstrap.ps1 first.' }
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'Windows timezone must be China Standard Time.' }
& $Python -m post_market_review --config (Join-Path $ProjectRoot 'config\runtime.json') doctor --redact --probe-model
exit $LASTEXITCODE

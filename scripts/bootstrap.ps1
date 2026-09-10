$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Venv = Join-Path $ProjectRoot '.venv'
if (-not (Test-Path -LiteralPath $Venv)) { python -m venv $Venv }
$Python = Join-Path $Venv 'Scripts\python.exe'
& $Python -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot 'requirements.lock')
& $Python -m pip install --disable-pip-version-check -e $ProjectRoot --no-deps
& $Python -m unittest discover -s (Join-Path $ProjectRoot 'tests')


$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentRoot = Join-Path $projectRoot '.benchmark-venvs'
$pythonVersion = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")

foreach ($name in @('uer', 'uie-nano', 'taskflow-ner')) {
    $environment = Join-Path $environmentRoot $name
    python -m venv $environment
    if ($LASTEXITCODE -ne 0) { throw "Failed to create $name environment" }
    $python = Join-Path $environment 'Scripts\python.exe'
    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip in $name environment" }
    $requirements = if ($name -eq 'uer') { 'requirements-uer.txt' } else { 'requirements-paddle.txt' }
    & $python -m pip install -r (Join-Path $PSScriptRoot $requirements)
    if ($LASTEXITCODE -ne 0) { throw "Failed to install $name requirements" }
    $actualVersion = (& $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if ($actualVersion -ne $pythonVersion) { throw "$name Python version mismatch: $actualVersion != $pythonVersion" }
}

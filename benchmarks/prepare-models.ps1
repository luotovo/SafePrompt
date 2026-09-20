$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentRoot = Join-Path $projectRoot '.benchmark-venvs'
$modelRoot = Join-Path $projectRoot '.benchmark-models'

$uerPython = Join-Path $environmentRoot 'uer\Scripts\python.exe'
$uerTarget = Join-Path $modelRoot 'uer-cluener'
& $uerPython -c "from huggingface_hub import snapshot_download; snapshot_download('uer/roberta-base-finetuned-cluener2020-chinese', revision='cddd8fc233e373855a8c0a7f4b7eb83acb686a2b', local_dir=r'$uerTarget', allow_patterns=['*.json', '*.txt', 'pytorch_model.bin', 'README.md'])"
if ($LASTEXITCODE -ne 0) { throw "UER model preparation failed with exit code $LASTEXITCODE" }

foreach ($name in @('uie-nano', 'taskflow-ner')) {
    $python = Join-Path $environmentRoot "$name\Scripts\python.exe"
    $target = Join-Path $modelRoot $name
    & $python (Join-Path $PSScriptRoot 'prepare_paddle_models.py') $name $target
    if ($LASTEXITCODE -ne 0) { throw "$name model preparation failed with exit code $LASTEXITCODE" }
}

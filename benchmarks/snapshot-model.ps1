param([Parameter(Mandatory=$true)][string]$ModelDirectory)
$resolved = (Resolve-Path -LiteralPath $ModelDirectory).Path
$manifest = Join-Path $resolved 'SHA256SUMS.json'
$entries = Get-ChildItem -LiteralPath $resolved -File -Recurse |
    Where-Object { $_.FullName -ne $manifest } |
    Sort-Object FullName |
    ForEach-Object { [ordered]@{ path = $_.FullName.Substring($resolved.Length + 1); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); bytes = $_.Length } }
$entries | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $manifest -Encoding utf8
$manifest

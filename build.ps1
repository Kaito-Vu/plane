# Build prod images, pull third-party images used by docker-compose.run.yml,
# and export all of them to one tarball to copy to the (offline) prod server.
# Usage: .\build.ps1 [-Tag prod]
param([string]$Tag = "prod")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:TAG = $Tag
$env:DOCKER_BUILDKIT = "1"
$out = "plane-images-$Tag.tar.gz"
$images = "web", "admin", "space", "live", "api", "proxy" | ForEach-Object { "plane-${_}:$Tag" }

docker compose -f docker-compose.yml build
if ($LASTEXITCODE) { throw "build failed" }

# third-party images = literal (non-${...}) image: lines in the run compose file
$external = Select-String -Path docker-compose.run.yml -Pattern '^\s+image:\s*(\S+)' |
    ForEach-Object { $_.Matches[0].Groups[1].Value } | Where-Object { $_ -notmatch '\$' }
foreach ($i in $external) {
    docker pull --platform linux/amd64 $i
    if ($LASTEXITCODE) { throw "pull $i failed" }
}

# docker save -o + gzip via .NET: PowerShell pipes corrupt binary streams
$tar = "plane-images-$Tag.tar"
docker save -o $tar @images @external
if ($LASTEXITCODE) { throw "docker save failed" }
$in = [IO.File]::OpenRead($tar)
$gz = New-Object IO.Compression.GZipStream([IO.File]::Create($out), [IO.Compression.CompressionMode]::Compress)
$in.CopyTo($gz); $gz.Dispose(); $in.Dispose()
Remove-Item $tar

Write-Host "Done: $out"
Write-Host "Copy to prod: $out docker-compose.run.yml .env.prod run.sh, then ./run.sh"

[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\backups\supabase"),
    [string]$DatabaseUrl = $env:MIGRATION_DATABASE_URL
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    throw "MIGRATION_DATABASE_URL or -DatabaseUrl is required."
}
if ($DatabaseUrl -notmatch "^postgres(ql)?(\+psycopg)?://") {
    throw "DatabaseUrl must be a PostgreSQL connection URL."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required because local pg_dump is not installed."
}

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$archiveName = "repowise-$timestamp.dump"
$archivePath = Join-Path $resolvedOutput $archiveName
$manifestPath = "$archivePath.json"

$previousDsn = $env:REPOWISE_BACKUP_DSN
$pgDumpUrl = $DatabaseUrl -replace "^postgresql\+psycopg://", "postgresql://"
$env:REPOWISE_BACKUP_DSN = $pgDumpUrl
try {
    $dockerArgs = @(
        "run", "--rm",
        "--env", "REPOWISE_BACKUP_DSN",
        "--mount", "type=bind,source=$resolvedOutput,target=/backup",
        "pgvector/pgvector:pg17",
        "bash", "-ceu",
        'pg_dump "$REPOWISE_BACKUP_DSN" --format=custom --compress=9 --no-owner --no-privileges --file="/backup/$1"; pg_restore --list "/backup/$1" >/dev/null',
        "--", $archiveName
    )
    & docker @dockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump or archive validation failed."
    }
}
finally {
    $env:REPOWISE_BACKUP_DSN = $previousDsn
}

$archive = Get-Item -LiteralPath $archivePath
$checksum = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest = [ordered]@{
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    archive = $archive.Name
    bytes = $archive.Length
    sha256 = $checksum
    format = "postgresql-custom"
    contains_secrets = $true
    restore_drill_required = $true
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Output ($manifest | ConvertTo-Json -Compress)

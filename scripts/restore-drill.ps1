[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required for the isolated restore drill."
}

$resolvedBackup = (Resolve-Path -LiteralPath $BackupFile).Path
$containerName = "repowise-restore-$([guid]::NewGuid().ToString('N').Substring(0, 12))"
$containerBackup = "/tmp/repowise.dump"
$password = [guid]::NewGuid().ToString("N")

try {
    & docker run --detach --rm --name $containerName --env "POSTGRES_PASSWORD=$password" pgvector/pgvector:pg17 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start the temporary PostgreSQL container."
    }

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        & docker exec $containerName pg_isready -U postgres -d postgres 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        throw "Temporary PostgreSQL did not become ready."
    }

    & docker cp $resolvedBackup "$($containerName):$containerBackup" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to copy the backup into the restore container."
    }

    $extensionSql = 'CREATE SCHEMA IF NOT EXISTS extensions; CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions; CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;'
    & docker exec $containerName psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c $extensionSql | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to prepare application extensions in the restore container."
    }

    & docker exec $containerName pg_restore --exit-on-error --no-owner --no-privileges --schema public --username postgres --dbname postgres $containerBackup
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore failed."
    }

    $migration = (& docker exec $containerName psql -U postgres -d postgres -Atqc "SELECT version_num FROM alembic_version").Trim()
    $vectorExtension = (& docker exec $containerName psql -U postgres -d postgres -Atqc "SELECT extversion FROM pg_extension WHERE extname='vector'").Trim()
    $vectorDistance = (& docker exec $containerName psql -U postgres -d postgres -Atqc "SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector").Trim()

    if ($migration -notlike "0016*") {
        throw "Restored migration head is '$migration', expected '0016'."
    }
    if ([string]::IsNullOrWhiteSpace($vectorExtension)) {
        throw "The vector extension is missing after restore."
    }

    [ordered]@{
        restored_at = (Get-Date).ToUniversalTime().ToString("o")
        migration_head = $migration
        vector_extension = $vectorExtension
        vector_distance = $vectorDistance
        outcome = "success"
    } | ConvertTo-Json -Compress | Write-Output
}
finally {
    & docker rm --force $containerName 2>$null | Out-Null
}

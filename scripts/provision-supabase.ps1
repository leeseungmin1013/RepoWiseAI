[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[a-z]{20}$")]
    [string]$ProjectRef,

    [Parameter(Mandatory = $true)]
    [string]$PoolerHost,

    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $PSScriptRoot "..\backups\phase3-production"
}
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$securePassword = Read-Host "Supabase DB password (input is hidden)" -AsSecureString
$passwordPointer = [IntPtr]::Zero
$plainPassword = $null
$escapedPassword = $null
$directUrl = $null
$poolerUrl = $null
$previousMigrationUrl = $env:MIGRATION_DATABASE_URL

try {
    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    if ([string]::IsNullOrWhiteSpace($plainPassword)) {
        throw "Database password must not be empty."
    }

    $escapedPassword = [uri]::EscapeDataString($plainPassword)
    $directUrl = "postgresql+psycopg://postgres:$escapedPassword@db.$ProjectRef.supabase.co:5432/postgres?sslmode=require"
    $poolerUrl = "postgresql+psycopg://postgres.${ProjectRef}:$escapedPassword@${PoolerHost}:5432/postgres?sslmode=require"

    Push-Location $repositoryRoot
    try {
        $env:MIGRATION_DATABASE_URL = $directUrl
        & uv run --project apps/api --locked python -m app.migrate
        if ($LASTEXITCODE -ne 0) {
            throw "Migration failed with exit code $LASTEXITCODE."
        }

        $env:MIGRATION_DATABASE_URL = $poolerUrl
        & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/backup-supabase.ps1 -OutputDirectory $OutputDirectory
        if ($LASTEXITCODE -ne 0) {
            throw "Backup failed with exit code $LASTEXITCODE."
        }

        $resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
        $backupFile = Get-ChildItem -LiteralPath $resolvedOutput -Filter "*.dump" |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if (-not $backupFile) {
            throw "Backup archive was not created."
        }

        & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restore-drill.ps1 -BackupFile $backupFile.FullName
        if ($LASTEXITCODE -ne 0) {
            throw "Restore drill failed with exit code $LASTEXITCODE."
        }

        [ordered]@{
            project_ref = $ProjectRef
            backup_file = $backupFile.Name
            outcome = "success"
        } | ConvertTo-Json -Compress | Write-Output
    }
    finally {
        Pop-Location
    }
}
finally {
    $env:MIGRATION_DATABASE_URL = $previousMigrationUrl
    $directUrl = $null
    $poolerUrl = $null
    $escapedPassword = $null
    $plainPassword = $null
    if ($passwordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
    if ($securePassword) {
        $securePassword.Dispose()
    }
}

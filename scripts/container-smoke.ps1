[CmdletBinding()]
param(
    [string]$Image = "repowise-api:production-smoke",
    [string]$EnvFile = ".env",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$resolvedEnvFile = (Resolve-Path -LiteralPath $EnvFile).Path
$suffix = "$PID"
$apiContainer = "repowise-api-smoke-$suffix"
$workerContainer = "repowise-worker-smoke-$suffix"

function Wait-Ready([string]$Url, [int]$Attempts = 30) {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            return Invoke-RestMethod -Uri $Url -TimeoutSec 3
        } catch {
            if ($attempt -eq $Attempts) { throw }
            Start-Sleep -Seconds 1
        }
    }
}

try {
    if (-not $SkipBuild) {
        docker build --pull --tag $Image .
        if ($LASTEXITCODE -ne 0) { throw "Docker build failed" }
    }

    docker run --rm --entrypoint sh $Image -c @'
set -eu
test ! -e /app/.env
test ! -d /app/.git
! grep -R -I -E 'sk-(proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' /app/app /app/migrations /app/alembic.ini
'@
    if ($LASTEXITCODE -ne 0) { throw "Image secret/source hygiene scan failed" }

    docker run --rm --env-file $resolvedEnvFile $Image python -m app.migrate
    if ($LASTEXITCODE -ne 0) { throw "Migration failed" }

    docker run --detach --name $apiContainer --env-file $resolvedEnvFile --publish 18000:10000 $Image
    if ($LASTEXITCODE -ne 0) { throw "API container failed to start" }
    $live = Wait-Ready "http://127.0.0.1:18000/api/health/live"
    $ready = Wait-Ready "http://127.0.0.1:18000/api/health/ready"
    if ($live.status -ne "alive" -or $ready.status -ne "ready") {
        throw "Health contract failed"
    }

    docker run --detach --name $workerContainer --env-file $resolvedEnvFile $Image python -m app.workers.runner
    if ($LASTEXITCODE -ne 0) { throw "Worker container failed to start" }
    Start-Sleep -Seconds 3
    $workerLogs = docker logs $workerContainer 2>&1 | Out-String
    if ($workerLogs -notmatch "repowise-deep-learning" -or $workerLogs -notmatch "repowise-analysis") {
        throw "Worker did not report both queues"
    }

    $first = docker run --rm --env-file $resolvedEnvFile $Image python -m app.workers.maintenance
    if ($LASTEXITCODE -ne 0) { throw "First maintenance run failed" }
    $second = docker run --rm --env-file $resolvedEnvFile $Image python -m app.workers.maintenance
    if ($LASTEXITCODE -ne 0) { throw "Second maintenance run failed" }
    $secondSummary = $second | Select-Object -Last 1 | ConvertFrom-Json
    if (
        $secondSummary.semantic_cache_deleted -ne 0 -or
        $secondSummary.stale_reservations_released -ne 0
    ) {
        throw "Second maintenance run was not a no-op"
    }

    docker stop --time 300 $workerContainer $apiContainer | Out-Null
    Write-Output ([ordered]@{
        image = $Image
        release = $ready.release
        liveness = $live.status
        readiness = $ready.status
        maintenance_second_run = $secondSummary.outcome
        outcome = "success"
    } | ConvertTo-Json -Compress)
} finally {
    docker rm --force $workerContainer $apiContainer 2>$null | Out-Null
}

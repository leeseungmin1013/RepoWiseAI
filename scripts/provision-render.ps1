[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OwnerId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[a-z]{20}$")]
    [string]$ProjectRef,

    [Parameter(Mandatory = $true)]
    [string]$PoolerHost,

    [string]$Repository = "https://github.com/leeseungmin1013/RepoWiseAI",
    [string]$Branch = "codex/repository-structure-visualization"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$renderConfigPath = Join-Path $env:USERPROFILE ".render\cli.yaml"
$securePassword = Read-Host "Supabase DB password (input is hidden and will be sent to Render secrets)" -AsSecureString
$passwordPointer = [IntPtr]::Zero
$plainPassword = $null
$escapedPassword = $null
$renderConfig = $null
$renderApiKey = $null
$openAiApiKey = $null
$headers = $null

function Get-DotEnvValue {
    param([string]$Path, [string]$Key)
    $line = Get-Content -LiteralPath $Path | Where-Object { $_ -match ("^\s*" + [regex]::Escape($Key) + "\s*=") } | Select-Object -First 1
    if (-not $line) { return $null }
    $value = ($line -replace ("^\s*" + [regex]::Escape($Key) + "\s*=\s*"), "").Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    return $value
}

function Invoke-RenderApi {
    param([string]$Method, [string]$Path, $Body = $null)
    $parameters = @{
        Method = $Method
        Uri = "https://api.render.com/v1$Path"
        Headers = $headers
    }
    if ($null -ne $Body) {
        $parameters.ContentType = "application/json"
        $parameters.Body = ($Body | ConvertTo-Json -Depth 20 -Compress)
    }
    return Invoke-RestMethod @parameters
}

function Get-ResourceObject {
    param($Value, [string]$Wrapper)
    if ($Value.PSObject.Properties.Name -contains $Wrapper) { return $Value.$Wrapper }
    return $Value
}

try {
    if (-not (Test-Path -LiteralPath $renderConfigPath)) { throw "Render CLI login is required." }
    $renderConfig = Get-Content -Raw -LiteralPath $renderConfigPath
    $keyMatch = [regex]::Match($renderConfig, '(?m)^\s+key:\s*(\S+)\s*$')
    if (-not $keyMatch.Success) { throw "Render API key is missing from CLI config." }
    $renderApiKey = $keyMatch.Groups[1].Value
    $headers = @{ Authorization = "Bearer $renderApiKey"; Accept = "application/json" }

    $openAiApiKey = Get-DotEnvValue -Path (Join-Path $repositoryRoot ".env") -Key "OPENAI_API_KEY"
    if ([string]::IsNullOrWhiteSpace($openAiApiKey)) { throw "OPENAI_API_KEY is missing from the repository .env file." }

    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    if ([string]::IsNullOrWhiteSpace($plainPassword)) { throw "Database password must not be empty." }
    $escapedPassword = [uri]::EscapeDataString($plainPassword)
    $databaseUrl = "postgresql+psycopg://postgres.${ProjectRef}:$escapedPassword@${PoolerHost}:5432/postgres?sslmode=require"
    $supabaseUrl = "https://$ProjectRef.supabase.co"

    $keyValues = Invoke-RenderApi -Method GET -Path "/key-value?ownerId=$OwnerId&limit=100"
    $queue = $null
    foreach ($entry in $keyValues) {
        $candidate = Get-ResourceObject -Value $entry -Wrapper "keyValue"
        if ($candidate.name -eq "repowise-queue") { $queue = $candidate; break }
    }
    if (-not $queue) {
        $queueResponse = Invoke-RenderApi -Method POST -Path "/key-value" -Body ([ordered]@{
            name = "repowise-queue"
            ownerId = $OwnerId
            plan = "free"
            region = "singapore"
            maxmemoryPolicy = "noeviction"
            persistenceMode = "off"
            ipAllowList = @()
        })
        $queue = Get-ResourceObject -Value $queueResponse -Wrapper "keyValue"
    }

    $connectionInfo = $null
    for ($attempt = 0; $attempt -lt 30 -and -not $connectionInfo; $attempt++) {
        try {
            $connectionInfo = Invoke-RenderApi -Method GET -Path "/key-value/$($queue.id)/connection-info"
        }
        catch {
            if ($attempt -eq 29) { throw }
            Start-Sleep -Seconds 2
        }
    }
    $redisUrl = $connectionInfo.internalConnectionString
    if ([string]::IsNullOrWhiteSpace($redisUrl)) { throw "Render internal Key Value URL is unavailable." }

    $commonEnv = @(
        @{ key = "APP_ENV"; value = "production" },
        @{ key = "AUTH_REQUIRED"; value = "true" },
        @{ key = "ANALYSIS_WORKSPACE"; value = "/tmp/repowise/repositories" },
        @{ key = "DATABASE_URL"; value = $databaseUrl },
        @{ key = "MIGRATION_DATABASE_URL"; value = $databaseUrl },
        @{ key = "REDIS_URL"; value = $redisUrl },
        @{ key = "SUPABASE_URL"; value = $supabaseUrl },
        @{ key = "SUPABASE_JWT_ISSUER"; value = "$supabaseUrl/auth/v1" },
        @{ key = "SUPABASE_JWKS_URL"; value = "$supabaseUrl/auth/v1/.well-known/jwks.json" },
        @{ key = "OPENAI_API_KEY"; value = $openAiApiKey },
        @{ key = "QUOTA_ENFORCEMENT_MODE"; value = "off" },
        @{ key = "DEFAULT_MONTHLY_ALLOWANCE_MICRO_USD"; value = "250000" },
        @{ key = "REALTIME_MAX_DURATION_SECONDS"; value = "300" }
    )

    $services = Invoke-RenderApi -Method GET -Path "/services?ownerId=$OwnerId&limit=100"
    $existing = @{}
    foreach ($entry in $services) {
        $candidate = Get-ResourceObject -Value $entry -Wrapper "service"
        $existing[$candidate.name] = $candidate
    }

    if (-not $existing.ContainsKey("repowise-api")) {
        $apiEnv = @($commonEnv) + @(
            @{ key = "SERVICE_NAME"; value = "repowise-api" },
            @{ key = "CORS_ORIGINS"; value = "http://localhost:3000,http://127.0.0.1:3000" },
            @{ key = "HEALTHCHECK_TIMEOUT_SECONDS"; value = "2" }
        )
        $apiResponse = Invoke-RenderApi -Method POST -Path "/services" -Body ([ordered]@{
            type = "web_service"
            name = "repowise-api"
            ownerId = $OwnerId
            repo = $Repository
            branch = $Branch
            autoDeploy = "yes"
            envVars = $apiEnv
            serviceDetails = [ordered]@{
                runtime = "docker"
                envSpecificDetails = [ordered]@{
                    dockerfilePath = "./Dockerfile"
                    dockerContext = "."
                }
                plan = "free"
                region = "singapore"
                numInstances = 1
                healthCheckPath = "/api/health/ready"
                previews = @{ generation = "off" }
            }
        })
        $existing["repowise-api"] = Get-ResourceObject -Value $apiResponse -Wrapper "service"
    }

    if (-not $existing.ContainsKey("repowise-worker")) {
        $workerEnv = @($commonEnv) + @(
            @{ key = "SERVICE_NAME"; value = "repowise-worker" },
            @{ key = "QUEUE_RECOVERY_STALE_SECONDS"; value = "900" },
            @{ key = "QUEUE_RECOVERY_BATCH_SIZE"; value = "500" }
        )
        $workerResponse = Invoke-RenderApi -Method POST -Path "/services" -Body ([ordered]@{
            type = "background_worker"
            name = "repowise-worker"
            ownerId = $OwnerId
            repo = $Repository
            branch = $Branch
            autoDeploy = "yes"
            envVars = $workerEnv
            serviceDetails = [ordered]@{
                runtime = "docker"
                envSpecificDetails = [ordered]@{
                    dockerfilePath = "./Dockerfile"
                    dockerContext = "."
                    dockerCommand = "python -m app.workers.runner"
                }
                preDeployCommand = "python -m app.migrate"
                plan = "starter"
                region = "singapore"
                numInstances = 1
                maxShutdownDelaySeconds = 300
                previews = @{ generation = "off" }
            }
        })
        $existing["repowise-worker"] = Get-ResourceObject -Value $workerResponse -Wrapper "service"
    }

    [ordered]@{
        queue = @{ id = $queue.id; name = $queue.name }
        api = @{ id = $existing["repowise-api"].id; name = $existing["repowise-api"].name }
        worker = @{ id = $existing["repowise-worker"].id; name = $existing["repowise-worker"].name }
        branch = $Branch
        outcome = "created_or_reused"
    } | ConvertTo-Json -Depth 5 -Compress | Write-Output
}
finally {
    $databaseUrl = $null
    $redisUrl = $null
    $plainPassword = $null
    $escapedPassword = $null
    $openAiApiKey = $null
    $renderApiKey = $null
    $headers = $null
    $renderConfig = $null
    if ($passwordPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer) }
    if ($securePassword) { $securePassword.Dispose() }
}

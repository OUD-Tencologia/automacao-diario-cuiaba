[CmdletBinding()]
param(
    [string]$EnvironmentFile = ".env"
)

$ErrorActionPreference = "Stop"

function Get-EnvConfiguration {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Arquivo de ambiente não encontrado: $Path"
    }

    $configuration = @{}
    Get-Content -LiteralPath $Path | ForEach-Object {
        if ($_ -match "^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
            $configuration[$Matches[1]] = $Matches[2].Trim().Trim([char]34)
        }
    }
    return $configuration
}

function Invoke-RemoteCommand {
    param(
        [string]$Target,
        [string]$Port,
        [string]$Command,
        [string]$InputText
    )

    $sshArguments = @(
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-p", $Port,
        $Target,
        $Command
    )

    if ($PSBoundParameters.ContainsKey("InputText")) {
        $InputText | & ssh @sshArguments
    }
    else {
        & ssh @sshArguments
    }

    if ($LASTEXITCODE -ne 0) {
        throw "A validação remota falhou (código SSH $LASTEXITCODE)."
    }
}

$configuration = Get-EnvConfiguration -Path $EnvironmentFile
$requiredVariables = @(
    "VPS_HOMOLOGATION_HOST",
    "VPS_HOMOLOGATION_PORT",
    "VPS_HOMOLOGATION_USER"
)

foreach ($variable in $requiredVariables) {
    if ([string]::IsNullOrWhiteSpace($configuration[$variable])) {
        throw "Variável obrigatória ausente em ${EnvironmentFile}: $variable"
    }
}

$target = "{0}@{1}" -f $configuration["VPS_HOMOLOGATION_USER"], $configuration["VPS_HOMOLOGATION_HOST"]
$port = $configuration["VPS_HOMOLOGATION_PORT"]
$databaseName = "dat01_contract_{0}_{1}" -f (Get-Date -Format "yyyyMMddHHmmss"), ([guid]::NewGuid().ToString("N").Substring(0, 8))
$migrationPath = Join-Path $PSScriptRoot "..\infra\migrations\001_initial_editorial_schema.sql"
$invariantsPath = Join-Path $PSScriptRoot "..\tests\integration\initial_schema_invariants.sql"

$describePostgres = @'
set -euo pipefail
container="$(docker ps --filter 'name=postgres' --format '{{.Names}}' | head -n 1)"
test -n "$container"
db_user="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$container" | sed -n 's/^POSTGRES_USER=//p' | head -n 1)"
db_name="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$container" | sed -n 's/^POSTGRES_DB=//p' | head -n 1)"
test -n "$db_user"
test -n "$db_name"
printf '%s\n%s\n%s\n' "$container" "$db_user" "$db_name"
'@

$connectionInfo = @(Invoke-RemoteCommand -Target $target -Port $port -Command $describePostgres)
if ($connectionInfo.Count -lt 3) {
    throw "Não foi possível identificar o PostgreSQL da VPS para o teste descartável."
}

$container = $connectionInfo[-3].Trim()
$databaseUser = $connectionInfo[-2].Trim()
$adminDatabase = $connectionInfo[-1].Trim()
$created = $false

try {
    $createDatabase = "set -euo pipefail; docker exec $container psql -X -v ON_ERROR_STOP=1 -U $databaseUser -d $adminDatabase -c 'CREATE DATABASE $databaseName'"
    Invoke-RemoteCommand -Target $target -Port $port -Command $createDatabase | Out-Null
    $created = $true

    $psqlForTestDatabase = "set -euo pipefail; docker exec -i $container psql -X -v ON_ERROR_STOP=1 -U $databaseUser -d $databaseName"
    Invoke-RemoteCommand -Target $target -Port $port -Command $psqlForTestDatabase -InputText (Get-Content -Raw -LiteralPath $migrationPath) | Out-Null
    Invoke-RemoteCommand -Target $target -Port $port -Command $psqlForTestDatabase -InputText (Get-Content -Raw -LiteralPath $invariantsPath) | Out-Null

    Write-Output "Migration DAT-01 e invariantes validadas em banco PostgreSQL descartável da VPS."
}
finally {
    if ($created) {
        $dropDatabase = "set -euo pipefail; docker exec $container psql -X -v ON_ERROR_STOP=1 -U $databaseUser -d $adminDatabase -c 'DROP DATABASE IF EXISTS $databaseName'"
        Invoke-RemoteCommand -Target $target -Port $port -Command $dropDatabase | Out-Null
        Write-Output "Banco temporário de validação removido."
    }
}

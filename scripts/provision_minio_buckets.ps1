[CmdletBinding()]
param(
    [string]$EnvironmentFile = ".env",
    [switch]$ValidateOnly,
    [string]$McImage = "quay.io/minio/mc:latest"
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
        [string]$Command
    )

    $sshArguments = @(
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-p", $Port,
        $Target,
        $Command
    )
    & ssh @sshArguments

    if ($LASTEXITCODE -ne 0) {
        throw "A operação remota do MinIO falhou (código SSH $LASTEXITCODE)."
    }
}

function Assert-BucketName {
    param(
        [string]$Name,
        [string]$VariableName
    )

    if ($Name -notmatch "^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$") {
        throw "Nome de bucket inválido em $VariableName. Use 3-63 caracteres minúsculos, números, ponto ou hífen."
    }
}

$configuration = Get-EnvConfiguration -Path $EnvironmentFile
$requiredVariables = @(
    "VPS_HOMOLOGATION_HOST",
    "VPS_HOMOLOGATION_PORT",
    "VPS_HOMOLOGATION_USER",
    "MINIO_BUCKET_BRONZE",
    "MINIO_BUCKET_SILVER",
    "MINIO_BUCKET_GOLD",
    "MINIO_RETENTION_DAYS"
)

foreach ($variable in $requiredVariables) {
    if ([string]::IsNullOrWhiteSpace($configuration[$variable])) {
        throw "Variável obrigatória ausente em ${EnvironmentFile}: $variable"
    }
}

$bronzeBucket = $configuration["MINIO_BUCKET_BRONZE"]
$silverBucket = $configuration["MINIO_BUCKET_SILVER"]
$goldBucket = $configuration["MINIO_BUCKET_GOLD"]
Assert-BucketName -Name $bronzeBucket -VariableName "MINIO_BUCKET_BRONZE"
Assert-BucketName -Name $silverBucket -VariableName "MINIO_BUCKET_SILVER"
Assert-BucketName -Name $goldBucket -VariableName "MINIO_BUCKET_GOLD"

if ($configuration["MINIO_RETENTION_DAYS"] -notmatch "^[1-9][0-9]*$") {
    throw "MINIO_RETENTION_DAYS deve ser um inteiro positivo."
}

if ($McImage -notmatch "^[a-zA-Z0-9./:@_-]+$") {
    throw "Imagem do MinIO Client inválida."
}

$target = "{0}@{1}" -f $configuration["VPS_HOMOLOGATION_USER"], $configuration["VPS_HOMOLOGATION_HOST"]
$port = $configuration["VPS_HOMOLOGATION_PORT"]
$probeKey = "__healthcheck__/obj-01-{0}.txt" -f ([guid]::NewGuid().ToString("N"))

$inspectionCommand = @'
set -euo pipefail
container="$(docker ps --filter 'name=minio' --format '{{.Names}}' | head -n 1)"
test -n "$container"
image="$(docker inspect -f '{{.Config.Image}}' "$container")"
volume_count="$(docker inspect -f '{{len .Mounts}}' "$container")"
network_count="$(docker inspect -f '{{len .NetworkSettings.Networks}}' "$container")"
root_user="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$container" | sed -n 's/^MINIO_ROOT_USER=//p' | head -n 1)"
root_password="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$container" | sed -n 's/^MINIO_ROOT_PASSWORD=//p' | head -n 1)"
test -n "$root_user"
test -n "$root_password"
curl -fsS http://127.0.0.1:9000/minio/health/live >/dev/null
printf 'container=%s\nimage=%s\nvolumes=%s\nnetworks=%s\nhealth=ok\ncredentials=available\n' "$container" "$image" "$volume_count" "$network_count"
'@

if ($ValidateOnly) {
    Invoke-RemoteCommand -Target $target -Port $port -Command $inspectionCommand
    Write-Output "Validação somente leitura do MinIO concluída."
    exit 0
}

$operationCommand = @'
set -euo pipefail
container="$(docker ps --filter 'name=minio' --format '{{.Names}}' | head -n 1)"
test -n "$container"
access_key="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$container" | sed -n 's/^MINIO_ROOT_USER=//p' | head -n 1)"
secret_key="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$container" | sed -n 's/^MINIO_ROOT_PASSWORD=//p' | head -n 1)"
test -n "$access_key"
test -n "$secret_key"

if ! docker image inspect '__MC_IMAGE__' >/dev/null 2>&1; then
    docker pull '__MC_IMAGE__' >/dev/null
fi

mc_config_dir="$(mktemp -d /tmp/automacao-editorial-mc.XXXXXX)"
cleanup_mc_config() {
    docker run --rm -v "${mc_config_dir}:/cleanup" alpine:3.20 \
        find /cleanup -mindepth 1 -delete >/dev/null
    rmdir "$mc_config_dir"
}
trap cleanup_mc_config EXIT

mc_cmd() {
    docker run --rm -i --network "container:${container}" \
        -v "${mc_config_dir}:/root/.mc" \
        '__MC_IMAGE__' "$@"
}

bronze_bucket='__BRONZE_BUCKET__'
silver_bucket='__SILVER_BUCKET__'
gold_bucket='__GOLD_BUCKET__'
retention_days='__RETENTION_DAYS__'
probe_key='__PROBE_KEY__'
probe_value='OBJ-01: conteúdo sintético de validação do armazenamento.'

mc_cmd alias set editorial http://127.0.0.1:9000 "$access_key" "$secret_key" >/dev/null
printf 'minio_client=authenticated\n'

if ! mc_cmd mb --ignore-existing --with-lock "editorial/$bronze_bucket" >/dev/null 2>&1; then
    mc_cmd stat "editorial/$bronze_bucket" >/dev/null
fi
for bucket in "$silver_bucket" "$gold_bucket"; do
    if ! mc_cmd mb --ignore-existing "editorial/$bucket" >/dev/null 2>&1; then
        mc_cmd stat "editorial/$bucket" >/dev/null
    fi
done
printf 'buckets=available\n'

for bucket in "$bronze_bucket" "$silver_bucket" "$gold_bucket"; do
    if ! mc_cmd version enable "editorial/$bucket" >/dev/null 2>&1; then
        mc_cmd version info "editorial/$bucket" | grep -qi "enabled"
    fi
    if ! mc_cmd anonymous set none "editorial/$bucket" >/dev/null 2>&1; then
        mc_cmd anonymous get "editorial/$bucket" | grep -Eqi "private|none"
    fi
    mc_cmd stat "editorial/$bucket" >/dev/null
done
printf 'versioning=enabled\n'

if ! mc_cmd retention set --default GOVERNANCE "${retention_days}d" "editorial/$bronze_bucket" >/dev/null 2>&1; then
    mc_cmd retention info "editorial/$bronze_bucket" | grep -qi "GOVERNANCE"
fi
mc_cmd retention info "editorial/$bronze_bucket" >/dev/null
printf 'bronze_retention=governance\n'

expected_hash="$(printf '%s\n' "$probe_value" | sha256sum | awk '{print $1}')"
for bucket in "$bronze_bucket" "$silver_bucket" "$gold_bucket"; do
    if ! printf '%s\n' "$probe_value" | mc_cmd pipe "editorial/$bucket/$probe_key"; then
        echo "Falha no upload do probe sintético para o bucket $bucket" >&2
        exit 1
    fi
    if ! actual_hash="$(mc_cmd cat "editorial/$bucket/$probe_key" | sha256sum | awk '{print $1}')"; then
        echo "Falha na leitura do probe sintético do bucket $bucket" >&2
        exit 1
    fi
    test "$expected_hash" = "$actual_hash"
done
printf 'put_get=ok\n'

docker restart "$container" >/dev/null
for attempt in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:9000/minio/health/live >/dev/null; then
        break
    fi
    if [ "$attempt" -eq 30 ]; then
        echo "MinIO não voltou saudável após o reinício" >&2
        exit 1
    fi
    sleep 1
done

for bucket in "$bronze_bucket" "$silver_bucket" "$gold_bucket"; do
    mc_cmd stat "editorial/$bucket" >/dev/null
    mc_cmd version info "editorial/$bucket" | grep -qi "enabled"
done
mc_cmd retention info "editorial/$bronze_bucket" | grep -qi "GOVERNANCE"
post_restart_hash="$(mc_cmd cat "editorial/$bronze_bucket/$probe_key" | sha256sum | awk '{print $1}')"
test "$expected_hash" = "$post_restart_hash"

printf 'persistence_after_restart=ok\n'
'@

$replacements = @{
    "__MC_IMAGE__" = $McImage
    "__BRONZE_BUCKET__" = $bronzeBucket
    "__SILVER_BUCKET__" = $silverBucket
    "__GOLD_BUCKET__" = $goldBucket
    "__RETENTION_DAYS__" = $configuration["MINIO_RETENTION_DAYS"]
    "__PROBE_KEY__" = $probeKey
}
foreach ($placeholder in $replacements.Keys) {
    $operationCommand = $operationCommand.Replace($placeholder, $replacements[$placeholder])
}

Invoke-RemoteCommand -Target $target -Port $port -Command $operationCommand
Write-Output "Buckets do MinIO provisionados e validados. O probe sintético do Bronze permanece retido conforme a política configurada."

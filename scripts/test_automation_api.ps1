param(
    [switch]$Integration,
    [switch]$Browser
)

$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\\.venv\\Scripts\\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente virtual não encontrado em .venv. Crie-o e instale o projeto antes de executar testes."
}

$unitExitCode = 0
& $python -m unittest discover -s "tests/unit" -p "test_*.py" -v
$unitExitCode = $LASTEXITCODE
if ($unitExitCode -ne 0) {
    exit $unitExitCode
}

if ($Browser) {
    & $python -m unittest discover -s "tests/browser" -p "test_*.py" -v
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

if ($Integration) {
    Write-Warning (
        "A validacao de migration cria e remove o banco temporario " +
        "automacao_editorial_sprint1_validation no PostgreSQL configurado. " +
        "Execute apenas contra homologacao descartavel, nunca producao."
    )
    & $python (Join-Path $PSScriptRoot "validate_single_gold_migration.py")
    exit $LASTEXITCODE
}

exit 0

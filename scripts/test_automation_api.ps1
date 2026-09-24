param(
    [switch]$Integration
)

$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\\.venv\\Scripts\\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente virtual não encontrado em .venv. Crie-o e instale o projeto antes de executar testes."
}

$target = "tests/unit"
if ($Integration) {
    $target = "tests"
}

& $python -m unittest discover -s $target -p "test_*.py" -v
exit $LASTEXITCODE

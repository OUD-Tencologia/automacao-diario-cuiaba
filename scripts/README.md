# Scripts de diagnóstico local

## Validação Folhapress do MVP

`validate_folhapress_access.py` é o diagnóstico vigente da captura enxuta. Ele
abre uma sessão temporária, valida saúde, login, catálogo, primeira página,
extração e download de TXT exclusivamente em memória. Não toca MinIO nem
PostgreSQL e não imprime conteúdo licenciado ou segredo.

```powershell
.\.venv\Scripts\python.exe scripts/validate_folhapress_access.py --max-pages 1
```

Um `ERR_CONNECTION_RESET` da origem é uma falha transitória reexecutável pelo
n8n; revise os seletores somente se a página carregar, mas o formulário mudar.

## PoC Folhapress histórica

`folhapress_poc.py` pertence ao levantamento anterior e não é o caminho usado
pela Automation API do MVP enxuto. Mantenha-o somente como evidência da PoC
manual.

`folhapress_poc.py` valida o acesso autenticado ao caminho `LOGIN` → `ENTRAR`
→ `TEXTOS` e, quando o seletor local do filtro estiver definido, aplica
`SERVIÇO NOTICIOSO`. Ele identifica links de matérias, calcula a próxima página
no padrão `sr=1`, `sr=25`, `sr=49` e pode baixar um TXT de forma temporária.

Antes da execução, preencha no `.env` local as variáveis de URL e credenciais
da Folhapress. Nunca coloque esses valores no `.env.example` ou em comandos
versionados.

```powershell
python scripts/folhapress_poc.py --self-check
python scripts/folhapress_poc.py --validate-config
python scripts/folhapress_poc.py --headed --download-first
```

A saída é um resumo JSON sem credenciais, cookies, URLs de matérias, títulos ou
corpo de texto. O arquivo baixado é usado apenas para calcular tamanho e SHA-256
e é removido antes do script terminar.

Se a página usar campos ou botões não cobertos pelos seletores genéricos,
preencha os seletores opcionais no `.env` após a inspeção manual. Esses
seletores são configuração local e não precisam ser versionados.

## Buckets MinIO

`provision_minio_buckets.ps1` prepara e valida os buckets físicos já existentes
na VPS de homologação. Ele usa a chave SSH local e lê os segredos apenas dentro
do container remoto, sem imprimi-los.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/provision_minio_buckets.ps1 -ValidateOnly
powershell -ExecutionPolicy Bypass -File scripts/provision_minio_buckets.ps1
```

A execução completa cria/valida os buckets, ativa versionamento, aplica a
retenção do Bronze, faz um put/get com conteúdo sintético e reinicia somente o
MinIO para confirmar persistência. Veja `docs/CONFIGURACAO_MINIO.md`.

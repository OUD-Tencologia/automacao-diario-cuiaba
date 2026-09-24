# Automation API

## Responsabilidade

A Automation API é a porta privada da ingestão editorial. O n8n a chama para
executar ciclos; ele não recebe acesso direto ao PostgreSQL ou MinIO.

Na Sprint 2, a API possui fundação para Gold única, armazenamento bruto,
health checks e captura modular da Folhapress. Resumo e CRUD interno entram na
Sprint 3.

## Endpoints disponíveis

| Endpoint | Uso |
|---|---|
| `GET /health/live` | Confirma que o processo FastAPI está ativo. |
| `GET /health/ready` | Executa `SELECT 1` no PostgreSQL e `HeadBucket` no bucket `bronze-raw` do MinIO. Retorna `503` sem expor erro ou segredo se uma dependência falhar. |
| `POST /automation/folhapress/capture` | Executa um ciclo idempotente para uso exclusivo do n8n. Retorna `502` em falha da fonte para que o n8n faça retry; não publica nem altera itens existentes. |
| `GET /openapi.json` | Expõe o contrato OpenAPI gerado. |

## Configuração local

Em desenvolvimento, a API usa PostgreSQL e MinIO da VPS configurados no
`.env`. `VPS_HOMOLOGATION_HOST` direciona o PostgreSQL local para a VPS. Um
endpoint MinIO explícito é preservado.

## Testes

```powershell
powershell -ExecutionPolicy Bypass -File scripts/test_automation_api.ps1
```

O comando usa o ambiente virtual do projeto e descobre os testes em
`tests/unit`; não depende de um `pytest` global do Windows.

## Regras de armazenamento bruto

- Bucket único do MVP: `MINIO_BUCKET_BRONZE` (`bronze-raw`).
- Chave: `{source}/{id}/{sha256}.txt`.
- Conteúdo idêntico reutiliza o objeto existente.
- Tamanho e SHA-256 são conferidos antes de retornar sucesso.
- O TXT não é substituído por edição editorial.

## Captura Folhapress

O ciclo cria uma sessão efêmera em memória, verifica a fonte, abre
explicitamente `/login`, navega o catálogo, deduplica por `SOURCE + ID`, baixa
o TXT em memória e só então o guarda no MinIO antes de inserir na Gold. Os
módulos estão em `infrastructure/folhapress/`: `health`, `auth`, `catalog`,
`extractor` e `downloader`.

Para validar login/listagem/download sem gravar no MinIO ou PostgreSQL:

```powershell
.\.venv\Scripts\python.exe scripts/validate_folhapress_access.py --max-pages 1
```

O comando emite apenas contagens, ID e flags de presença de metadados; nunca
imprime credenciais, cookies, título ou corpo de matéria.

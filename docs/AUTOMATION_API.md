# Automation API

## Responsabilidade

A Automation API é a porta privada da ingestão editorial. O n8n a chama para
executar ciclos; ele não recebe acesso direto ao PostgreSQL ou MinIO.

Na Sprint 1, a API possui a fundação para a Gold única, armazenamento bruto e
health checks. A captura da Folhapress entra na Sprint 2; resumo e CRUD interno,
na Sprint 3.

## Endpoints disponíveis

| Endpoint | Uso |
|---|---|
| `GET /health/live` | Confirma que o processo FastAPI está ativo. |
| `GET /health/ready` | Executa `SELECT 1` no PostgreSQL e `HeadBucket` no bucket `bronze-raw` do MinIO. Retorna `503` sem expor erro ou segredo se uma dependência falhar. |
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

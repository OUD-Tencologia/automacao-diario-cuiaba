# Contrato de armazenamento MinIO

**Tarefa do backlog:** `OBJ-01`  
**Ambiente atual:** VPS de homologação já existente

## Buckets físicos

| Bucket configurado | Finalidade | Proteção |
|---|---|---|
| `MINIO_BUCKET_BRONZE` (`bronze-raw`) | TXT original obtido da Folhapress | Versionamento, Object Lock e retenção padrão em `GOVERNANCE` por `MINIO_RETENTION_DAYS`. |
| `MINIO_BUCKET_SILVER` (`silver-processed`) | Artefatos derivados e normalizados, quando a camada Silver precisar deles | Versionamento. |
| `MINIO_BUCKET_GOLD` (`gold-approved`) | Snapshots aprovados e versionados, quando a camada Gold precisar de artefatos | Versionamento. |

Todos os buckets são privados. Não existe política pública de leitura ou escrita.

`GOVERNANCE` protege o conteúdo bruto contra remoção e sobrescrita acidentais
durante a retenção, mas permite uma ação administrativa explícita e auditável
quando houver necessidade operacional. A API também usará chaves determinísticas
e rejeitará sobrescrita; ela será implementada nas tarefas `API-02` e `API-03`.

## Convenção de chaves

| Camada | Padrão reservado |
|---|---|
| Bronze | `folhapress/{AAAA}/{MM}/{DD}/{source_id}.txt` |
| Silver | `folhapress/{source_id}/normalization-v{n}.json` |
| Gold | `folhapress/{source_id}/approved-v{n}.json` |

O `object_key`, SHA-256 e tamanho são sempre persistidos no PostgreSQL; o TXT
não é duplicado como conteúdo primário nas tabelas.

## Provisionamento e validação

O script abaixo usa apenas a conexão SSH e os nomes de bucket presentes no
`.env` local. As credenciais do MinIO são lidas somente da configuração do
container já existente na VPS, não são exibidas e não são gravadas no Git.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/provision_minio_buckets.ps1 -ValidateOnly
powershell -ExecutionPolicy Bypass -File scripts/provision_minio_buckets.ps1
```

A execução completa cria os buckets quando ausentes, confirma saúde, realiza
put/get de conteúdo sintético, reinicia somente o container MinIO da
homologação e confirma a persistência. O probe do bucket Bronze é mantido pela
política de retenção; ele contém apenas texto sintético.

O cliente administrativo temporário vem de `quay.io/minio/mc:latest`, o mesmo
registry da imagem MinIO já observada na VPS. A imagem pode ser substituída pelo
parâmetro `-McImage` quando a infraestrutura fixar uma versão ou digest.

## Limite atual e próxima melhoria

As credenciais configuradas no ambiente de homologação ainda são administrativas.
Antes da produção, criar uma credencial de serviço exclusiva para a Automation
API, limitada aos buckets e operações necessários, e manter a credencial root
somente para administração.

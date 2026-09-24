# Automation API

## Responsabilidade

A Automation API é a porta privada da ingestão editorial. O n8n a chama para
executar ciclos; ele não recebe acesso direto ao PostgreSQL ou MinIO.

Na Sprint 3, a API possui a fundação para Gold única, captura modular da
Folhapress, resumo local e serviço CRUD interno. Na Sprint 4 foram preparados o
workflow n8n inativo e um Compose que adiciona somente a API à rede existente.
A implantação e o ciclo real aguardam a conectividade SSH e os gates de
homologação registrados em `docs/RUNBOOK_HOMOLOGACAO_MVP.md`.

## Endpoints disponíveis

| Endpoint | Uso |
|---|---|
| `GET /health/live` | Confirma que o processo FastAPI está ativo. |
| `GET /health/ready` | Executa `SELECT 1` no PostgreSQL e `HeadBucket` no bucket `bronze-raw` do MinIO. Retorna `503` sem expor erro ou segredo se uma dependência falhar. |
| `POST /automation/folhapress/capture` | Executa um ciclo idempotente para uso exclusivo do n8n. Retorna `502` em falha da fonte para que o n8n faça retry; não publica nem altera itens existentes. |
| `GET /editorial/articles` | Lista notícias com paginação e filtro opcional `status`. |
| `GET /editorial/articles/{source}/{source_id}` | Consulta uma notícia pelo identificador composto. |
| `PATCH /editorial/articles/{source}/{source_id}` | Edita somente os campos editoriais aceitos. Rejeita campos técnicos e `PUBLICADO`. |
| `POST /editorial/articles/{source}/{source_id}/discard` | Define `DESCARTADO`; mantém o registro e o TXT original. |
| `GET /openapi.json` | Expõe o contrato OpenAPI gerado. |

## Configuração local

Em desenvolvimento, a API usa PostgreSQL e MinIO da VPS configurados no
`.env`. `VPS_HOMOLOGATION_HOST` direciona o PostgreSQL local para a VPS. Um
endpoint MinIO explícito é preservado.

Depois de `pip install -e .`, prepare o navegador e o tokenizer local:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m nltk.downloader punkt_tab
```

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

## Orquestração e homologação

O workflow versionado em `workflows/n8n/folhapress-hourly-mvp.json` tem gatilho
manual e cron `0 * * * *`, com timezone `America/Sao_Paulo`. Ele vem inativo,
faz POST apenas para a Automation API, limita timeout/retry e encerra a execução
com erro se as tentativas acabarem. Não guarda credenciais de banco ou MinIO.

`infra/compose/automation-api.compose.yml` não recria serviços existentes e não
publica a porta da API no host. O template das variáveis está ao lado; a cópia
`automation-api.env` é privada e ignorada pelo Git. O primeiro piloto limita
captura a uma página. Nunca iniciar o cron antes de uma captura manual integrada
e idempotente passar; siga todos os gates em `docs/RUNBOOK_HOMOLOGACAO_MVP.md`.

## Resumo e contrato editorial

`SumyLsaEditorialSummary` usa Sumy LSA em português, com dependências NumPy e
`punkt_tab` preparadas na instalação da imagem. O resumo é extrativo e tem no
máximo 150 caracteres. Se não houver frase completa que caiba ou se a geração
falhar, `ds_resumo` fica nulo e a notícia segue para a fila.

O serviço CRUD pode editar chapéu, título, autor, local, corpo de trabalho,
resumo, destaque, tipo, intenção de publicação e status. Identidade, URL da
fonte, hash, chave e metadados do objeto MinIO são somente leitura. `PUBLICADO`
é rejeitado enquanto o Trinix não estiver integrado; descarte é lógico.

Essas rotas são internas e dependem da rede privada da API. Autenticação de
usuários e frontend continuam fora deste corte; não exponha as rotas
editoriais à internet pública.

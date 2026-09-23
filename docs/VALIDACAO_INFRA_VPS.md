# Validação da infraestrutura existente na VPS

**Tarefa do backlog:** `INF-01`  
**Data:** 23/09/2026  
**Método:** conexão SSH por chave, somente leitura

## Serviços validados

| Serviço | Estado | Evidência |
|---|---|---|
| PostgreSQL | Operacional | Aceita conexões na porta configurada; `pg_isready` retornou sucesso dentro do container |
| MinIO | Operacional | Endpoint de saúde retornou HTTP 200 |
| n8n | Operacional | Endpoint de saúde retornou HTTP 200 |

Foram localizados os volumes persistentes de PostgreSQL, MinIO e n8n, além da
rede Docker dedicada `automacao-editorial_interna`.

## Capacidade observada

- Disco da VPS: aproximadamente 37,5 GB disponíveis (22% utilizado).
- Três containers em execução e três volumes ativos.
- A configuração Docker Compose existente foi validada sem erro.

## Decisão de desenvolvimento

Não será criado um segundo PostgreSQL, MinIO ou n8n local. A API será
desenvolvida localmente e consumirá os serviços já existentes na VPS usando o
arquivo `.env` local, que não é versionado.

## Risco registrado

No estado observado, PostgreSQL (5432), MinIO/S3 (9000), console MinIO (9001)
e n8n (5678) estão publicados para a interface de rede da VPS. Isso atende o
desenvolvimento local direto solicitado, porém contraria a recomendação de
isolar banco e armazenamento em rede Docker interna.

Não foi feita alteração remota. Antes de produção, a infraestrutura deverá
restringir essas portas por firewall/VPN ou adotar acesso por túnel SSH.

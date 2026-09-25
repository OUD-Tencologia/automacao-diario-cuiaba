# Status da correção da captura Folhapress — 25/09/2026

Este arquivo registra o estado vigente após a correção do extrator e o
reprocessamento dos TXT que já estavam no MinIO. Ele complementa os
checkpoints históricos de `CORRECAO_CAPTURA_FOLHAPRESS.md`.

## Implementação vigente

- Release implantada na API: `b5c8414`.
- Versão do contrato de extração: `4`.
- Chapéu, título, data, autor e local são lidos primeiro do cabeçalho real do
  TXT da Folhapress.
- O parser não aceita JavaScript, `datepicker` ou texto arbitrário como local.
- Locais compostos são aceitos, como `Londres, Inglaterra` e `São Paulo, SP e
  Brasília, DF`.
- O reparo usa os TXT imutáveis do MinIO e não chama novamente a Folhapress.
- O reparo só atualiza itens em `FILA_EDITORIAL`, preservando curadoria que
  eventualmente já tenha sido feita.

## Resultado do reparo

Comando executado:

```sh
docker exec automacao-editorial-api-automation-api-1 \
  python -m automation_api.cli.repair_folhapress_txt_metadata --limit 100
```

Resultado: `scanned=86`, `repaired=86`, `skipped=0`, `failed=0`.

Auditoria da tabela `gold.articles` para `source='folhapress'`:

| Campo | Resultado |
|---|---:|
| Total de registros | 86 |
| Chapéu preenchido | 86 |
| Título preenchido | 86 |
| Título genérico `Folhapress` | 0 |
| Data preenchida | 86 |
| Local preenchido | 72 |
| Local contendo JavaScript/datepicker | 0 |
| Autor preenchido | 79 |
| Contrato de extração 4 | 86 |

Os 14 registros sem local e os 7 sem autor não apresentam esses dados no TXT
original. Permanecem nulos para revisão editorial; nenhum valor foi inferido.

## Infraestrutura validada

- API: `healthy`.
- `/health/ready`: PostgreSQL e MinIO em `up`.
- n8n alcança a API pela rede interna e recebeu HTTP `200` no health check.
- PostgreSQL, MinIO e n8n não foram recriados nem reiniciados durante a troca;
  somente o container da API foi atualizado.

## Testes

- 112 testes unitários aprovados localmente.
- O ciclo anterior de captura real concluiu 22/22 itens, sem falhas, e os
  retries trataram instabilidades transitórias da Folhapress.

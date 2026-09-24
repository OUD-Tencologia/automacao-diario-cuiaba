# Estado atual da persistência editorial

**Referência:** 24/09/2026  
**Situação:** contrato do MVP enxuto versionado; nenhuma migration editorial foi
aplicada ainda na base de homologação.

## Decisão vigente

O modelo físico Bronze/Silver/Gold originalmente planejado foi substituído para
este MVP. Ele permanece no repositório apenas como histórico e **não deve ser
aplicado** na VPS.

O modelo que será aplicado é:

```text
Folhapress TXT original -> MinIO / bronze-raw
Metadados e conteúdo editorial editável -> PostgreSQL / gold.articles
```

Não existem tabelas Bronze, Silver, operacional, usuários ou perfis neste
corte. O futuro Admin consome uma API; ele não acessa o PostgreSQL diretamente.

## Migration aplicável

| Arquivo | Estado | Uso |
|---|---|---|
| `001_initial_editorial_schema.sql` | histórico | Não aplicar no MVP. Contém o desenho anterior com Bronze/Silver/Gold. |
| `002_mvp_single_gold_schema.sql` | vigente | Única migration editorial a aplicar, após backup e validação. |
| `002_mvp_single_gold_schema.down.sql` | proteção | Interrompe rollback automático, pois um `DROP` apagaria conteúdo editorial. |

A migration `002` aborta se encontrar dados em estruturas legadas. Caso os
schemas antigos estejam vazios, ela os remove sem `CASCADE` e cria somente
`gold.articles`.

## Tabela prevista: `gold.articles`

| Grupo | Colunas |
|---|---|
| Identificação | `source`, `id` (chave primária composta), `source_url` |
| Editorial | `dt_noticia`, `ds_chapeu`, `ds_titulo`, `nm_autor`, `ds_local`, `ds_noticia`, `ds_resumo` |
| Decisão editorial | `destaque`, `tipo_de_conteudo`, `publicar_imediatamente`, `status` |
| Contraprova do original | `minio_bucket`, `minio_object_key`, `raw_sha256`, `raw_size_bytes`, `raw_metadata` (JSONB) |
| Auditoria | `created_at`, `update_at` |

Regras importantes:

- A identidade da notícia é `source + id`; para Folhapress, `id` vem da URL.
- A recaptura não cria nova linha nem atualiza conteúdo que um editor já tenha
  alterado.
- `ds_noticia` é uma cópia de trabalho editável; o TXT original fica no MinIO
  e não é alterado.
- `ds_resumo` aceita no máximo 150 caracteres e pode permanecer nulo se o
  sumarizador falhar.
- Os valores iniciais são `FILA_EDITORIAL`, `INTERNO`, `false` para destaque e
  `false` para publicação imediata.
- A remoção física é bloqueada no banco. Para descartar, usar
  `status = DESCARTADO`.
- `PUBLICADO` jamais é definido automaticamente: depende de ação humana e da
  futura integração Trinix.

## Aplicação segura na homologação

A Sprint 4 é responsável pela aplicação real. A ordem obrigatória é:

1. Fazer backup lógico do banco de homologação.
2. Confirmar que não há dados nas estruturas legadas.
3. Rodar `python scripts/validate_single_gold_migration.py`, que valida o fluxo
   em banco temporário e o remove ao final.
4. Aplicar exclusivamente `002_mvp_single_gold_schema.sql`.
5. Conferir `gold.articles`, os índices e os triggers de `update_at` e bloqueio
   de `DELETE`.

O detalhamento de execução está em
[`infra/migrations/README.md`](../infra/migrations/README.md), e o plano em
[`PLANO_EXECUCAO_MVP_ENXUTO.md`](PLANO_EXECUCAO_MVP_ENXUTO.md).

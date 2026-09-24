# Plano de Execução - MVP Enxuto de Automação Editorial

**Status:** pronto para execução, sem estimativas ou datas artificiais.

## Objetivo

Entregar uma automação horária da Folhapress: login, descoberta de matérias
novas, download do TXT, guarda do original no MinIO, persistência em uma única
tabela Gold, resumo local sugerido e contrato de edição para o Admin futuro.

Não entram neste MVP: Bronze/Silver no PostgreSQL, front-end, Radar/concorrentes,
Estadão, autenticação de pessoas, produção, domínio, IA generativa e integração
real com o Trinix.

## Arquitetura reduzida

```text
n8n - cron de uma hora
  -> Automation API privada
      -> source_health -> folhapress_auth -> folhapress_catalog
      -> article_extractor -> txt_downloader -> raw_storage
      -> gold_news_repository -> editorial_summary
      -> PublisherPort do Trinix desabilitado
```

- O n8n agenda, chama a API e faz retry; não grava em PostgreSQL ou MinIO.
- A API de captura é privada e tem o n8n como único chamador.
- CRUD é entregue como serviço, repositório e contrato interno para o Admin;
  não haverá front-end nem acesso de navegador diretamente ao banco.
- MinIO `bronze-raw` guarda o TXT imutável. `gold.articles` é a única tabela
  editorial.

## Contrato editorial congelado

```text
ID, SOURCE, DT_NOTICIA, DS_CHAPEU, DS_TITULO, NM_AUTOR,
DS_LOCAL, DS_NOTICIA, DS_RESUMO, DESTAQUE, TIPO_DE_CONTEUDO,
PUBLICAR_IMEDIATAMENTE, STATUS, CREATED_AT, UPDATE_AT
```

Campos técnicos obrigatórios: `SOURCE_URL`, `MINIO_BUCKET`,
`MINIO_OBJECT_KEY`, `RAW_SHA256`, `RAW_SIZE_BYTES` e `RAW_METADATA` (JSONB).

- `ID` é o ID no link da fonte; a deduplicação é `SOURCE + ID`.
- `DT_NOTICIA` preserva data/hora em `America/Sao_Paulo`.
- `DS_CHAPEU` é a etiqueta completa; `DS_LOCAL` é normalizado para apresentação.
- `DS_NOTICIA` é editável; o TXT original no MinIO nunca é alterado.
- Valores iniciais: `FILA_EDITORIAL`, `DESTAQUE=false`, `INTERNO` e
  `PUBLICAR_IMEDIATAMENTE=false`.
- Estados: `FILA_EDITORIAL`, `EM_EDICAO`, `REVISAO`, `APROVADO`, `DESCARTADO`
  e `PUBLICADO`. Este último só existe após ação humana no Trinix.
- Descarte é lógico (`STATUS=DESCARTADO`); não existe exclusão física.

## Sprint 0 - Base replanejada

**Estado: concluída.**

- PoC manual da Folhapress validada: login, textos, paginação e TXT.
- PostgreSQL e MinIO da VPS validados pela API local (`/health/ready` retorna
  200).
- `.env` e `.env.example` contêm apenas configuração do MVP.
- O modelo anterior Bronze/Silver/Gold foi marcado como obsoleto e não será
  aplicado na homologação.

## Sprint 1 - Gold única e armazenamento bruto

**Objetivo:** deixar a persistência final pronta antes de capturar dados reais.

**Estado: concluída.** Migration validada em banco temporário e removida ao
fim do teste; upload idempotente de TXT sintético validado no MinIO da VPS.

1. Criar migration de transição para `gold.articles`.
2. Fazer a migration abortar se houver dados no modelo antigo antes de remover
   as estruturas vazias Bronze/Silver/Gold.
3. Criar colunas editoriais e técnicas, `CHECK` de tipos/status, índices de fila
   e unicidade `SOURCE + ID`.
4. Implementar domínio `News`, validações e `gold_news_repository`.
5. Implementar deduplicação: recaptura não cria linha, não duplica TXT e não
   sobrescreve edição editorial.
6. Implementar `raw_storage`: objeto com fonte, ID e SHA-256; validar tamanho,
   hash e existência no `bronze-raw`.
7. Ajustar health do MinIO para testar o bucket `bronze-raw`, não listar todos
   os buckets.
8. Corrigir a descoberta/execução padronizada dos testes.

**Aceite e testes:** migration em banco vazio; proteção contra dados antigos;
inserção/consulta/duplicidade; upload e leitura de TXT sanitizado; nenhuma
sobrescrita; health retorna 200 apenas com banco e bucket utilizáveis.

**Commit:** `feat(sprint-01): cria gold unica e armazenamento bruto`

## Sprint 2 - Adaptador Folhapress

**Objetivo:** automatizar o caminho já comprovado manualmente.

**Estado:** implementação e testes sintéticos concluídos. A validação externa
controlada não persistiu dados, mas ficou pendente de nova execução porque a
Folhapress retornou `ERR_CONNECTION_RESET` ao Chromium automatizado antes do
login em 24/09/2026. O adaptador trata essa condição como falha reexecutável;
o comando de confirmação é `python scripts/validate_folhapress_access.py
--max-pages 1` quando a origem normalizar.

1. Criar configuração tipada da fonte e validar variáveis obrigatórias.
2. Implementar `source_health` sem vazar segredo ou conteúdo em log.
3. Implementar `folhapress_auth`, sessão isolada e renovação após expiração.
4. Implementar `folhapress_catalog`: `TEXTOS`, `SERVIÇO NOTICIOSO`, filtros
   configuráveis e paginação de 24 itens.
5. Implementar `article_extractor`: ID, chapéu, título, autor, data/hora,
   local, URLs e conteúdo.
6. Normalizar data/hora e local sem inventar campos ausentes.
7. Implementar `txt_downloader` com espera explícita e SHA-256.
8. Implementar `capture_folhapress`: descobrir, deduplicar, baixar, guardar e
   persistir item completo na Gold.

**Aceite e testes:** fakes de navegador/HTML/TXT sanitizado; teste controlado
de login, página e download reais; item inicia em `FILA_EDITORIAL`; reexecução
não duplica; falha de login, página, download ou MinIO não cria item incompleto.

**Commit:** `feat(sprint-02): automatiza captura folhapress`

## Sprint 3 - Resumo e CRUD editorial interno

**Objetivo:** tornar a notícia utilizável pelo futuro Admin, sem criar front-end.

**Estado: concluída.** Sumy LSA instalado localmente; NumPy e `punkt_tab`
incluídos como dependências de produção e preparação da imagem. CRUD de lista,
detalhe, edição e descarte implementado; `PUBLICADO` continua bloqueado sem
Trinix. Sem migration adicional: `ds_resumo` já faz parte da migration `002`.

1. Adicionar `sumy` e tokenização portuguesa como dependência de produção.
2. Implementar `editorial_summary` com LSA extrativo e entrada `DS_NOTICIA`.
3. Gerar sugestão de no máximo 150 caracteres, priorizando frases completas e
   sem cortar palavras.
4. Salvar em `DS_RESUMO`; falha deixa resumo nulo e registra log sem interromper
   a captura.
5. Implementar `list_news`, `get_news`, `update_news` e `discard_news`.
6. Limitar atualizações a campos editoriais/estado e atualizar `UPDATE_AT`.
7. Publicar OpenAPI interno de lista, detalhe, edição e descarte.
8. Criar `PublisherPort` e adaptador Trinix desabilitado, sem conexão externa.

**Aceite e testes:** português/acentuação/texto vazio/limite do resumo; edição
não altera objeto ou hash no MinIO; descarte não exclui linha; contrato rejeita
estado inválido; Trinix não faz chamada nem marca `PUBLICADO`.

**Validação:** 63 testes unitários passaram na revisão final, incluindo resumo
em português, rotas OpenAPI, limites de edição, descarte lógico e adaptador
Trinix inativo.

**Commit:** `feat(sprint-03): adiciona resumo e crud editorial`

## Sprint 4 - n8n e homologação integrada

**Objetivo:** transformar a automação em ciclo horário na VPS.

1. Versionar workflow n8n com cron `0 * * * *`.
2. Configurar chamada privada, timeout, retry limitado e erro rastreável no n8n.
3. Implantar somente a API na rede Docker dos serviços existentes na VPS; não
   criar PostgreSQL, MinIO ou n8n locais adicionais.
4. Fazer backup lógico e confirmar que não existem dados antes de aplicar a
   migration Gold.
5. Executar ciclo controlado de uma página: Folhapress -> MinIO -> Gold ->
   resumo.
6. Ativar o cron apenas depois do ciclo manual integrado passar.
7. Criar runbook de configuração, reinício e reprocessamento.

**Aceite e testes:** workflow importável; execução manual; erro transitório e
retry esgotado; n8n sem credencial de banco/MinIO; persistência após reinício;
próximo ciclo idempotente.

**Commit:** `feat(sprint-04): orquestra mvp na homologacao`

## Sprint 5 - Aceite técnico e handoff

**Objetivo:** entregar o MVP reproduzível e pronto para o Admin futuro.

1. Rodar testes unitários, integração e contrato finais.
2. Revisar Git e logs para não haver segredo, cookie ou conteúdo licenciado
   indevido.
3. Atualizar README, OpenAPI, schema Gold e runbook.
4. Documentar responsabilidades do Admin/frontend e pendências do Trinix.
5. Demonstrar captura, TXT original, resumo de 150 caracteres, edição e
   descarte lógico.

**Aceite final:** cron horário funcional; captura configurada e idempotente;
TXT verificável no `bronze-raw`; Gold única completa; resumo local apenas como
sugestão; CRUD interno sem exclusão física; Trinix inativo e preparado.

**Commit:** `docs(sprint-05): finaliza aceite do mvp enxuto`

## Regras de qualidade mínima

- Cada sprint termina com testes verdes, revisão de diff e commit próprio.
- Migrations são testadas antes da homologação.
- Logs nunca contêm senha, cookie, token ou corpo integral da matéria.
- Reprocessamento é sempre idempotente.
- Alterações em schema, workflow ou OpenAPI atualizam a documentação.

## Pendências não bloqueantes

Trinix, Estadão, Radar, front-end, autenticação, produção, domínio e eventual
modelo generativo local permanecem fora deste MVP.

# Plano de Execução do MVP - Automação de Captura Editorial

**Status:** aprovado para execução  
**Início:** 22/09/2026  
**Capacidade:** 2,5 horas por dia, de segunda a sábado  
**Esforço planejado:** 62 horas / 24,8 dias de trabalho  
**Previsão de aceite técnico:** 21/10/2026  
**Feriado considerado:** 12/10/2026  

## 1. Objetivo e fontes de decisão

Entregar o MVP de automação que captura notícias licenciadas da Folhapress, preserva o TXT original, normaliza os dados e disponibiliza o conteúdo aprovado para a futura integração com o Trinix.

Este plano é fiel às seguintes fontes, nesta ordem de aplicação:

1. Decisões do gestor e o HTML `1.Arquitetura de Design System/Arquitetura Central Editorial.html`.
2. Documento técnico aprovado e backlog aprovado.
3. PDF de anotações operacionais da Folhapress.

Quando houver uma dependência externa sem acesso disponível, o plano não cria solução alternativa fora da arquitetura. Registra a pendência, implementa o contrato/porta necessário e segue com o restante do MVP.

### Escopo do MVP

- Fonte inicial: Folhapress.
- Orquestração: n8n, com ciclo de uma hora (`0 * * * *`).
- Captura: Python + Playwright, com login, filtro em `TEXTOS`, paginação, metadados e download do TXT.
- Persistência: PostgreSQL com Bronze, Silver, Gold e dados operacionais; JSONB para metadados brutos flexíveis.
- Armazenamento de objetos: MinIO/S3 para o TXT original, imutável.
- Backend: FastAPI, OpenAPI, deduplicação, auditoria e regras de promoção entre camadas.
- Ambiente: Docker Compose local e VPS de homologação.
- Meta operacional: 200 notícias por dia, monitorada como meta e alerta de volume, não como limite rígido codificado.

### Fora do escopo atual

- Front-end e autenticação de pessoas.
- IA, RAG, agentes e enriquecimento automático.
- Imagens: nesta fase, somente texto e URL de origem; não baixar, processar ou armazenar imagens.
- Adaptador do Estadão Conteúdo.
- Produção, domínio, DNS e TLS público.
- Integração real com o Trinix enquanto não houver acesso, DDL e credenciais.

## 2. Arquitetura que deve ser respeitada

```text
n8n (cron horário)
  -> Scraper Folhapress (Playwright)
  -> Automation API (FastAPI)
  -> MinIO: TXT original, imutável, com object_key e hash
  -> Bronze: metadados brutos + referência ao objeto
  -> Silver: dados normalizados para curadoria futura
  -> Gold: snapshot aprovado e versionado
  -> Trinix: escrita direta no banco, somente quando o acesso existir
```

### Regras estruturais obrigatórias

1. O n8n orquestra. Ele não contém regra de negócio nem grava diretamente nas tabelas Bronze, Silver ou Gold. O workflow chama a Automation API.
2. A Automation API concentra deduplicação, persistência, transições de estado, auditoria, idempotência e reconciliação.
3. O PostgreSQL é o banco de dados. JSONB é um tipo de coluna para `metadado_bruto`; não existe banco NoSQL separado no MVP.
4. O TXT original não é sobrescrito e não fica armazenado como cópia primária no PostgreSQL. Ele fica no MinIO, com `object_key`, hash e timestamp de captura registrados no banco.
5. Bronze é imutável. Silver contém a normalização e a futura edição editorial. Gold é um snapshot versionado do aprovado.
6. A deduplicação usa `source + source_id` como chave de negócio. O hash do TXT é usado para integridade, auditoria e detecção de alteração, não como única chave de identidade.
7. A integração definitiva com o Trinix segue o HTML de arquitetura: acesso direto ao banco do Trinix, sobre TLS, com credencial em Vault ou Docker secrets. Webhook, push via API e pull foram avaliados e não são parte da solução aprovada.
8. Enquanto o Trinix não disponibilizar acesso, DDL, permissões e homologação, existe somente uma porta/fake adapter. Nenhum envio real será simulado como concluído.
9. PostgreSQL e MinIO ficam em rede interna Docker. Somente o proxy Traefik poderá ser exposto quando houver domínio/DNS e decisão de TLS público.
10. Segredos não entram no Git. O `.env` local fica ignorado; somente `.env.example` pode ser versionado. No MVP, Docker secrets pode substituir Vault quando necessário.

## 3. Contratos a congelar antes da implementação

O primeiro sprint termina com estes contratos escritos e versionados. Qualquer mudança posterior exige atualização do contrato, teste e commit do sprint correspondente.

### 3.1 Contrato de origem Folhapress

| Item | Regra do MVP |
|---|---|
| Acesso | `LOGIN` -> `ENTRAR` -> `TEXTOS` -> `SERVIÇO NOTICIOSO`. |
| Fonte de filtros | Os filtros existentes no menu `TEXTOS` são a fonte de seleção. Não codificar um de-para editorial sem confirmação. |
| Exclusão confirmada | `Exterior` fica fora. |
| Categoria pendente | `Cultura` e `Notícias` dependem do alinhamento do grupo. A lista de filtros deve ser configurável. |
| Paginação | 24 registros por página; sequência observada `sr=1`, `sr=25`, `sr=49`, `sr=73` etc. O scraper encerra ao não receber mais resultados elegíveis. |
| Identidade | O ID numérico da URL da Folhapress é `source_id`. Ex.: `/texto/{source_id}`. |
| Download | O TXT é obtido por `/texto/{source_id}/baixar`, respeitando a sessão autenticada e espera explícita pelo download. |
| Meta | Monitorar 200 notícias/dia no fuso `America/Sao_Paulo`. |
| Conteúdo | Capturar texto e URL de origem. Imagens estão fora do MVP. |
| Regra editorial | Conteúdo sem autor/assinatura não pode ser promovido para Gold/publicado. |

As URLs reais, credenciais e IDs de filtro da Folhapress não devem ser gravados em código ou documentação versionada. A PoC valida esses dados e os mantém como configuração segura.

### 3.2 Contrato mínimo de dados

Os nomes finais de colunas são definidos em migration no `DAT-01`, mas estes campos são obrigatórios como conceito:

| Camada | Dados mínimos | Invariantes |
|---|---|---|
| Operacional | `run_id`, início/fim, status, tentativas, erro, volume capturado | Permite reprocessar e auditar cada ciclo horário. |
| Bronze | `source`, `source_id`, título, autor, URL da matéria, URL de download, categoria de origem, data de origem, captura, `content_hash`, `object_key`, `metadado_bruto` JSONB | Uma linha por `source + source_id`; nunca alterar o payload bruto. |
| MinIO | TXT original, chave de objeto, hash e metadados de captura | Objeto imutável, persistente e recuperável. |
| Silver | referência Bronze, campos normalizados, conteúdo para curadoria, estado e trilha de auditoria | Não apaga o Bronze; mantém vínculo com a origem. |
| Gold | referência Silver, versão, conteúdo aprovado, autor/assinatura e instante da aprovação | É criado somente por promoção válida; sem autor não pode ser criado. |

### 3.3 Regras de consistência entre banco e objeto

1. Gerar uma `object_key` determinística e enviar o TXT ao MinIO.
2. Conferir hash, tamanho e existência do objeto.
3. Persistir a referência no Bronze de forma idempotente.
4. Se houver falha parcial, registrar o ciclo como pendente/falho e reconciliar no reprocessamento. Não aceitar arquivo órfão ou linha Bronze sem objeto válido como sucesso.
5. Repetir a mesma captura não cria segunda notícia nem sobrescreve o TXT original.

## 4. Preparação obrigatória antes do primeiro código

### Estrutura inicial do repositório

```text
apps/
  automation_api/
    src/
      domain/
      application/
      adapters/folhapress/
      infrastructure/
infra/
  compose/
  migrations/
  monitoring/
workflows/
  n8n/
tests/
  unit/
  integration/
  fixtures/
docs/
```

### Checklist do dia 22/09

- [ ] Criar o repositório remoto e a branch padrão `main`.
- [ ] Criar `.gitignore`, `.env.example`, README e esta documentação em `docs/`.
- [ ] Confirmar que `.env` não será versionado e não contém credenciais no histórico Git.
- [ ] Definir convenção de branches: `feat/PLN-01`, `feat/SRC-01`, `feat/OBJ-01` etc.
- [ ] Registrar o contrato de dados e a decisão de fronteira do Trinix nesta documentação.
- [ ] Criar fixtures sanitizadas. Não versionar TXT licenciado nem credenciais da Folhapress sem autorização explícita.
- [ ] Validar manualmente que o acesso Folhapress permite chegar ao menu `TEXTOS`; registrar somente evidências não sensíveis.

O commit inicial de bootstrap pode ocorrer no primeiro dia. Ele não substitui o commit obrigatório de encerramento de sprint.

## 5. Sprints de execução

Cada sprint termina somente depois de todos os itens planejados, testes e critérios de aceite estarem verdes. O commit de encerramento é obrigatório e deve conter código, migrations, workflows exportados, testes, documentação e configuração não sensível relacionados ao sprint.

### Mapa cronológico do backlog aprovado

| Sprint | ID | Período da tarefa | Esforço |
|---|---|---:|---:|
| 1 | `PLN-01` | 22/09 a 23/09 | 4h |
| 1 | `SRC-01` | 23/09 a 25/09 | 4h |
| 1 | `INF-01` | 25/09 a 26/09 | 4h |
| 1 | `DAT-01` | 26/09 a 28/09 | 3h |
| 2 | `OBJ-01` | 29/09 a 30/09 | 3h |
| 2 | `API-01` | 30/09 a 01/10 | 4h |
| 3 | `SRC-02` | 02/10 a 05/10 | 6h |
| 3 | `API-02` | 05/10 a 07/10 | 6h |
| 3 | `API-03` | 07/10 a 10/10 | 6h |
| 3 | `API-04` | 10/10 | 2h |
| 4 | `AUT-01` | 13/10 a 15/10 | 6h |
| 4 | `OBS-01` | 15/10 a 16/10 | 2h |
| 4 | `TST-01` | 16/10 a 17/10 | 4h |
| 5 | `HML-01` | 19/10 a 20/10 | 4h |
| 5 | `DOC-01` | 20/10 a 21/10 | 4h |

### Sprint 1 - Base, PoC e modelo inicial

**Período:** 22/09 a 28/09 (dias úteis: 22 a 26 e 28)  
**Esforço:** 15h  
**Backlog:** `PLN-01`, `SRC-01`, `INF-01`, `DAT-01`

#### Tarefas

1. `PLN-01` - Consolidar requisitos do MVP, criar repositório e registrar decisões de arquitetura.
2. `SRC-01` - Executar a PoC Folhapress: login, `TEXTOS`, `SERVIÇO NOTICIOSO`, filtro, paginação e um download de TXT.
3. `INF-01` - Preparar Docker Compose local e a referência de homologação: rede interna, volumes persistentes e health checks básicos.
4. `DAT-01` - Criar schemas/tabelas físicas Bronze, Silver, Gold e operacional; migrations, índices e massa sanitizada de teste.

#### Testes e aceite

- `docker compose config` sem variáveis ausentes obrigatórias.
- Migration sobe em banco vazio e cria as tabelas/esquemas esperados.
- Consulta por `source + source_id` usa índice único ou regra equivalente de idempotência.
- PoC demonstra login, menu `TEXTOS`, uma página de resultados, cálculo da próxima página e um TXT obtido com sessão válida.
- Nenhuma credencial, cookie ou TXT licenciado é gravado no repositório.

#### Commit obrigatório

**Data:** 28/09  
**Mensagem:** `feat(sprint-01): base do projeto, poc folhapress e modelo inicial`

### Sprint 2 - Objetos e base da API

**Período:** 29/09 a 01/10  
**Esforço:** 7h  
**Backlog:** `OBJ-01`, `API-01`

#### Tarefas

1. `OBJ-01` - Subir MinIO em container, criar buckets `bronze-raw`, `silver-processed` e `gold-approved`, configurar volume e health check.
2. `API-01` - Criar o esqueleto FastAPI, health checks, acesso PostgreSQL, repositórios e OpenAPI inicial.

#### Testes e aceite

- MinIO inicia com volume persistente.
- Put/get de TXT sanitizado funciona em cada bucket aplicável.
- Reinício do container mantém o objeto e o bucket.
- API inicia em container, expõe health check e gera OpenAPI sem erro.
- Falha do PostgreSQL ou MinIO deixa health/status inadequado de forma visível, sem falso sucesso.

#### Commit obrigatório

**Data:** 01/10  
**Mensagem:** `feat(sprint-02): minio persistente e base da automation api`

### Sprint 3 - Captura, Bronze, Silver, Gold e contrato v1

**Período:** 02/10 a 10/10 (sem atividade em 04/10)  
**Esforço:** 20h  
**Backlog:** `SRC-02`, `API-02`, `API-03`, `API-04`

#### Tarefas

1. `SRC-02` - Implementar o adapter Folhapress com Playwright, configuração de filtros, paginação por 24 itens, espera explícita e download do TXT.
2. `API-02` - Implementar deduplicação por `source + source_id`, cálculo de hash, upload ao MinIO, Bronze idempotente e reconciliação de falha parcial.
3. `API-03` - Implementar normalização Bronze -> Silver, auditoria, versionamento e promoção Silver -> Gold.
4. `API-04` - Publicar e versionar o contrato OpenAPI para o futuro front-end, sem implementar o front-end.

#### Testes e aceite

- Adapter: login, configuração de filtro, páginas `sr=1/25/49`, fim de paginação e timeout de download cobertos por teste/fake controlado.
- Fonte: o mesmo `source_id` em nova execução não cria novo Bronze.
- Integridade: Bronze aponta para objeto existente; `object_key`, hash e tamanho são conferidos.
- Falha parcial: erro entre MinIO e PostgreSQL gera estado rastreável e o reprocessamento converge sem duplicidade.
- Bronze permanece imutável após Silver e Gold serem criados.
- Promoção sem autor/assinatura falha de modo explícito; promoção válida cria Gold versionado e evento de auditoria.
- JSONB preserva o metadado bruto sem substituir os campos relacionais obrigatórios.
- OpenAPI descreve leitura da Silver e promoção para Gold; qualquer incompatibilidade é corrigida antes do commit.

#### Marco e commit obrigatório

**Marco:** 10/10 - Captura, MinIO, Bronze, Silver e Gold funcionais.  
**Mensagem:** `feat(sprint-03): captura folhapress e pipeline bronze-silver-gold`

### Sprint 4 - Orquestração, observabilidade e qualidade

**Período:** 13/10 a 17/10 (12/10 é feriado)  
**Esforço:** 12h  
**Backlog:** `AUT-01`, `OBS-01`, `TST-01`

#### Tarefas

1. `AUT-01` - Criar workflow n8n com cron `0 * * * *`, chamada à Automation API, retry limitado, tratamento de erro e reprocessamento controlado.
2. `OBS-01` - Configurar logs estruturados, métricas mínimas, health checks e alerta para serviço indisponível ou volume abaixo da meta diária.
3. `TST-01` - Consolidar testes unitários e de integração do ciclo crítico.

#### Testes e aceite

- Importação do workflow n8n funciona a partir do arquivo versionado.
- Cron, execução manual, erro transitório, retry esgotado e reprocessamento são testados.
- O n8n não grava diretamente no banco; toda gravação passa pela API.
- Métricas distinguem sucesso, falha, tentativa, itens encontrados, itens novos, duplicados e falhas de objeto.
- Health checks validam API, PostgreSQL, MinIO e n8n.
- Fluxo local completo: Folhapress/fake controlado -> TXT/MinIO -> Bronze -> Silver -> Gold.

#### Marco e commit obrigatório

**Marco:** 15/10 - n8n com retentativas pronto.  
**Mensagem:** `feat(sprint-04): orquestracao, observabilidade e testes criticos`

### Sprint 5 - Homologação, documentação e aceite

**Período:** 19/10 a 21/10  
**Esforço:** 8h  
**Backlog:** `HML-01`, `DOC-01`

#### Tarefas

1. `HML-01` - Implantar Docker Compose na VPS de homologação e executar piloto técnico controlado.
2. `DOC-01` - Finalizar runbook, instruções de backup/restore, OpenAPI, checklist de aceite e handoff técnico.

#### Testes e aceite

- A VPS sobe os serviços com volumes persistentes, rede interna e health checks saudáveis.
- Executar uma captura piloto licenciada/controlada e comprovar o fluxo Folhapress -> MinIO -> Bronze -> Silver -> Gold.
- Reiniciar os serviços e confirmar persistência do PostgreSQL e MinIO.
- Executar teste de backup e restore conforme o runbook.
- Revisar logs, alertas, métricas e registros de auditoria.
- Confirmar que não há credenciais em Git, imagens no fluxo ou chamadas reais ao Trinix sem acesso autorizado.

#### Marco e commit obrigatório

**Marco:** 20/10 - piloto de homologação concluído.  
**Aceite técnico:** 21/10.  
**Mensagem:** `docs(sprint-05): homologacao, runbook e aceite tecnico do mvp`

## 6. Estratégia de testes contínuos

| Nível | Quando executar | Cobertura mínima |
|---|---|---|
| Unitário | A cada alteração de domínio/adapter | hash, normalização, validação de autor, idempotência, configuração de filtros e transições Bronze/Silver/Gold. |
| Integração | Ao terminar cada tarefa de infraestrutura ou persistência | migrations, PostgreSQL, MinIO, upload/download, reconciliação e repositórios. |
| Contrato | Ao alterar a API | OpenAPI versionado, campos obrigatórios, respostas de erro e compatibilidade do contrato futuro do front-end. |
| Fluxo local | Ao fim dos Sprints 3 e 4 | captura controlada -> objeto -> Bronze -> Silver -> Gold; retry e reprocessamento. |
| Homologação | Sprint 5 | Compose na VPS, persistência após restart, ciclo completo, logs, métricas, alertas e backup/restore. |

Não existe critério de cobertura percentual aprovado. A exigência deste plano é cobrir integralmente o caminho crítico e os cenários de falha descritos acima; nenhum sprint fecha com teste crítico pendente ou falhando.

## 7. Política de commits, revisão e entrega

1. Trabalhar em branch por tarefa ou agrupamento coerente de tarefas.
2. Um commit pode ser feito durante o trabalho, mas o commit de encerramento de cada sprint é obrigatório nas datas deste plano.
3. Antes do commit de sprint, executar os testes aplicáveis, atualizar migrations/OpenAPI/workflows/docs e revisar o diff para garantir que não há `.env`, chaves, tokens, cookies ou dados licenciados indevidos.
4. Usar Conventional Commits com ID do backlog quando aplicável: `feat(SRC-02): ...`, `test(API-02): ...`, `docs(DOC-01): ...`.
5. Criar tag de referência após cada encerramento: `sprint-01` a `sprint-05`.
6. Não alterar schemas Bronze/Silver/Gold, contratos OpenAPI ou workflow n8n sem migration/versão, teste de compatibilidade e registro no commit.

### Gate obrigatório de final de sprint

- [ ] Todas as tarefas do sprint atendem ao critério de aceite do backlog.
- [ ] Testes unitários, integração e contrato aplicáveis estão verdes.
- [ ] `docker compose config` está válido quando houver alteração de Compose.
- [ ] Migrations sobem em banco vazio e, quando aplicável, têm caminho de rollback testado.
- [ ] MinIO e PostgreSQL preservam dados após reinício quando forem alterados.
- [ ] OpenAPI e workflow n8n exportado estão versionados quando alterados.
- [ ] Nenhum segredo ou dado licenciado não autorizado foi adicionado ao Git.
- [ ] README/runbook/decisões foram atualizados.
- [ ] Commit de sprint e tag foram criados.

## 8. Pendências e gates externos

| Pendência | Impacto | Tratamento no MVP |
|---|---|---|
| Credenciais e PoC Folhapress | Bloqueia captura real, não bloqueia setup e testes com fixture | Validar no `SRC-01`; manter segredo fora do Git. |
| Filtros de categoria Folhapress | Configuração de captura | Configurável; Exterior excluído; Cultura/Notícias aguardam decisão do grupo. |
| Trinix: acesso, DDL, permissões e homologação | Bloqueia escrita real no destino | Manter porta/fake adapter. Não substituir por webhook, push ou pull. |
| VPS de produção | Bloqueia operação produtiva | Homologar apenas na VPS atual. |
| Domínio/DNS/TLS público | Bloqueia exposição pública | Traefik/TLS só é ativado após liberação. |
| Front-end e autenticação | Fora do escopo | API é documentada; não implementar interface nem identidade neste MVP. |
| Estadão Conteúdo | Nova fonte | Adapter futuro, isolado do adapter Folhapress. |

## 9. Definição de pronto do MVP técnico

O MVP está pronto para aceite técnico quando todos os itens abaixo forem verdadeiros:

- [ ] Um ciclo n8n horário chama a Automation API e pode ser reprocessado sem duplicidade.
- [ ] O adapter Folhapress captura apenas conteúdo elegível configurado, baixa o TXT e registra a origem.
- [ ] O TXT está no MinIO com volume persistente, hash e `object_key` verificáveis.
- [ ] Bronze, Silver e Gold são tabelas físicas e atendem às regras de imutabilidade, normalização, auditoria e versionamento.
- [ ] Uma notícia sem autor não chega a Gold/publicado.
- [ ] Falhas parciais entre PostgreSQL e MinIO são rastreáveis e recuperáveis.
- [ ] Logs, métricas, health checks e alerta de volume/serviço estão ativos.
- [ ] O fluxo passa localmente e na VPS de homologação.
- [ ] Backup/restore e documentação operacional foram validados.
- [ ] Trinix, produção, domínio, front-end, autenticação, imagens e Estadão permanecem explicitamente fora do aceite atual, salvo nova decisão formal.

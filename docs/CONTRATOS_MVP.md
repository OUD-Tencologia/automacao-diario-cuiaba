# Contratos do MVP Editorial

**Status:** vigente para a implementação inicial  
**Fonte de decisão:** arquitetura aprovada, documento técnico e backlog

Este documento congela as regras funcionais antes do código. Nomes definitivos
de tabelas e colunas serão criados e versionados na migration da tarefa
`DAT-01`; não devem ser inferidos ou alterados sem migration, teste e revisão.

## 1. Fronteiras e responsabilidades

| Componente | Responsabilidade | Não é responsabilidade |
|---|---|---|
| n8n | Disparar o ciclo horário, chamar a API e controlar retentativas | Regra de negócio e escrita direta no banco |
| Scraper Folhapress | Navegar a fonte autenticada e obter metadados/TXT | Persistir camadas editoriais |
| Automation API | Validar, deduplicar, gravar, promover e auditar | Exibir interface de curadoria |
| MinIO | Conservar o TXT original imutável | Armazenar o estado editorial |
| PostgreSQL | Armazenar dados operacionais e camadas Bronze/Silver/Gold | Guardar o TXT primário |
| Trinix | Destino futuro de publicação | Ser integrado antes de acesso e DDL aprovados |

## 2. Contrato da fonte Folhapress

- Fluxo de navegação: `LOGIN` → `ENTRAR` → `TEXTOS` → `SERVIÇO NOTICIOSO`.
- A coleta usa exclusivamente o menu `TEXTOS` e seus filtros configuráveis.
- `Exterior` é excluído.
- `Cultura` e `Notícias` aguardam definição editorial e não serão fixados no código.
- A paginação observada é de 24 itens: `sr=1`, `sr=25`, `sr=49` e assim por diante.
- O identificador numérico da URL é `source_id`; a identidade da matéria é
  `source + source_id`.
- O TXT é obtido na rota de download associada ao `source_id`, usando a sessão
  autenticada e espera explícita de download.
- O hash do TXT comprova integridade e alteração; não substitui a chave de negócio.
- A meta é monitorar 200 notícias por dia no fuso `America/Sao_Paulo`, sem
  transformá-la em bloqueio rígido da coleta.
- Imagens não são coletadas no MVP.

## 3. Contrato de dados e estados

| Camada | Conteúdo mínimo | Regra obrigatória |
|---|---|---|
| Operacional | ciclo, status, tentativa, erro, tempos e contagem de itens | Cada ciclo pode ser auditado e reprocessado |
| Bronze | origem, `source_id`, metadados brutos, hash e referência MinIO | Imutável; uma matéria por `source + source_id` |
| Silver | referência Bronze, campos normalizados e estado de curadoria | Não altera nem apaga Bronze |
| Gold | referência Silver, versão, conteúdo aprovado, autor e aprovação | Só nasce de promoção válida |
| MinIO | TXT original, `object_key`, hash e metadados de captura | Persistente, recuperável e não sobrescrito |

Transições permitidas:

```text
captura válida -> Bronze -> Silver -> Gold/publicado
```

Uma matéria sem autor ou assinatura não pode chegar à Gold/publicado. A Gold é
um snapshot versionado; uma alteração aprovada no futuro cria versão nova, sem
modificar a versão anterior.

## 4. Integridade, falhas e idempotência

1. A API gera uma `object_key` determinística e envia o TXT ao MinIO.
2. A API valida existência, tamanho e hash do objeto.
3. A referência é persistida no Bronze de forma idempotente.
4. Se MinIO ou PostgreSQL falharem parcialmente, o ciclo fica rastreável como
   pendente ou falho e pode ser reconciliado.
5. Uma recaptura do mesmo `source + source_id` não cria nova notícia nem
   sobrescreve o TXT original.

## 5. Contrato da API futura

A API será criada no `API-01` e terá seu OpenAPI versionado no `API-04`. O
contrato deverá, no mínimo, permitir leitura da Silver pelo futuro front-end e
promoção explícita para Gold. A interface, autenticação de pessoas e publicação
real no Trinix ficam fora deste MVP.

## 6. Contrato Trinix

A arquitetura definitiva prevê escrita direta no banco do Trinix com TLS e
segredo em Vault ou Docker secrets. Até que sejam entregues host, DDL,
permissões mínimas e ambiente de homologação, o sistema terá apenas uma porta
com adaptador mock. O mock não pode registrar publicação como concluída.

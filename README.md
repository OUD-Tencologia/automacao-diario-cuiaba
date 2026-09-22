# Automação Editorial — MVP

MVP para capturar conteúdo licenciado da Folhapress, preservar o TXT original
no MinIO e organizar as notícias nas camadas físicas Bronze, Silver e Gold no
PostgreSQL.

O repositório segue a arquitetura aprovada em
`1.Arquitetura de Design System/Arquitetura Central Editorial.html` e o plano
operacional em `docs/PLANO_EXECUCAO_MVP.md`.

## Estado atual

O projeto está na Sprint 1. Nesta fase são definidos os contratos, a estrutura
do repositório e a PoC de acesso à Folhapress. Não há ainda captura automática,
API, banco ou ambiente de homologação implantado.

## Arquitetura do MVP

```text
n8n (cron de hora em hora)
  -> scraper Folhapress (Python + Playwright)
  -> Automation API (FastAPI)
  -> MinIO (TXT original)
  -> PostgreSQL: Bronze -> Silver -> Gold
  -> porta do Trinix (mock até acesso e DDL serem fornecidos)
```

O n8n apenas orquestra. Todas as regras de negócio, deduplicação,
idempotência, persistência e auditoria pertencem à Automation API.

## Documentação de referência

- `docs/PLANO_EXECUCAO_MVP.md`: cronograma aprovado, sprints, testes e gates.
- `docs/CONTRATOS_MVP.md`: regras e contratos que orientam a implementação.
- `docs/DECISOES_DE_ARQUITETURA.md`: decisões técnicas vigentes e pendências.
- `output/backlog/Backlog_Automacao_Editorial.csv`: backlog aprovado.

## Configuração local

1. Copie `.env.example` para `.env`.
2. Preencha somente as variáveis necessárias para a etapa que será executada.
3. Nunca versione `.env`, cookies, tokens, credenciais ou TXT licenciado.

Os serviços em Docker Compose serão incluídos na tarefa `INF-01`. A API e suas
dependências serão incluídas a partir da tarefa `API-01`, conforme o backlog.

## Convenções de trabalho

- Branches: `feat/<ID-do-backlog>`, por exemplo `feat/PLN-01`.
- Commits: Conventional Commits, por exemplo `docs(PLN-01): registra contratos do mvp`.
- O encerramento de cada sprint exige testes aplicáveis, revisão de segredos e
  uma tag (`sprint-01` a `sprint-05`).
- Mudanças em contratos, schema, OpenAPI ou workflows exigem documentação e
  testes compatíveis na mesma entrega.

## Limites desta fase

Front-end, autenticação de pessoas, imagens, Estadão, produção, domínio/DNS e
integração real com Trinix não fazem parte do MVP atual. A integração Trinix
só poderá escrever no destino após disponibilização de acesso, DDL, permissões
e ambiente de homologação.

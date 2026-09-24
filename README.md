# Automação Editorial - Diário Cuiabá

MVP de captura de conteúdo licenciado da Folhapress. A automação preserva o
TXT original no MinIO e prepara a única tabela editorial Gold no PostgreSQL.

## Arquitetura do MVP

```text
n8n (cron horário)
  -> Automation API privada
  -> Folhapress: login, catálogo, metadados e TXT
  -> MinIO: bronze-raw, original imutável
  -> PostgreSQL: gold.articles
  -> resumo local sugerido / CRUD editorial interno
  -> porta Trinix desabilitada
```

Não fazem parte deste corte: Bronze/Silver no PostgreSQL, front-end, Radar,
Estadão, autenticação de pessoas, produção e integração real com Trinix.

## Estado atual

- Sprint 0 concluída: PoC Folhapress e serviços VPS validados.
- Sprint 1 concluída: migration Gold única, repositório idempotente, guardas
  contra exclusão física e armazenamento bruto com hash.
- Sprint 2 concluída: captura Folhapress modular e idempotente. O teste externo
  automatizado ficou pendente porque a origem resetou conexão antes do login.
- Sprint 3 concluída: resumo Sumy LSA de até 150 caracteres, CRUD editorial,
  descarte lógico e adaptador Trinix desabilitado.
- A API local conversa com PostgreSQL e MinIO existentes na VPS; não há uma
  segunda pilha local desses serviços.

## Documentação

- `docs/PLANO_EXECUCAO_MVP_ENXUTO.md`: sprints, tarefas, aceite e commits.
- `docs/REPLANEJAMENTO_MVP_ENXUTO.md`: decisões de escopo e arquitetura.
- `docs/AUTOMATION_API.md`: health checks, captura e contrato CRUD.
- `infra/migrations/README.md`: aplicação segura da migration Gold.

## Execução local

1. Copie `.env.example` para `.env` e preencha as credenciais locais.
2. Instale o projeto: `\.venv\Scripts\python.exe -m pip install -e .`
3. Prepare os recursos locais: `\.venv\Scripts\python.exe -m playwright install chromium` e `\.venv\Scripts\python.exe -m nltk.downloader punkt_tab`
4. Inicie a API: `\.venv\Scripts\python.exe -m uvicorn automation_api.main:app --host 127.0.0.1 --port 8000`
5. Rode os testes: `powershell -ExecutionPolicy Bypass -File scripts/test_automation_api.ps1`

Nunca versione `.env`, cookies, tokens, credenciais ou TXT licenciado.

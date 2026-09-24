# Runbook de homologação — MVP editorial

Este runbook cobre somente a Automation API, ligada aos containers já
existentes de PostgreSQL, MinIO e n8n. Não use `docker compose up` na raiz do
repositório nem crie uma segunda cópia desses serviços.

## Estado e limites

- O Compose da API não publica portas no host; a porta 8000 fica acessível
  apenas pela rede Docker existente `automacao-editorial_interna`.
- O workflow `workflows/n8n/folhapress-hourly-mvp.json` deve ser importado
  inativo. O n8n chama a API; não recebe credenciais de PostgreSQL/MinIO.
- O primeiro ciclo fica limitado a uma página (`FOLHAPRESS_MAX_PAGES_PER_CYCLE=1`).
- A migration permitida é exclusivamente `002_mvp_single_gold_schema.sql`.
  Nunca aplique `001_initial_editorial_schema.sql` nem o script antigo de
  criação de buckets Bronze/Silver/Gold.
- A captura real permanece bloqueada até o acesso SSH, estado da rede e
  precondições do banco serem verificados na VPS.

## 1. Pré-verificações na VPS

Antes de qualquer alteração, confirmar por SSH:

1. Os containers existentes `automacao-editorial-postgres-1`,
   `automacao-editorial-minio-1` e `automacao-editorial-n8n-1` estão saudáveis.
2. A rede externa `automacao-editorial_interna` existe e conecta os três
   containers.
3. A API conectada a essa rede consegue resolver os nomes dos containers e
   fazer HTTPS de saída para a Folhapress. Se a rede for `internal: true` e
   bloquear saída, interromper: aprovar uma rede com saída antes de conectar a
   API. Não expor a porta 8000 publicamente para contornar isso.
4. O bucket `bronze-raw` já existe e está acessível com a credencial prevista.
5. O banco e as tabelas/schemas existentes foram inspecionados sem ler ou
   imprimir conteúdo editorial. Não prossiga se houver tabelas/dados
   inesperados ou se o destino estiver incerto.

O SSH deve usar uma chave já configurada e `BatchMode=yes`; não gravar senha de
SSH em arquivos ou comandos. Em caso de timeout, não tente endereços alternativos
nem execute DDL: registre a indisponibilidade e aguarde a rede/VPS voltar.

## 2. Preparar a configuração da API

Na cópia do repositório na VPS, crie o arquivo privado a partir do modelo e
restrinja suas permissões:

```sh
cp infra/compose/automation-api.env.template infra/compose/automation-api.env
chmod 600 infra/compose/automation-api.env
```

Preencha os campos de PostgreSQL, MinIO e Folhapress com credenciais já
autorizadas. Não inclua valores em comandos, tickets ou logs. O arquivo
`automation-api.env` é ignorado pelo Git. Preserve o limite de uma página para
o primeiro piloto.

Confira que a imagem e o Compose são válidos, sem iniciar container:

```sh
docker compose -f infra/compose/automation-api.compose.yml config --quiet
docker compose -f infra/compose/automation-api.compose.yml build automation-api
```

O Compose adiciona apenas `automation-api`; não contém serviços para PostgreSQL,
MinIO ou n8n. Não deve haver `ports:` nem mapeamento para a interface pública.

## 3. Backup e preflight da migration

Antes de qualquer DDL, faça e confira um backup lógico do banco de homologação,
armazenado fora do repositório e com acesso restrito. O operador deve usar o
procedimento aprovado para a instalação corrente de PostgreSQL e confirmar que
o arquivo gerado não está vazio e pode ser lido por `pg_restore --list`.

Inspecione apenas o catálogo e contagens agregadas. `002` aborta se encontrar
linhas nas estruturas legadas conhecidas; isso é uma proteção adicional, não
substitui a inspeção/backup. Se houver esquema/tabela/dado inesperado, pare e
peça revisão antes de executar a migration. Não apague tabelas manualmente.

Com a conexão ao PostgreSQL de homologação confirmada, rode também a suíte e a
validação isolada da transição. O modo de integração cria e remove o banco
temporário `automacao_editorial_sprint1_validation`; confirme que esse nome
está livre antes de executar:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/test_automation_api.ps1 -Integration
```

Aplicação autorizada, somente após os gates anteriores:

```sh
docker exec -i automacao-editorial-postgres-1 \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' \
  < infra/migrations/002_mvp_single_gold_schema.sql
```

O comando retorna erro e aborta a transação se as estruturas existentes não
forem seguras para a transição. Não use `--force`, não aplique o rollback como
teste na homologação e não aplique `001`.

## 4. Implantar somente a API

Depois do preflight/migration aprovados:

```sh
docker compose -f infra/compose/automation-api.compose.yml up -d --build automation-api
docker compose -f infra/compose/automation-api.compose.yml ps
docker compose -f infra/compose/automation-api.compose.yml logs --tail=100 automation-api
```

Confirme que o healthcheck do container está `healthy`, que
`GET /health/ready` retorna `ready` ao ser consultado da rede e que os logs não
contêm credenciais, cookies ou corpo de matérias. O endpoint editorial não
deve ficar publicado na Internet.

## 5. Importar e executar manualmente

1. Importe `workflows/n8n/folhapress-hourly-mvp.json` no n8n.
2. Confira URL `http://automation-api:8000/automation/folhapress/capture`,
   timeout de 900 s, uma repetição após 60 s e a saída de erro.
3. Mantenha o workflow inativo; execute apenas pelo gatilho manual.
4. Confirme no resultado do n8n as contagens `scanned`, `captured` e
   `skipped_existing`. Não copie título/corpo de notícia para evidências.
5. Valide contagens e integridade por consultas agregadas: a linha nova deve
   estar em `gold.articles`, começar em `FILA_EDITORIAL`, apontar para
   `bronze-raw` e possuir tamanho/hash registrados. O próprio upload verifica
   o objeto no MinIO antes de inserir a linha.
6. Rode o ciclo manual mais uma vez. A contagem da tabela não deve crescer para
   os mesmos IDs; as matérias existentes devem ser contabilizadas como
   ignoradas. Edite uma notícia de teste apenas se necessário e confirme que a
   recaptura não sobrescreve a edição nem o TXT.

Se houver falha de acesso à origem, erro de schema, objeto ausente ou qualquer
resultado inesperado, mantenha o workflow inativo e não repita em loop. Corrija
primeiro a causa e preserve o erro sanitizado do n8n/API.

## 6. Reinício, idempotência e ativação

Valide reinício somente da API e sua recuperação para `healthy`. Execute de novo
o ciclo manual e confirme idempotência. PostgreSQL, MinIO e n8n não devem ser
reiniciados como parte dessa tarefa.

Ative o agendamento horário no n8n apenas após todos os passos manuais passarem
e após aprovação operacional. O cron é `0 * * * *` em `America/Sao_Paulo`.
Mantenha o limite inicial de uma página; amplie-o de forma deliberada se a
observação de volume mostrar que uma página não cobre o intervalo entre ciclos.

## 7. Operação e recuperação

- Reiniciar apenas a API:

  ```sh
  docker compose -f infra/compose/automation-api.compose.yml restart automation-api
  ```

- Reprocessar: executar manualmente no n8n. A API deduplica por `SOURCE + ID`;
  não apagar a linha nem o TXT para forçar nova captura.
- Falha de banco/MinIO/origem: conferir healthcheck e logs sanitizados, corrigir
  a dependência e reexecutar uma vez manualmente.
- Um TXT já guardado continua sendo o original imutável. Edições ocorrem apenas
  nos campos editoriais de `gold.articles`.
- Não marcar `PUBLICADO` pela automação; isso depende de confirmação humana no
  Trinix, que permanece fora deste MVP.

## Gate de aceite da Sprint 4

- [ ] SSH/VPS acessíveis; containers e rede verificados.
- [ ] Saída HTTPS da rede confirmada ou rede de egress formalmente aprovada.
- [ ] Backup lógico válido e estado do banco revisado.
- [ ] Migration `002` aplicada sem atingir dados inesperados.
- [ ] API saudável e conectada à rede existente, sem porta pública.
- [ ] Workflow importado inativo e ciclo manual controlado aprovado.
- [ ] Reexecução idempotente após reinício da API.
- [ ] Ativação horária aprovada e runbook atualizado.

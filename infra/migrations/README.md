# Migrations do PostgreSQL

`001_initial_editorial_schema.sql` cria as tabelas físicas das camadas
operacional, Bronze, Silver e Gold. A migration implementa:

- deduplicação de Bronze por `source + source_id`;
- JSONB para metadados flexíveis sem substituir os campos relacionais;
- rastreio de objetos MinIO e falhas parciais para reconciliação;
- bloqueio de Bronze e Gold contra alteração ou remoção;
- promoção para Gold somente com `author_name` preenchido;
- índices para busca editorial, auditoria e reprocessamento.

## Aplicação

A migration ainda não deve ser aplicada manualmente na VPS. Ela será executada
em um banco descartável de validação antes do banco de homologação receber DDL.
O executor versionado será incluído junto com a Automation API, para que o
mesmo processo seja usado localmente e na VPS.

`001_initial_editorial_schema.down.sql` é destrutiva e serve apenas para o
banco descartável de teste. Nunca a execute em ambiente com dados aceitos.

## Validação de integração

Depois de aplicar a migration em um banco vazio e descartável, execute
`tests/integration/initial_schema_invariants.sql`. Ele valida a criação das
camadas físicas e as regras críticas de integridade e imutabilidade, usando
apenas dados sintéticos.

Com o SSH por chave configurado e as variáveis `VPS_HOMOLOGATION_*` preenchidas
no `.env` local, a validação descartável pode ser repetida com:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/validate_dat01_remote.ps1
```

O script cria um banco temporário com nome único, aplica a migration e o teste
de invariantes e o remove ao finalizar. Ele não aplica DDL no banco de
homologação da aplicação e não lê nem exibe senhas.

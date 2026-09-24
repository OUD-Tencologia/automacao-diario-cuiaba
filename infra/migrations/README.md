# Migrations do MVP enxuto

`001_initial_editorial_schema.sql` preserva o modelo histórico Bronze/Silver/
Gold e não deve ser aplicado na homologação deste MVP.

`002_mvp_single_gold_schema.sql` é a migration aplicável. Ela cria somente
`gold.articles`. Caso encontre tabelas legadas com dados, aborta sem remover
nenhuma linha.

Antes de aplicar na VPS:

1. Faça um backup lógico do banco.
2. Execute `python scripts/validate_single_gold_migration.py` para validar a
   transição em banco temporário.
3. Confirme que não existem dados no modelo legado.
4. Aplique exclusivamente `002_mvp_single_gold_schema.sql` na homologação.

O script de validação cria e remove o banco temporário
`automacao_editorial_sprint1_validation`; ele não aplica schema na base de
homologação da aplicação.

# Correção da captura Folhapress

## Motivo

O TXT da Folhapress é o original da matéria e, no formato observado, não traz
obrigatoriamente os rótulos `TITULO`, `AUTOR` e `DATA/HORA`. O MVP anterior
aceitava metadados genéricos da página (`Folhapress`), causando registros
editoriais inválidos.

## Regras vigentes

- `ds_noticia` vem sempre do TXT original. Se o TXT possuir `DESCRICAO`, somente
  essa seção é usada; caso contrário, o TXT inteiro normalizado é usado.
- `source_url` é a URL canônica `/texto/{id}` e precisa corresponder ao ID.
- Título genérico do portal, data ausente ou corpo vazio impedem a gravação.
- O chapéu é extraído do prefixo visível no catálogo: em
  `BRASIL-ONU: Brasil se retira...`, `ds_chapeu=BRASIL-ONU` e
  `ds_titulo=Brasil se retira...`. Esse título tem precedência sobre o título
  técnico da página; um `TITULO:` explícito no TXT continua tendo precedência.
- O local contém somente a localidade da abertura do texto, por exemplo
  `Brasília, DF`; a aplicação não grava mais `Da FolhaPress - ...`.
- Chapéu, autor e local só ficam nulos quando a fonte não os disponibilizar.
- O resumo é opcional e é calculado apenas depois da validação do corpo.
- O MinIO continua sendo somente `bronze-raw`; a tabela editorial única é
  `gold.articles`.

## Reconciliar registros antigos

O reparo não é um endpoint HTTP nem um workflow n8n. Execute somente dentro do
container da API após implantar a versão que contém esta correção:

```sh
docker compose -f infra/compose/automation-api.compose.yml exec automation-api \
  python -m automation_api.cli.reconcile_folhapress --limit 100
```

O comando seleciona itens Folhapress em `FILA_EDITORIAL` cuja versão de contrato
seja anterior à vigente. Ele relê o TXT já existente no MinIO, valida o SHA-256,
consulta novamente o catálogo (para recuperar chapéu/título) e a página da
matéria e atualiza a mesma linha. Se uma matéria não estiver mais no catálogo,
ela é reportada como `catalog_reference_missing` e não é alterada. O comando não
remove objetos, não cria duplicatas e não sobrescreve itens que saíram da fila.

Uma saída JSON contém somente contagens, IDs e códigos sanitizados. Não copie
texto de notícia, cookies ou credenciais para logs e tickets.

## Normalizar locais de registros já existentes

Quando o catálogo histórico não disponibilizar mais uma matéria, ainda é
possível corrigir o local de forma verificável pelo TXT já armazenado, sem
navegar na Folhapress e sem alterar título, chapéu, autor, corpo ou resumo:

```sh
docker compose -f infra/compose/automation-api.compose.yml exec automation-api \
  python -m automation_api.cli.normalize_folhapress_locations --limit 100
```

O resultado transforma, por exemplo, `BRASÍLIA, DF (FOLHAPRESS) - ...` em
`Brasília, DF`. Um chapéu ausente continua pendente de catálogo/exportação
histórica confiável; ele nunca é inferido a partir do local ou do título.

## Operação segura

1. Mantenha o cron n8n inativo.
2. Faça uma captura manual e valide título, data, `source_url`, corpo, objeto
   MinIO e resumo no PostgreSQL.
3. Execute a reconciliação uma vez e confira suas contagens.
4. Execute novamente a captura manual para confirmar idempotência.
5. Só então obtenha aceite para ativar o cron horário.

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
o chapéu permanece pendente, mas a API ainda tenta recuperar título, data e
autor da própria página. Uma página que retornar somente o título genérico do
portal é rejeitada e a linha fica intacta. O comando não remove objetos, não
cria duplicatas e não sobrescreve itens que saíram da fila.

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

## Checkpoint de homologação — 24/09/2026

Após a aplicação controlada dos comandos acima, a tabela de homologação ficou
com 64 registros Folhapress, todos com `ds_local`, `source_url` canônico e
referência verificável ao TXT no MinIO. Foram normalizados 64 locais e 61
registros passaram ao contrato de extração 3; 49 possuem chapéu recuperado do
catálogo. Três itens históricos (`2600694`, `2600695` e `2600696`) continuam
com título genérico porque tanto o catálogo histórico quanto suas páginas não
ofereceram um título específico. Eles foram preservados sem inferência e devem
ser corrigidos somente se a Folhapress fornecer uma fonte histórica confiável.

### Validação ponta a ponta — 25/09/2026

Foi executado um ciclo controlado pela mesma rota interna usada pelo n8n
(`POST /automation/folhapress/capture`). O ciclo `efceb359bec1436991c612db7f5fc9a8`
concluiu em 704.353 ms com `scanned=22`, `captured=22`,
`skipped_existing=0` e `failed=0`. Houve duas instabilidades transitórias da
Folhapress (um `connection_reset` e um timeout de navegação); ambas foram
recuperadas automaticamente pela nova sessão e retry, sem perda de item.

Após o ciclo, a conferência cruzada registrou 86 notícias Folhapress na tabela
`gold.articles` e 86 objetos TXT sob o prefixo `folhapress/` no bucket MinIO.
Todos os 86 têm título, local, URL de origem e chave MinIO preenchidos. Desses,
83 estão no contrato de extração 3 — os três restantes são os itens históricos
sem título confiável já documentados acima. O agendamento horário do n8n não
foi alterado por esta validação.

## Operação segura

1. Mantenha o cron n8n inativo.
2. Faça uma captura manual e valide título, data, `source_url`, corpo, objeto
   MinIO e resumo no PostgreSQL.
3. Execute a reconciliação uma vez e confira suas contagens.
4. Execute novamente a captura manual para confirmar idempotência.
5. Só então obtenha aceite para ativar o cron horário.

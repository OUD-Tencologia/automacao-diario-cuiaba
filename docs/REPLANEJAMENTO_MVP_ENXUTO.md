# Replanejamento do MVP - Automação Editorial Enxuta

**Status:** diretriz técnica para substituir o pipeline Bronze/Silver/Gold
antes da próxima implementação funcional.

O plano operacional em sprints, tarefas, testes e critérios de aceite está em
[`PLANO_EXECUCAO_MVP_ENXUTO.md`](PLANO_EXECUCAO_MVP_ENXUTO.md).

## Objetivo

Entregar rapidamente a ingestão horária de notícias licenciadas da Folhapress,
com preservação do TXT original no MinIO, persistência em uma única tabela
editorial Gold e dados prontos para o Admin do Diário. A Automation API é
privada: o n8n é seu único chamador de automação.

## Fluxo alvo

```text
n8n (cron de uma hora)
  -> Automation API privada
      -> saúde da fonte
      -> autenticação Folhapress
      -> listagem, filtros e paginação
      -> extração de metadados e download do TXT
      -> MinIO / bronze-raw (original imutável)
      -> PostgreSQL / gold.articles (registro editorial único)
      -> resumo editorial sugerido
      -> item disponível ao Admin
      -> PublisherPort do Trinix (desabilitado até haver acesso)
```

O n8n agenda, chama o ciclo e trata retry. Regra de negócio, deduplicação,
armazenamento e geração de resumo pertencem à API.

## Módulos da Automation API

| Módulo | Responsabilidade |
|---|---|
| `source_health` | Verificar alcance e resposta esperada da Folhapress. |
| `folhapress_auth` | Login, sessão e expiração da sessão. |
| `folhapress_catalog` | Filtros, paginação e identificação de itens novos. |
| `article_extractor` | Extrair campos editoriais e metadados da matéria. |
| `txt_downloader` | Baixar e validar o TXT da sessão autenticada. |
| `raw_storage` | Gravar o original no bucket `bronze-raw`, com hash e chave sem sobrescrita. |
| `gold_news_repository` | Deduplicar por `source + id` e persistir a tabela Gold. |
| `editorial_summary` | Gerar sugestão local de resumo. |
| `publisher_port` | Isolar futura publicação no Trinix; inicia desabilitado. |

## Dados editoriais

`ID` é o identificador da matéria na URL da fonte. A unicidade é dada por
`SOURCE + ID`, para permitir outras fontes no futuro sem colisão.

| Campo | Regra inicial |
|---|---|
| `DT_NOTICIA` | Data e hora da notícia em `America/Sao_Paulo`. |
| `DS_CHAPEU` | Etiqueta editorial completa da fonte; não derivar somente o primeiro nome. |
| `DS_TITULO`, `NM_AUTOR`, `DS_LOCAL` | Metadados extraídos e normalizados para apresentação. |
| `DS_NOTICIA` | Corpo de trabalho, inicialmente igual ao texto capturado e editável pelo Admin. |
| `DS_RESUMO` | Sugestão opcional ao editor; começa nulo se a geração falhar. |
| `DESTAQUE` | Booleano. |
| `TIPO_DE_CONTEUDO` | `PUBLICO` ou `INTERNO`. |
| `PUBLICAR_IMEDIATAMENTE` | Instrução editorial, nunca publicação automática. |
| `STATUS` | Estado editorial; `PUBLICADO` só ocorre após integração real e ação humana no Trinix. |

O MinIO conserva o TXT baixado como contraprova imutável. A edição de
`DS_NOTICIA` não altera esse arquivo.

## Resumo editorial local - SUM-01

O resumo passa a fazer parte deste MVP, sem chamada a modelo externo.

1. A implementação inicial usa `sumy` com tokenizer em português e
   sumarização extrativa LSA.
2. A entrada é `DS_NOTICIA`; a saída é uma sugestão em `DS_RESUMO` com no
   máximo 150 caracteres, incluindo espaços.
3. A composição deve selecionar frases completas prioritariamente; não deve
   cortar palavras apenas para cumprir o limite.
4. Erro ou ausência de texto não bloqueiam a captura: o item é salvo com
   `DS_RESUMO` nulo e falha registrada em log.
5. O editor pode editar ou ignorar a sugestão. O resumo não causa aprovação,
   publicação ou alteração do TXT original.
6. Testes obrigatórios: limite de 150 caracteres, texto vazio, caracteres
   acentuados, falha controlada do sumarizador e preservação do original.

`transformers`, `torch` e `sentencepiece` não entram neste corte. São mais
pesados, exigem download/cache de modelo e o exemplo de `mT5-small` não
garante qualidade de sumarização jornalística em português. Uma futura troca
para modelo generativo local depende de avaliação editorial com amostras reais.

## Persistência e infraestrutura

- MinIO: somente o bucket `bronze-raw` é usado pelo MVP. Os buckets antigos
  não devem ser apagados neste momento.
- PostgreSQL: haverá uma única tabela editorial Gold. A migration antiga não
  deve ser aplicada à homologação; a substituição precisa ser versionada e
  impedir execução caso encontre dados no modelo anterior.
- MinIO: a chave do objeto deve incluir fonte, `ID` e hash, evitando
  sobrescrever uma revisão posterior da origem.
- Health check MinIO deve testar acesso ao bucket `bronze-raw`, não depender
  de listagem global de todos os buckets.

## Limites explícitos

- Não há front-end neste escopo.
- O navegador não acessa PostgreSQL diretamente. O futuro Admin deve consumir
  uma interface de leitura/edição protegida, separada do endpoint privado de
  ingestão do n8n.
- Não há publicação automática ou integração real com Trinix.
- Radar de concorrentes não é implementado neste corte. Apenas a abstração de
  fontes permanece preparada; a coleta depende de lista autorizada e regra
  jurídica, e não deve armazenar íntegra de conteúdo de concorrentes.

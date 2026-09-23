# Evidências da PoC Folhapress

**Tarefa do backlog:** `SRC-01`  
**Data da validação manual:** 23/09/2026  
**Status:** concluída

## Resultado

O acesso autenticado foi validado manualmente pelo responsável do projeto. Não
houve solicitação de CAPTCHA ou MFA no fluxo observado.

## Rotas confirmadas

| Finalidade | Rota |
|---|---|
| Base e entrada de login | `https://folhapress.folha.com.br/` |
| Lista de textos | `https://folhapress.folha.com.br/textos` |
| Detalhe da matéria | `https://folhapress.folha.com.br/texto/{source_id}` |
| Download do TXT | `https://folhapress.folha.com.br/texto/{source_id}/baixar` |

## Comportamentos confirmados

- A aba `TEXTOS` está disponível após a autenticação.
- O grupo `Serviço Noticioso` contém os filtros: Todos, Celebridades, Cotidiano,
  Cultura, Economia, Esporte, Exterior, Notícias e Política.
- `Exterior` permanece excluído pela regra vigente do MVP. Cultura e Notícias
  continuam configuráveis, aguardando decisão editorial; a disponibilidade no
  portal não equivale a autorização de coleta.
- A lista exibe 24 itens por página; a navegação mostra páginas sequenciais e
  existe um limite de 1.000 resultados exibidos para a busca observada.
- A matéria possui código numérico, usado como `source_id`.
- O detalhe expõe data do conteúdo, data/hora de inclusão, serviço/categoria,
  aviso editorial, título, autor/assinatura e texto.
- O TXT de uma matéria foi baixado e aberto com sucesso.
- O portal informa que determinado conteúdo só pode ser publicado com
  assinatura; a regra já existente de impedir promoção a Gold/publicado sem
  autor/assinatura permanece válida.

## Consequências para a implementação

1. A autenticação automática deve ser testada no scraper, mas não há requisito
   de resolver CAPTCHA ou MFA no cenário atualmente validado.
2. O adapter usará `source + source_id` para deduplicação e a rota de download
   confirmada para obter o TXT.
3. O filtro de origem continuará configurável; nenhuma categoria adicional será
   incluída sem decisão editorial.
4. Capturas reais, cookies e TXT licenciados continuam fora do Git.

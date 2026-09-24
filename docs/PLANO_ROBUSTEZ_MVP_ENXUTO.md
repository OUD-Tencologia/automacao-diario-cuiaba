# Plano de robustez do MVP enxuto

**Situação:** R1 concluída e R2 implementada localmente; validação controlada
na homologação pendente. Não altera o escopo funcional do MVP.  
**Base:** código e homologação inspecionados em 24/09/2026.

## 1. Objetivo e limite

O MVP continua exatamente com a arquitetura reduzida:

```text
n8n (cron horário, inativo)
  -> Automation API privada
      -> Folhapress (login, catálogo, matéria e TXT)
      -> MinIO / bronze-raw (TXT original)
      -> PostgreSQL / gold.articles (única tabela editorial)
      -> resumo LSA e CRUD interno
```

Este plano melhora a **confiabilidade das funções já existentes**. Não cria
Bronze/Silver no PostgreSQL, não muda a Gold única, não cria front-end, não
inclui Estadão, Trinix real, produção, domínio ou autenticação de usuários.

Também não muda a regra editorial: a notícia entra em `FILA_EDITORIAL`, o TXT
original é imutável no MinIO e a deduplicação continua sendo `source + id`.

## 2. Evidências e diagnóstico atual

### O que já funciona e deve ser preservado

- A API está implantada sem publicar a porta no host e responde `ready` pela
  rede Docker do n8n.
- A captura real já comprovou login, catálogo, extração, TXT, MinIO, Gold,
  resumo e deduplicação em execuções anteriores.
- A tabela `gold.articles` e o bucket `bronze-raw` são os únicos destinos do
  MVP. O upload verifica hash e tamanho antes de gravar a linha.
- O workflow importado usa chamada privada, timeout de 15 minutos, uma
  retentativa após 60 segundos e continua inativo.
- Durante a execução manual mais recente havia 39 linhas na Gold, 37 com
  resumo. Isso confirma persistência parcial válida, mas não constitui aceite
  do ciclo porque houve ao menos uma falha de download automatizado.

### Causa conhecida da execução em andamento

O download manual de uma matéria que falhou na automação funcionou. Portanto,
o link e a permissão humana na Folhapress estavam válidos. A falha está no
percurso automatizado com Chromium/Playwright. Hoje ela é registrada apenas
como `FolhapressDownloadError`; o código seguro específico é descartado pelo
orquestrador. Não é possível distinguir, a partir do log atual, entre timeout,
evento de download cancelado, arquivo temporário ausente, HTML devolvido ou
expiração de sessão.

### Fragilidades priorizadas

| Prioridade | Ponto | Efeito atual | Melhoria preservando o MVP |
|---|---|---|---|
| Crítica | Diagnóstico de item falho é perdido | Não há causa suficiente para corrigir o download sem tentativa e erro | Propagar etapa e código sanitizado por ID; nunca registrar credenciais, cookie, título ou corpo |
| Crítica | Retry acontece no ciclo inteiro | Um TXT pontualmente instável faz o n8n repetir login e catálogo; o node fica aguardando por minutos | Repetir somente o item falho com sessão nova e limite pequeno; manter retry global apenas como última proteção |
| Crítica | Não há trava de execução | Clique manual e cron futuro podem rodar juntos e duplicar trabalho/consumir a Folhapress | Lock transacional/advisory no PostgreSQL, sem criar tabela nova |
| Alta | Resposta só chega no fim do ciclo | O n8n aparenta estar travado, embora a API esteja trabalhando | Registrar início/fim/duração/contagens/correlação e devolver resultado estruturado ao término |
| Alta | Uma página pode não cobrir uma hora de volume | Se a Folhapress listar mais itens novos que a primeira página, os mais antigos podem nunca ser descobertos | Definir janela de páginas inicial, alerta quando o limite é atingido e procedimento de backfill controlado |
| Alta | Parser e seletores dependem de HTML externo | Pequena mudança de layout pode gerar campos vazios, links errados ou login em campo incorreto | Validadores explícitos, seletores configuráveis e fixtures sintéticas representativas |
| Média | MinIO e Gold não formam uma transação única | Falha após upload pode deixar TXT órfão; falha antes do insert não deixa notícia visível | Marcar e conciliar objetos órfãos por chave determinística, sem apagar automaticamente conteúdo editorial |
| Média | Sem testes reais controlados de regressão operacional | Testes locais não reproduzem completamente o comportamento do container e da fonte | Smoke test controlado, sem persistência, e checklist de homologação com dados agregados |
| Média | Imagem e dependências não são totalmente reprodutíveis | Uma nova build pode mudar Chromium/Python/dependências sem mudança de código | Fixar versões/constraints e identificar versão da imagem implantada |
| Média | CRUD não possui proteção de concorrência | Dois futuros editores podem sobrescrever alterações entre si | Usar `update_at` como controle otimista no contrato interno, sem criar front-end |
| Baixa | Resumo pode ficar nulo para textos cuja primeira frase excede 150 caracteres | A captura continua, mas o editor fica sem sugestão | Registrar motivo e definir fallback seguro que não corta palavras, mantendo o limite de 150 |

### Pontos que **não** são defeitos a corrigir neste plano

- O endpoint não tem autenticação de usuário: é decisão temporária aceita para
  uma API sem porta pública e restrita à rede Docker. Não expor a API para
  compensar essa decisão.
- `JSONB` é uma coluna da Gold para metadados técnicos; não é outro banco nem
  implica novas camadas.
- O cron estar inativo é a condição correta até o aceite manual completo.
- A ausência de integração real com Trinix e front-end é escopo futuro.

## 3. Resultado esperado

Após estas sprints, uma execução manual deve permitir responder, sem ver
conteúdo licenciado, a estas perguntas:

1. O ciclo começou quando, com qual versão da API e qual ID de correlação?
2. Quantas referências foram encontradas, ignoradas, persistidas e falharam?
3. Para cada falha, em qual etapa ocorreu e qual código técnico sanitizado a
   descreve?
4. A API ainda está trabalhando, já finalizou ou foi bloqueada por outra
   execução?
5. O TXT e a linha gravada possuem chave, tamanho e hash coerentes?

O objetivo operacional não é transformar uma captura de fonte externa em algo
instantâneo. É tornar uma execução de alguns minutos previsível, limitada,
observável e recuperável sem duplicar ou perder dados.

## 4. Sprints e tarefas

Cada sprint termina com testes verdes, revisão de diff, atualização do runbook
e um commit próprio. Nenhuma sprint ativa o cron automaticamente.

### Sprint R1 — Diagnóstico seguro e contrato de execução

**Objetivo:** descobrir a causa real de cada falha e tornar o estado de uma
execução compreensível no n8n e nos logs.

**Estado:** concluída no código e em testes locais. A API agora gera
`capture_id`, mede duração, devolve contagens e retorna, em falha parcial,
etapa/código sanitizado por matéria.

1. Criar um `capture_id` por chamada da API e incluí-lo em todos os logs do
   ciclo, sem usar ID de usuário, cookie ou conteúdo editorial.
2. Criar um modelo interno de falha por item: `source_id`, `stage`,
   `diagnostic_code`, `retryable` e duração. Os únicos valores permitidos de
   etapa são, por exemplo, `source_health`, `login`, `catalog`, `article`,
   `download`, `minio`, `database` e `summary`.
3. Preservar os códigos existentes do downloader (`download_failed`,
   `temporary_file_missing`, `empty_body`, `html_response`, `download_timeout`,
   `session_expired` etc.) e registrar o `diagnostic_code` em vez do nome
   genérico da exceção.
4. Fazer `CaptureCycleError` carregar um resumo sanitizado de contagens e
   falhas. A resposta HTTP para o n8n deve continuar sem texto/licença/segredo.
5. Definir resposta de ciclo concluído com contagens de `scanned`, `captured`,
   `skipped_existing`, `failed` e duração. Definir resposta de falha parcial
   compatível com o tratamento de erro do n8n.
6. Adicionar logs estruturados de início, fim e duração por etapa. Definir
   retenção/rotação de logs no Compose para não esgotar o disco da VPS.
7. Criar testes para cada código de falha, para a ausência de dados sensíveis
   em logs/respostas e para o contrato OpenAPI atualizado.

**Aceite R1:** uma falha reproduzida informa ID, etapa e código sanitizado;
nenhuma evidência contém senha, cookie, URL assinada, título ou corpo; o n8n
exibe se a execução falhou por completo ou parcialmente.

### Sprint R2 — Download e sessão Folhapress resilientes

**Objetivo:** reduzir a falha intermitente do TXT sem fazer repetição cega de
POST de login ou clique de download.

**Estado:** implementação local concluída; falta validar com uma execução
controlada no container de homologação. A primeira tentativa usa a sessão do
ciclo; somente códigos transitórios abrem uma sessão nova limitada para a
matéria que falhou. Respostas HTML, TXT vazio e falhas de contrato não entram
em retry.

1. Usar o diagnóstico da R1 para reproduzir no container da API o cenário de
   falha com uma única matéria, em modo não persistente. Não salvar HTML, TXT,
   screenshot ou trace que contenha conteúdo licenciado.
2. Separar os tempos de `login`, `catálogo`, `matéria` e `download` em
   configurações tipadas, com limites seguros. O timeout total do ciclo deve
   ficar abaixo dos 900 segundos configurados no n8n.
3. Implementar tentativa por item apenas para falhas transitórias classificadas
   como retryable. Cada nova tentativa deve recriar contexto/sessão, refazer
   autenticação e abrir a matéria; não repetir o mesmo clique dentro da mesma
   sessão corrompida.
4. Limitar as tentativas por item e aplicar espera incremental curta. Falhas de
   HTML, texto vazio, campo obrigatório ausente ou permissão negada não devem
   ser repetidas como se fossem rede.
5. Validar antes de persistir: evento de download concluído, arquivo temporário
   acessível, bytes não vazios, resposta não HTML, tamanho máximo configurável
   e hash calculado.
6. Tornar os seletores críticos explicitamente configuráveis e validar que o
   login/catálogo realmente alcançaram os marcadores esperados. Evitar depender
   de seletores amplos quando houver seletor conhecido.
7. Criar fixtures sintéticas para: download cancelado, timeout, login expirado,
   HTML em vez de TXT, arquivo vazio e TXT válido. Ampliar o teste Chromium
   local para cobrir esses casos.

**Aceite R2:** o caso real é classificado por código; uma falha transitória de
download é recuperada por tentativa isolada ou retorna erro claro; uma falha
determinística não gera loop; os testes de navegador e unitários passam.

### Sprint R3 — Controle de ciclo, idempotência e cobertura de catálogo

**Objetivo:** impedir concorrência e garantir que o cron futuro não deixe itens
novos para trás.

**Estado:** controle de concorrência, prazo do ciclo e aviso de limite de
catálogo implementados localmente. A conciliação de objetos MinIO e a validação
em homologação permanecem pendentes.

1. Implementar lock exclusivo de captura da Folhapress usando advisory lock do
   PostgreSQL, com liberação garantida em `finally`. Não criar tabela de runs.
2. Quando o lock estiver ocupado, retornar conflito/retry explícito e fazer o
   n8n encerrar a execução sem iniciar segundo navegador. Documentar o
   comportamento para clique manual durante cron.
3. Definir um orçamento de execução (`deadline`) menor que o timeout do n8n.
   Ao atingir o limite, interromper de forma segura, registrar o ponto e
   devolver resultado/erro recuperável sem gravar item incompleto.
4. Rever a paginação. Começar por uma quantidade aprovada de páginas e criar
   aviso `catalog_limit_reached` quando a última página ainda estiver cheia;
   isso evidencia risco de cobertura sem aumentar a infraestrutura.
5. Criar procedimento de backfill manual: ampliar páginas temporariamente,
   executar uma vez, conferir contagens e voltar ao limite normal. A chave
   composta continua protegendo contra duplicidade.
6. Tratar o intervalo entre upload e insert: registrar métricas de objeto
   guardado/linha criada e criar comando de conciliação **somente de relatório**
   para identificar possíveis objetos órfãos. Não apagar nada automaticamente.
7. Testar concorrência com dois disparos sintéticos, recaptura de mesma matéria,
   falha de banco após upload e catálogo com mais itens que a janela.

**Aceite R3:** nunca há dois ciclos Folhapress simultâneos; recaptura preserva
edições; o risco de paginação truncada é visível; eventual órfão é identificável
sem exclusão automática.

### Sprint R4 — Operação n8n e recuperação controlada

**Objetivo:** fazer o workflow representar corretamente o resultado da API e
dar uma operação simples para homologação.

1. Atualizar o workflow para interpretar o contrato R1: sucesso completo,
   sucesso com pendência recuperável, lock ocupado e falha não recuperável.
2. Manter somente uma retentativa global, porque a R2 já trata retry por item.
   Garantir que o tempo combinado de API, espera e retry caiba na política de
   execução do n8n.
3. Configurar nome/saída dos nodes para mostrar contagens, `capture_id` e código
   sanitizado. Não inserir credenciais de banco, MinIO ou Folhapress no n8n.
4. Registrar procedimento manual de operação: iniciar, acompanhar, verificar
   `/health/ready`, consultar execução n8n, ler logs pelo `capture_id` e validar
   apenas contagens/hash/tamanho no banco e MinIO.
5. Testar no n8n: sucesso idempotente, falha de item recuperada, lock ocupado,
   retry esgotado e parada limpa. O workflow continua `active: false`.
6. Corrigir os avisos de configuração do n8n que afetem a execução JavaScript
   atual, sem instalar runner Python ou adicionar automações novas. Registrar
   os avisos que forem apenas de upgrade futuro.

**Aceite R4:** o node não fica em estado ambíguo; cada execução tem resultado
legível; o retry não cria sobreposição; o cron continua inativo após os testes.

### Sprint R5 — Qualidade de entrega e aceite do MVP melhorado

**Objetivo:** tornar a versão reproduzível e habilitar uma decisão segura sobre
o cron, sem ampliar funcionalidades.

1. Fixar dependências de build da API e versões de navegador/Python por arquivo
   de constraints ou lock revisado. Registrar a versão/imagem implantada em
   evidência de homologação.
2. Adicionar lint/formatação e execução automatizada de testes em pull request.
   A suíte deve conter unitários, contratos de OpenAPI, browser local e
   integração SQL em banco descartável quando explicitamente acionada.
3. Atualizar README, modelo de dados, contrato da API, runbook e plano de
   execução para remover checkpoints obsoletos e refletir a homologação real.
4. Executar um ciclo manual controlado com uma página e registrar somente
   evidências agregadas: contagens, duração, hashes/tamanhos, status inicial e
   ausência de duplicação na segunda execução.
5. Validar CRUD já existente: leitura, edição permitida, descarte lógico,
   bloqueio de `PUBLICADO` sem Trinix e controle otimista por `update_at`.
6. Fazer revisão de segredos/diff/imagem: `.env`, cookies, chaves SSH, TXT e
   conteúdo licenciado não entram no Git nem na documentação.
7. Aplicar gate formal de ativação. Só então, com aprovação humana, ativar o
   cron `0 * * * *` em `America/Sao_Paulo` e observar os primeiros ciclos.

**Aceite R5:** todos os testes acordados passam; duas execuções manuais são
idempotentes; há diagnóstico para falhas; documentação está fiel; cron só é
ativado mediante aprovação explícita.

## 5. Ordem de execução e decisões necessárias

1. Executar R1 antes de tentar novas correções de downloader: hoje falta a
   informação que diferencia uma causa de outra.
2. Executar R2 e aceitar ao menos uma captura de matéria nova sem erro antes de
   alterar páginas ou ativar agendamento.
3. Executar R3 antes de qualquer cron, pois a captura pode durar minutos e um
   disparo manual não deve concorrer com o horário.
4. Executar R4 e R5 em homologação. A VPS atual é homologação; não migrar para
   produção nesta etapa.

As únicas decisões de negócio necessárias antes da R3 são: número inicial de
páginas por ciclo e prazo máximo aceitável para um ciclo. A recomendação técnica
é começar com duas páginas após os testes, medir volume/duração por alguns
ciclos manuais e ajustar com evidência; uma página é segura para piloto, mas
pode não absorver picos acima de 24 referências.

## 6. Critérios finais de pronto

- [ ] Falhas de fonte são classificadas por código e etapa, sem vazamento.
- [ ] Download transitório é retentado de modo isolado e limitado.
- [ ] Execuções concorrentes são bloqueadas.
- [ ] O tempo máximo é menor que o timeout do n8n e o workflow informa o fim.
- [ ] Catálogo, MinIO, Gold, resumo e deduplicação foram validados no ciclo
      completo com evidências agregadas.
- [ ] CRUD preserva original no MinIO, bloqueia publicação sem Trinix e evita
      sobrescrita concorrente.
- [ ] Build, testes e documentação são reproduzíveis e atualizados.
- [ ] O cron permanece inativo até aprovação operacional explícita.

## 7. Riscos que permanecem após as melhorias

- A Folhapress é uma dependência externa com HTML e regras que podem mudar.
  Monitoramento e diagnóstico reduzem o tempo de correção, mas não eliminam
  indisponibilidade externa.
- A fonte pode publicar mais itens que a janela escolhida. O alerta de limite e
  backfill reduzem risco; a escolha de cobertura ainda precisa de observação.
- MinIO e PostgreSQL não possuem transação distribuída. A conciliação detecta
  resíduos; a decisão de remover ou preservar qualquer objeto continua humana.
- A API segue sem autenticação de usuário por decisão de escopo. Sua segurança
  depende de permanecer sem porta pública e em rede confiável.

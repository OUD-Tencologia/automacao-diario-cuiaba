# Decisões de Arquitetura — MVP Editorial

## ADR-001 — Orquestração horária pelo n8n

**Decisão:** o n8n executará um cron `0 * * * *` e chamará a Automation API.

**Consequência:** o workflow não terá regra de negócio nem acesso direto às
tabelas Bronze, Silver ou Gold. Retentativas e reprocessamento serão
rastreáveis por ciclo na API.

## ADR-002 — PostgreSQL com tabelas físicas e JSONB auxiliar

**Decisão:** Bronze, Silver, Gold e dados operacionais existirão como tabelas
físicas do PostgreSQL. `JSONB` será uma coluna de metadados brutos flexíveis,
não um banco separado.

**Consequência:** campos consultados e regras relacionais ficam em colunas
tipadas e indexadas; variações da fonte permanecem preservadas no JSONB.

## ADR-003 — MinIO é a fonte primária do TXT original

**Decisão:** o TXT licenciado será guardado no MinIO/S3, com `object_key`, hash
e momento da captura registrados no PostgreSQL.

**Consequência:** o TXT não será sobrescrito nem terá uma cópia primária em
coluna do banco. Cada gravação Bronze depende de objeto validado.

## ADR-004 — Adapter isolado para Folhapress

**Decisão:** o acesso à Folhapress será implementado em Python com Playwright,
com seletores e filtros configuráveis.

**Consequência:** alterações de layout ficam restritas ao adapter. A PoC da
tarefa `SRC-01` validará login, menu `TEXTOS`, paginação e download antes da
implementação definitiva.

## ADR-005 — Trinix por porta e mock até liberação externa

**Decisão:** a integração real não será antecipada. A porta será preparada para
a escrita direta no banco do Trinix, conforme arquitetura aprovada, mas o
adapter atual será mock.

**Consequência:** nenhuma publicação real será marcada como concluída enquanto
não houver acesso, DDL, permissões e homologação.

## ADR-006 — Exposição pública posterior

**Decisão:** PostgreSQL e MinIO vivem em rede interna Docker. Traefik, DNS e
TLS público só entram após domínio e decisão de infraestrutura.

**Consequência:** a homologação ocorrerá na VPS definida, sem antecipar
produção ou expor serviços de dados.

## ADR-007 — Desenvolvimento local com serviços existentes na VPS

**Decisão:** PostgreSQL, MinIO e n8n já existentes na VPS de homologação serão
reutilizados. A Automation API será desenvolvida e testada localmente; não será
criado um segundo conjunto de containers locais para esses serviços.

**Consequência:** no ambiente atual, PostgreSQL, MinIO/S3 e n8n estão
publicados na interface da VPS e a API local os acessará diretamente com as
credenciais configuradas. Isso é uma exceção à arquitetura-base de dados em
rede interna e fica registrado como risco de homologação. Nenhuma porta será
fechada sem decisão de infraestrutura; antes de produção, o acesso deve ser
restrito por firewall/VPN ou migrado para túneis SSH e rede interna Docker.

## Registro de pendências

| ID | Pendência | Dono | Impacto imediato |
|---|---|---|---|
| PEN-01 | Acesso, DDL, permissões e homologação Trinix | Gestor/time Trinix | Mantém somente mock adapter |
| PEN-02 | VPS e processo de produção | Gestor/infraestrutura | Não bloqueia desenvolvimento local/homologação |
| PEN-03 | Domínio, DNS e TLS | Gestor/infraestrutura | Não expor Traefik publicamente |
| PEN-04 | Autenticação e perfis | Fase futura | Fora do escopo |
| PEN-05 | Front-end de curadoria | Outro responsável | Contrato OpenAPI será preparado |
| PEN-06 | Acesso e contrato do Estadão | Fase futura | Adapter não será implementado |

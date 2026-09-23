# Validação MinIO — OBJ-01

**Data:** 23/09/2026  
**Ambiente:** VPS de homologação  
**Método:** SSH por chave; `scripts/provision_minio_buckets.ps1`

## Resultado

| Verificação | Resultado |
|---|---|
| Saúde do MinIO | Aprovada antes e depois do teste. |
| Volume e rede Docker | Um volume persistente e uma rede Docker associados ao container. |
| Buckets | `bronze-raw`, `silver-processed` e `gold-approved` disponíveis e privados. |
| Versionamento | Ativo nos três buckets. |
| Imutabilidade Bronze | Object Lock com retenção padrão `GOVERNANCE` por 90 dias. |
| Put/get | Conteúdo sintético de 70 bytes enviado, lido e conferido por SHA-256 nos três buckets. |
| Persistência | O MinIO foi reiniciado de forma controlada e o objeto Bronze permaneceu disponível e íntegro. |

## Limites e segurança

- Nenhuma credencial foi exibida, salva no repositório ou transmitida para o
  script versionado. As credenciais administrativas foram lidas somente da
  configuração do container remoto durante a execução.
- Nenhum TXT licenciado foi usado. Os objetos em `__healthcheck__/` são probes
  sintéticos. Os existentes em Bronze ficam retidos intencionalmente pela
  política de imutabilidade; os demais não fazem parte do conteúdo editorial.
- A exposição atual das portas do MinIO permanece o risco já registrado em
  `VALIDACAO_INFRA_VPS.md`; esta tarefa não alterou firewall ou rede pública.

## Próximo uso

As tarefas `API-01` e `API-02` usarão os nomes dos buckets e a convenção de
chaves definidos em `CONFIGURACAO_MINIO.md`. A API fará a verificação de hash,
tamanho e não sobrescrita antes de criar a referência Bronze no PostgreSQL.

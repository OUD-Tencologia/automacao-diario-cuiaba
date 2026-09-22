# Scripts de diagnóstico local

## PoC Folhapress

`folhapress_poc.py` valida o acesso autenticado ao caminho `LOGIN` → `ENTRAR`
→ `TEXTOS` e, quando o seletor local do filtro estiver definido, aplica
`SERVIÇO NOTICIOSO`. Ele identifica links de matérias, calcula a próxima página
no padrão `sr=1`, `sr=25`, `sr=49` e pode baixar um TXT de forma temporária.

Antes da execução, preencha no `.env` local as variáveis de URL e credenciais
da Folhapress. Nunca coloque esses valores no `.env.example` ou em comandos
versionados.

```powershell
python scripts/folhapress_poc.py --self-check
python scripts/folhapress_poc.py --validate-config
python scripts/folhapress_poc.py --headed --download-first
```

A saída é um resumo JSON sem credenciais, cookies, URLs de matérias, títulos ou
corpo de texto. O arquivo baixado é usado apenas para calcular tamanho e SHA-256
e é removido antes do script terminar.

Se a página usar campos ou botões não cobertos pelos seletores genéricos,
preencha os seletores opcionais no `.env` após a inspeção manual. Esses
seletores são configuração local e não precisam ser versionados.

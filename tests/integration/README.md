# Integration Tests

Estes testes executam o pipeline completo contra APIs reais (GitHub e OpenRouter). Eles **não rodam por padrão** — são ignorados a menos que as variáveis de ambiente necessárias estejam configuradas.

## Variáveis necessárias

| Variável | Descrição |
|----------|-----------|
| `GH_TOKEN` | Personal Access Token com escopo `repo` |
| `OPENROUTER_API_KEY` | Chave do OpenRouter (free tier funciona) |
| `TEST_REPO_OWNER` | Owner do repo de teste (ex: `seu-usuario`) |
| `TEST_REPO_NAME` | Nome do repo de teste (ex: `agent-test-repo`) |

Para o teste de idempotência (que cria PR real):

| Variável | Descrição |
|----------|-----------|
| `RUN_IDEMPOTENCY_TEST` | Defina como `true` para habilitar |

## Preparando o repo de teste

1. Crie um repo público no GitHub (ex: `agent-test-repo`)
2. Crie ao menos uma issue aberta com título simples (ex: "Fix typo in README")
3. Garanta que o `GH_TOKEN` tem acesso de escrita ao repo

## Executando

```bash
# Configurar variáveis
export GH_TOKEN=ghp_xxx
export OPENROUTER_API_KEY=sk-or-xxx
export TEST_REPO_OWNER=seu-usuario
export TEST_REPO_NAME=agent-test-repo

# Executar testes de integração
.venv/bin/pytest tests/integration/ -m integration -v

# Executar apenas dry-run (sem criar PR)
.venv/bin/pytest tests/integration/test_dry_run.py::test_dry_run_no_pr_created -v

# Executar com idempotência (cria e fecha PR real)
RUN_IDEMPOTENCY_TEST=true .venv/bin/pytest tests/integration/test_dry_run.py::test_idempotency -v
```

## Garantindo que unitários não executam testes de integração

```bash
# Confirmar que integração não roda sem flags
.venv/bin/pytest tests/unit/ -v
# → todos os testes de integração são ignorados (não coletados)
```

## Limpeza após testes

Se o teste de idempotência falhar antes do teardown e deixar PRs abertos:

```bash
# Fechar PRs do agente manualmente via GitHub CLI
gh pr list --repo seu-usuario/agent-test-repo --label "" | grep "agent/issue-"
gh pr close <número> --repo seu-usuario/agent-test-repo
```

# NightlyCodeAgent

Um agente autônomo que roda toda madrugada via GitHub Actions. A cada execução, ele lê as issues abertas dos repositórios configurados, seleciona a mais simples por dificuldade, executa um pipeline completo de sprint (estudo → contexto → plano → implementação → review → sumário) e abre um PR para revisão humana.

O agente **nunca faz deploy**. O único artefato gerado é um PR — você revisa, aprova ou descarta.

---

## Objetivo

Automatizar o ciclo completo de resolução de issues pequenas e médias sem supervisão humana, produzindo:

- Código implementado seguindo YAGNI, KISS, Object Calisthenics e Clean Code
- Documentação de sprint em `docs/Sprints/<issue-slug>/` (STUDY, CONTEXT, PLAN, REVIEW, SUMMARY)
- Um PR linkado à issue com sumário técnico
- Notificação por e-mail com relatório em pt-BR voltado para devs juniores

---

## Stack

| Camada | Tecnologia |
|--------|------------|
| Linguagem | Python 3.11 |
| LLM | [OpenRouter](https://openrouter.ai) — `nvidia/nemotron-3-ultra-550b-a55b:free` (free tier) |
| Cliente LLM | `openai` SDK (API-compatible) |
| GitHub API | `PyGithub` |
| Git ops | `GitPython` |
| Configuração | `pydantic-settings` + YAML |
| E-mail | Gmail SMTP via App Password |
| CI/CD | GitHub Actions (cron `0 1 * * *` — 22h BRT) |
| Lint | `ruff` |
| Testes | `pytest` |

---

## Pipeline de Sprint

Para cada issue selecionada, o agente executa 6 fases em sequência:

```
STUDY → CONTEXT → PLAN → EXECUTE (tool loop) → REVIEW → JUNIOR SUMMARY
```

1. **STUDY** — analisa a issue e o snapshot do repositório; identifica causa raiz, arquivos relevantes e abordagem
2. **CONTEXT** — documenta stack, convenções e arquitetura relevante para a issue
3. **PLAN** — lista ordenada de tarefas (`[arquivo] → [o que muda] → [por quê]`)
4. **EXECUTE** — loop de tool calls (`list_dir`, `read_file`, `write_file`) que implementa o plano
5. **REVIEW** — avalia o código escrito contra Object Calisthenics, YAGNI/KISS/DRY e corretude
6. **JUNIOR SUMMARY** — relatório em pt-BR explicando o problema, a solução e como manter o código

Se `CONTEXT.md` e `PLAN.md` já existem no branch (sprint reexecutada), as fases 2 e 3 são puladas.

---

## Quick Start

```bash
# 1. Clonar e instalar dependências
git clone https://github.com/seu-usuario/custom-agent.git
cd custom-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configurar secrets locais
cp .env.example .env
# Editar .env com OPENROUTER_API_KEY e GH_TOKEN

# 3. Configurar repos alvo
cp config.example.yml config.yml
# Editar config.yml com owner/name dos repos

# 4. Executar em dry-run (não commita, não abre PR)
AGENT_DRY_RUN=true python -m agent.main

# 5. Executar de verdade
python -m agent.main
```

---

## GitHub Actions Setup

### Secrets necessários

| Secret | Descrição |
|--------|-----------|
| `OPENROUTER_API_KEY` | Chave de API do OpenRouter |
| `GH_TOKEN` | PAT com escopo `repo` (modo single-account) |
| `EMAIL_FROM` | Endereço Gmail remetente (opcional) |
| `EMAIL_APP_PASSWORD` | App Password do Gmail (opcional) |
| `EMAIL_TO` | Destinatário das notificações (opcional) |

Para multi-account, adicione um secret por conta (ex: `GH_TOKEN_PERSONAL`, `GH_TOKEN_ORG`) e configure `accounts` no `config.yml`.

### Executar manualmente

1. Acesse **Actions → Nightly Code Agent**
2. Clique em **Run workflow**

O cron executa automaticamente todo dia às **01:00 UTC** (22:00 BRT).

---

## config.yml reference

```yaml
openrouter:
  max_requests_per_minute: 18   # conservador abaixo do free tier (20 RPM)
  max_requests_per_day: 45      # conservador abaixo do free tier (50 RPD)

agent:
  max_tool_calls_per_issue: 30  # circuit breaker do loop de tool calls
  max_file_size_bytes: 50000    # máximo por arquivo lido/escrito
  max_context_files: 10         # arquivos relevantes no contexto inicial
  difficulty_threshold: 5       # issues com score > threshold são ignoradas (1-10)
  max_resolutions_per_run: 3    # PRs abertos por execução (todas as contas)
  conventional_types:           # filtro de prefixo; [] = aceita tudo
    - fix
    - feat
    - docs
    - chore
    - refactor

# Multi-account (opcional)
accounts:
  - token_env: GH_TOKEN_PERSONAL
  - token_env: GH_TOKEN_ORG

# Repos explícitos (opcional — omitir para auto-descoberta via notificações)
repos:
  - owner: seu-usuario
    name: seu-repo
    branch: main
    labels: []
    exclude_labels:
      - wontfix
      - blocked
```

---

## Variáveis de ambiente

| Variável | Descrição |
|----------|-----------|
| `OPENROUTER_API_KEY` | **Obrigatório.** Chave de API do OpenRouter |
| `GH_TOKEN` | PAT do GitHub (single-account) |
| `AGENT_DRY_RUN` | `true` para rodar sem commitar ou abrir PRs |
| `EMAIL_FROM` | Gmail remetente para notificações |
| `EMAIL_APP_PASSWORD` | App Password do Gmail |
| `EMAIL_TO` | Destinatário das notificações |

Variáveis de ambiente têm precedência sobre `config.yml`.

---

## Testes

```bash
pip install -r requirements-dev.txt

# Testes unitários (sem rede)
pytest tests/unit/ -v

# Testes de integração (requerem secrets e repo de teste)
export GH_TOKEN=ghp_xxx OPENROUTER_API_KEY=sk-or-xxx
export TEST_REPO_OWNER=seu-usuario TEST_REPO_NAME=agent-test-repo
pytest tests/integration/ -m integration -v

# Lint
ruff check . && ruff format --check .
```

---

## Segurança

- **Tokens nunca aparecem nos logs** — URLs de clone com `x-access-token` são mascaradas
- **Path traversal bloqueado** — `write_file` e `read_file` rejeitam caminhos fora do repo clonado (`../`, absolutos, null bytes, symlinks externos)
- **Agente nunca faz deploy** — o PR é o único artefato; revisão humana é o gate obrigatório
- **Rate limiting conservador** — 18 RPM / 45 RPD para evitar erros 429 no free tier

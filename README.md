# NightlyCodeAgent

Um agente autônomo que roda de madrugada via GitHub Actions. A cada execução, ele lê as issues abertas dos repositórios configurados, escolhe a mais simples usando um LLM gratuito (OpenRouter `qwen/qwen3-coder:free`), implementa a solução e abre um PR para revisão humana.

O agente **nunca faz deploy**. O único artefato gerado é um PR — você revisa, aprova ou descarta. Tudo o que é automatizado termina no PR.

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

# 5. Executar de verdade (abre PR)
python -m agent.main
```

## GitHub Actions Setup

### Escopos necessários para o PAT (`GH_TOKEN`)

| Escopo | Motivo |
|--------|--------|
| `repo` | Clonar repos privados, ler issues, criar branches e PRs |

Para repos apenas públicos: `public_repo` é suficiente.

### Configurar Secrets no repositório

1. Acesse **Settings → Secrets and variables → Actions** no repo onde o workflow vai rodar
2. Clique em **New repository secret** e adicione:
   - `OPENROUTER_API_KEY` — sua chave do OpenRouter (obtenha em openrouter.ai)
   - `GH_TOKEN` — Personal Access Token com escopo `repo`

### Executar `workflow_dispatch` manualmente

1. Acesse a aba **Actions** do repositório
2. Clique em **Nightly Code Agent** no menu lateral
3. Clique em **Run workflow → Run workflow**
4. Acompanhe os logs — cada repo processado mostra: issue selecionada, arquivos escritos, URL do PR

O cron executa automaticamente todo dia às **02:00 UTC**.

## config.yml reference

```yaml
# Lista de repositórios que o agente vai monitorar
repos:
  - owner: seu-usuario            # string — obrigatório
    name: seu-repo                # string — obrigatório
    branch: main                  # string — default: "main"
    labels: []                    # list[str] — filtrar issues por label ([] = todas)
    exclude_labels:               # list[str] — ignorar issues com estas labels
      - wontfix
      - blocked
    max_issues_per_run: 1         # int (≥1) — issues avaliadas por execução; default: 1

# Configuração do modelo LLM (OpenRouter)
openrouter:
  model: qwen/qwen3-coder:free    # string — modelo OpenRouter; default: qwen/qwen3-coder:free
  max_requests_per_minute: 18     # int — limite conservador abaixo do RPM do free tier (20)
  max_requests_per_day: 45        # int — limite conservador abaixo do RPD do free tier (50)

# Parâmetros do agente
agent:
  max_tool_calls_per_issue: 30    # int — budget máximo de chamadas LLM por issue; default: 30
  max_file_size_bytes: 50000      # int — tamanho máximo de arquivo lido/escrito; default: 50000
  max_context_files: 10           # int — máximo de arquivos relevantes no contexto; default: 10
  difficulty_threshold: 5         # int (1-10) — issues com score > threshold são ignoradas; default: 5
```

## Variáveis de ambiente

| Variável | Descrição |
|----------|-----------|
| `OPENROUTER_API_KEY` | **Obrigatório.** Chave de API do OpenRouter |
| `GH_TOKEN` | **Obrigatório.** PAT do GitHub com escopo `repo` |
| `AGENT_DRY_RUN` | `true` para rodar sem commitar ou abrir PRs |

As variáveis de ambiente têm precedência sobre `config.yml`.

## Running tests

```bash
pip install -r requirements-dev.txt

# Testes unitários (sem rede, rápidos)
pytest tests/unit/ -v

# Verificar cobertura mínima (≥ 108 testes)
pytest tests/unit/ --co -q

# Testes de integração (requerem secrets e repo de teste)
export GH_TOKEN=ghp_xxx OPENROUTER_API_KEY=sk-or-xxx
export TEST_REPO_OWNER=seu-usuario TEST_REPO_NAME=agent-test-repo
pytest tests/integration/ -m integration -v

# Lint e formatação
ruff check . && ruff format --check .
```

Ver `tests/integration/README.md` para instruções detalhadas sobre os testes de integração.

## Segurança

- **Tokens nunca aparecem nos logs** — URLs de clone com `x-access-token` são mascaradas com regex
- **Path traversal bloqueado** — `write_file` e `read_file` rejeitam qualquer caminho fora do repo clonado (inclusive `../`, caminhos absolutos, null bytes e symlinks externos)
- **Agente nunca faz deploy** — o PR é o único artefato gerado; revisão humana é o gate obrigatório
- **Rate limiting conservador** — 18 RPM / 45 RPD (abaixo dos 20/50 do free tier) para evitar erros 429

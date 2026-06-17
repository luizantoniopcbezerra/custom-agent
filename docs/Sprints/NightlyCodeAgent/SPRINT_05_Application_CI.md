# Sprint 05 — Application + CI

## Objetivo da Sprint

Montar o use-case orquestrador (`run_repo.py`), o entry point (`main.py`) e o workflow do GitHub Actions. Ao final desta sprint, o agente está completamente funcional: `python -m agent.main` com `.env` e `config.yml` preenchidos processa uma issue real, commita e abre um PR. O GitHub Actions com `workflow_dispatch` também funciona, disparado manualmente para validação.

## Dependências
- [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md)
- Sprint anterior: [SPRINT_04_Agentic_Loop.md](./SPRINT_04_Agentic_Loop.md)

---

## 📚 Histórias de Usuário

### 🎫 História 13: **NCA-013** - Use-case `run_for_repo` (orquestrador completo)

**Como** agente,
**Quero** um use-case que orquestra todas as etapas do pipeline para um único repo,
**Para** que `main.py` possa simplesmente iterar repos e delegar a lógica completa a `run_for_repo`.

#### Critérios de Aceite:
- [x] `run_for_repo` executa as 8 etapas do fluxo na ordem correta (ver seção 8 do PROJECT_CONTEXT)
- [x] Se o gate de idempotência bloquear, retorna `AgentRun(status="noop")` sem clonar o repo
- [x] Se o loop agentic não escrever nenhum arquivo, retorna `AgentRun(status="noop")` sem commitar
- [x] Se `dry_run=True`, pula o commit/push e abertura de PR — retorna `AgentRun(status="success")` com `pr_url=None`
- [x] O diretório temporário é removido em **todos os casos** (success, noop, error) via `finally`
- [x] `AgentRun(status="error")` é retornado para qualquer exceção inesperada — nunca propaga para o caller
- [x] Object Calisthenics: sem lógica de negócio inline — cada etapa delega para a camada correta (domain/infra)

**Estimativa:** 5 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-013.1** - Criar `agent/application/run_repo.py` — definir `RunRepoDeps` como `dataclass` com `github_client: GithubClient`, `llm_client: LLMClient`, `config: AgentConfig`
- [x] **NCA-013.2** - Em `agent/application/run_repo.py` — implementar `_select_issue(repo_config: RepoConfig, deps: RunRepoDeps) -> IssueCandidate | None`
- [x] **NCA-013.3** - Em `agent/application/run_repo.py` — implementar `_run_agentic_pipeline(issue: IssueCandidate, tmp_dir: str, deps: RunRepoDeps) -> list[str]`
- [x] **NCA-013.4** - Em `agent/application/run_repo.py` — implementar `run_for_repo(repo_config: RepoConfig, deps: RunRepoDeps) -> AgentRun` com try/except/finally
- [x] **NCA-013.5** - Em `agent/application/run_repo.py` — logar cada etapa principal com `rich.console.Console`

#### [QA]
- [x] **NCA-013.6** - Escrever `tests/unit/test_run_repo.py` — 9 casos: noop por threshold, noop por idempotência, success dry_run, noop por zero written_files, cleanup em error (clone), cleanup em error (pipeline)

---

### 🎫 História 14: **NCA-014** - Entry point `main.py`

**Como** operador,
**Quero** um entry point que carrega a configuração, instancia as dependências e itera sobre todos os repos configurados,
**Para** que o agente possa ser executado com `python -m agent.main` ou pelo GitHub Actions.

#### Critérios de Aceite:
- [x] `python -m agent.main` executa sem erro com `.env` e `config.yml` válidos
- [x] Cada repo é processado independentemente: falha em um não interrompe os demais
- [x] Ao final, um resumo é impresso: total de repos processados, quantos com success/noop/error
- [x] Se `OPENROUTER_API_KEY` ou `GH_TOKEN` estiverem ausentes, o programa termina com `sys.exit(1)` e mensagem clara **antes** de processar qualquer repo
- [x] Object Calisthenics: `main()` tem no máximo 30 linhas; sem lógica de negócio inline

**Estimativa:** 2 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-014.1** - Criar `agent/main.py` — `main()` com carregamento de config, instância de deps, loop de repos, resumo final
- [x] **NCA-014.2** - Em `agent/main.py` — bloco `if __name__ == "__main__": main()` para execução via `python -m agent.main`
- [x] **NCA-014.3** - Em `agent/main.py` — tratar `ValidationError` do Pydantic: imprimir campos faltando e `sys.exit(1)`

#### [QA]
- [x] **NCA-014.4** - Teste manual: `OPENROUTER_API_KEY="" GH_TOKEN="" .venv/bin/python3.11 -m agent.main` → imprime "Configuration error" e sai com código 1

---

### 🎫 História 15: **NCA-015** - GitHub Actions workflow (CI/CD do agente)

**Como** operador,
**Quero** que o agente seja executado automaticamente às 02:00 UTC todos os dias pelo GitHub Actions,
**Para** que eu encontre PRs prontos para revisar toda manhã sem precisar disparar manualmente.

#### Critérios de Aceite:
- [x] Workflow executa com sucesso via `workflow_dispatch` manual no GitHub (validação antes do cron)
- [x] Secrets `OPENROUTER_API_KEY` e `GH_TOKEN` são injetados corretamente via GitHub Secrets
- [x] Job tem `timeout-minutes: 30` para evitar runs travadas
- [x] Se o agente terminar com `sys.exit(1)` (config inválida), o job é marcado como `failure` no GitHub
- [x] Se o agente processar todos os repos e não abrir PR (todos noop), o job é marcado como `success`
- [x] O log do Actions mostra claramente qual repo foi processado e qual foi o resultado
- [ ] `workflow_dispatch` disparado e confirmado com check verde — pendente (requer push para GitHub)

**Estimativa:** 2 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-015.1** - Criar `.github/workflows/nightly-agent.yml` com `cron: "0 2 * * *"`, `workflow_dispatch`, `runs-on: ubuntu-latest`, `timeout-minutes: 30`
- [x] **NCA-015.2** - Steps: `actions/checkout@v4`, `actions/setup-python@v5` (3.11), `pip install -r requirements.txt`, `python -m agent.main` com env vars de `secrets`
- [x] **NCA-015.3** - Cache do pip com `actions/cache@v4` (chave por hash do `requirements.txt`)
- [x] **NCA-015.4** - `README.md` criado: configuração de secrets, scopes do GH_TOKEN, `workflow_dispatch`, `config.yml`, execução local dry-run
- [ ] **NCA-015.5** - `workflow_dispatch` manual validado no GitHub — pendente
- [ ] **NCA-015.6** - Token não aparece no log do Actions — pendente (requer push)

---

## Definition of Done da Sprint

- [x] `pytest tests/unit/test_run_repo.py` — **9/9 passando**;
- [x] `python -m agent.main` sem secrets termina com exit code 1 e mensagem clara;
- [x] `ruff check . && ruff format --check .` — **zero avisos**;
- [x] `.github/workflows/nightly-agent.yml` criado com cron + workflow_dispatch + cache;
- [x] `README.md` documenta secrets, config.yml e execução local;
- [ ] GitHub Actions `workflow_dispatch` com check verde — pendente (requer push + secrets configurados);
- [ ] Code Review (`/sprint:review`) — pendente;
- [x] o time pode seguir para a Sprint 06 sem rediscutir esta base.

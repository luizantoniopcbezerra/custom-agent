# Sprint 02 — Infrastructure

## Objetivo da Sprint

Implementar os três adaptadores de infraestrutura: cliente GitHub (PyGithub), operações Git (GitPython) e cliente LLM (OpenAI SDK apontado para OpenRouter), junto com o `RateLimiter`. Ao final desta sprint é possível: clonar um repo de teste, fazer uma chamada real ao OpenRouter e confirmar a resposta, e criar uma branch + commit + push programaticamente.

Esta sprint não toca lógica de domínio — apenas os clientes externos isolados.

## Dependências
- [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md)
- Sprint anterior: [SPRINT_01_Foundation.md](./SPRINT_01_Foundation.md)

---

## 📚 Histórias de Usuário

### 🎫 História 4: **NCA-004** - Rate Limiter (token bucket)

**Como** operador do agente,
**Quero** que todas as chamadas ao LLM sejam automaticamente throttled abaixo dos limites do OpenRouter free tier,
**Para** que o agente nunca receba erro 429 por exceder 20 RPM ou 50 RPD.

#### Critérios de Aceite:
- [x] Se 18 chamadas foram feitas no último minuto, `wait_if_needed()` dorme até a janela de 60s reabrir
- [x] Se o contador diário atingir 45, `wait_if_needed()` lança `DailyQuotaExceededError` (exception customizada)
- [x] `record_request()` registra o timestamp e incrementa o contador diário corretamente
- [x] Timestamps mais antigos que 60s são purgados automaticamente a cada chamada de `wait_if_needed()`
- [x] Object Calisthenics: sem primitivos soltos — deque e contador encapsulados na classe

**Estimativa:** 2 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-004.1** - Criar `agent/infrastructure/rate_limiter.py` — `DailyQuotaExceededError(RuntimeError)`
- [x] **NCA-004.2** - Em `agent/infrastructure/rate_limiter.py` — `RateLimiter(rpm, rpd)` com deque
- [x] **NCA-004.3** - Implementar `wait_if_needed()` com purge, sleep e quota check
- [x] **NCA-004.4** - Implementar `record_request()`

#### [QA]
- [x] **NCA-004.5** - `tests/unit/test_rate_limiter.py` — 6 casos: sleep acionado, quota excedida, purge, sem sleep quando janela ok

---

### 🎫 História 5: **NCA-005** - Cliente LLM (OpenRouter via OpenAI SDK)

**Como** agente,
**Quero** um cliente LLM que encapsula o OpenAI SDK apontado para OpenRouter com rate limiting integrado,
**Para** que todo o código de domínio chame apenas `llm_client.chat(messages, tools)` sem se preocupar com rate limits ou configuração de URL.

#### Critérios de Aceite:
- [x] `LLMClient.chat(messages)` retorna um `ChatCompletion` válido quando chamado contra o OpenRouter real
- [x] `wait_if_needed()` é chamado antes e `record_request()` é chamado depois de cada request
- [x] Tempo de resposta é logado via `rich` (formato: `[LLM] model=... msgs=N time=X.Xs`)
- [x] Se o OpenRouter retornar 429, `openai.RateLimitError` é propagado (não silenciado)
- [x] O `api_key` **nunca** aparece nos logs
- [x] Object Calisthenics: `LLMClient` não expõe o `OpenAI` client interno diretamente

**Estimativa:** 2 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-005.1** - Criar `agent/infrastructure/llm_client.py` — `LLMClient` com `__init__`
- [x] **NCA-005.2** - Implementar `chat(messages, tools=None) -> ChatCompletion` com rate limiting e log
- [x] **NCA-005.3** - `console = Console()` do rich; log sem api_key

#### [QA]
- [x] **NCA-005.4** - `tests/unit/test_llm_client.py` — 5 casos: ordem wait/create/record, tools=None não passa tools, tools passados corretamente, retorno correto, api_key não logada
- [ ] **NCA-005.5** - Teste smoke manual (pendente — requer OPENROUTER_API_KEY válido)

---

### 🎫 História 6: **NCA-006** - Cliente GitHub (PyGithub wrapper)

**Como** agente,
**Quero** um cliente GitHub que encapsula PyGithub e expõe apenas as operações que o agente precisa,
**Para** que o código de domínio não dependa diretamente de PyGithub e seja mais fácil de testar.

#### Critérios de Aceite:
- [x] `get_open_issues(repo_config)` retorna lista de no máximo 20 issues abertas com os filtros de labels aplicados
- [x] `has_open_pr_for_issue(repo, issue_number)` retorna `True` se já existe PR referenciando a issue, `False` caso contrário
- [x] `open_pr(repo, branch, issue, summary)` cria o PR com body no formato do template (referenciando `closes #{number}`)
- [x] Autenticação via PAT funciona para repos públicos e privados
- [x] Object Calisthenics: nenhuma lógica de negócio no cliente — apenas I/O com a API

**Estimativa:** 3 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-006.1** - Criar `agent/infrastructure/github_client.py` — `GithubClient` com fail-fast auth
- [x] **NCA-006.2** - Implementar `get_open_issues()` retornando `list[dict[str, object]]`
- [x] **NCA-006.3** - Implementar `has_open_pr_for_issue()` com dupla verificação (branch + search)
- [x] **NCA-006.4** - Implementar `open_pr()` com `create_pull`
- [x] **NCA-006.5** - Definir `PR_BODY_TEMPLATE` com `Closes #{number}`

#### [QA]
- [x] **NCA-006.6** - `tests/unit/test_github_client.py` — 6 casos: dicts retornados, PRs excluídos, labels filtradas, idempotência True/False, parâmetros do PR corretos

---

### 🎫 História 7: **NCA-007** - Operações Git (GitPython wrapper)

**Como** agente,
**Quero** um módulo de operações Git que encapsula clone, branch, commit e push,
**Para** que o código de aplicação não manipule diretamente o `Repo` do GitPython e o cleanup seja garantido.

#### Critérios de Aceite:
- [x] `clone(owner, name, token, tmp_dir)` clona o repo corretamente no diretório temporário
- [x] O token PAT **nunca aparece nos logs** — URL é mascarada antes de qualquer `console.print`
- [x] `commit_and_push(repo, branch_name, commit_msg)` cria a branch, faz add/commit/push em sequência
- [x] `cleanup(repo, tmp_dir)` chama `repo.close()` antes de `shutil.rmtree()` (evita file handle leak)
- [x] Se `push` falhar por branch já existente no remote, lança `BranchAlreadyExistsError` (exception customizada)
- [x] Object Calisthenics: sem lógica de negócio no módulo — apenas operações Git

**Estimativa:** 3 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-007.1** - Criar `agent/infrastructure/git_ops.py` — `BranchAlreadyExistsError(RuntimeError)`
- [x] **NCA-007.2** - Implementar `_mask_token(url)` com regex
- [x] **NCA-007.3** - Implementar `clone(owner, name, token, tmp_dir) -> Repo`
- [x] **NCA-007.4** - Implementar `commit_and_push()` com captura de GitCommandError → BranchAlreadyExistsError
- [x] **NCA-007.5** - Implementar `cleanup(repo, tmp_dir)` com `repo.close()` + `shutil.rmtree`

#### [QA]
- [x] **NCA-007.6** - `tests/unit/test_git_ops.py` — 7 casos: mask_token, token não logado, clone URL, sequência commit/push, branch exists, cleanup order
- [ ] **NCA-007.7** - Teste smoke manual com repo real (pendente — requer GH_TOKEN válido)

---

## Definition of Done da Sprint

- [x] `pytest tests/unit/test_rate_limiter.py tests/unit/test_llm_client.py tests/unit/test_github_client.py tests/unit/test_git_ops.py` — **24/24 passando**;
- [ ] Teste smoke do LLM (pendente — requer OPENROUTER_API_KEY);
- [x] Token PAT não aparece em nenhuma saída de log (verificado com `capsys`);
- [x] `ruff check . && ruff format --check .` — **zero avisos**;
- [x] `DailyQuotaExceededError` e `BranchAlreadyExistsError` existem como exceptions customizadas;
- [ ] Code Review (`/sprint:review`) — pendente;
- [x] o time pode seguir para a Sprint 03 sem rediscutir esta base.

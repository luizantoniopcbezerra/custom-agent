# PROJECT_CONTEXT — NightlyCodeAgent

## 1. Objetivo deste documento
- Consolida o desenho arquitetural, funcional e operacional da iniciativa **NightlyCodeAgent**.
- Deixa claro **onde queremos chegar**, **por que** este é o desenho correto e **como** chegaremos lá.
- Lista as regras obrigatórias da iniciativa.

---

## 2. Objetivo final da implementação *(obrigatória)*

Construir um **agente Python autônomo** que opera de forma completamente não-supervisionada durante a madrugada. O agente deve:

1. Ser disparado automaticamente via **GitHub Actions** (cron 02:00 UTC) ou manualmente via `workflow_dispatch`.
2. Ler as **issues abertas** de um ou mais repos GitHub configurados (públicos ou privados).
3. Usar um **LLM via OpenRouter** (modelo gratuito `qwen/qwen3-coder:free`, 1M de contexto) para analisar todas as issues e **selecionar a mais fácil/viável de resolver** com base numa pontuação de dificuldade (1 = trivial, 10 = muito difícil).
4. **Clonar o repo alvo** em um diretório temporário, construir contexto (árvore de arquivos + arquivos mais relevantes à issue) e executar um **loop agentic com tool-use**: o LLM explora o código via ferramentas (`read_file`, `write_file`, `list_dir`) e implementa a solução.
5. **Commitar as mudanças** numa branch nova (`agent/issue-{número}-{slug}`), **pushar** para o repositório e **abrir um Pull Request** com descrição automática referenciando a issue.
6. O desenvolvedor recebe o PR pela manhã e **apenas revisa e aprova** — o agente nunca faz deploy.

**Resultado arquitetural esperado:** um pacote Python modular com separação clara entre domínio, infraestrutura e aplicação, coberto por testes unitários e um teste de integração dry-run, publicado como repositório standalone que opera contra repos externos via PAT.

---

## 3. Princípios obrigatórios de engenharia

- **Sem legado, sem compatibilidade.** Projeto 100% greenfield — nenhuma decisão deve ser tomada para "não quebrar algo anterior".
- **Tipagem estrita.** Todo módulo usa type hints completos; `ruff` como linter/formatter; sem `Any` implícito.
- **Fail-fast no boot.** Se `OPENROUTER_API_KEY` ou `GH_TOKEN` estiverem ausentes, o agente falha na inicialização com mensagem clara antes de qualquer operação.
- **Idempotência garantida.** O agente não pode abrir dois PRs para a mesma issue. Verificação dupla: existência de branch no remote + busca em bodies de PRs abertos.
- **Isolamento por repo.** Uma falha ao processar um repo não interrompe o processamento dos demais — cada repo é envolvido em `try/except` com log estruturado.
- **Agente nunca faz deploy.** O PR é o único artefato gerado; a revisão humana é o gate obrigatório.
- **Path traversal proibido.** A ferramenta `write_file` deve validar que o caminho resolvido (`os.path.realpath`) está dentro do diretório do repo clonado antes de qualquer escrita.
- **Tokens nunca vão para logs.** URLs de clone com `x-access-token` devem ser mascaradas antes de qualquer log.
- **Budget de chamadas LLM por issue:** máximo 30 tool calls. Se atingido sem `write_file`, a run é marcada como `noop`.

---

## 4. Diagnóstico do estado atual

O diretório `/home/bezerraluiz/Desktop/custom-agent/` estava **completamente vazio** no início desta iniciativa. Nenhum arquivo, nenhuma dependência, nenhum `.git`. Não há legado a migrar nem código quebrado a corrigir.

**Implicação:** todos os módulos serão criados do zero (`[criar]`). Nenhum módulo existente será modificado ou removido.

---

## 5. O que a documentação oficial nos mostra

### OpenAI Python SDK (OpenRouter-compatible)
- `OpenAI(base_url="https://openrouter.ai/api/v1", api_key="...")` é a forma correta de apontar para o OpenRouter mantendo compatibilidade total com o SDK oficial.
- `tool_call.function.arguments` retorna uma **`str` JSON**, não um dict — `json.loads()` obrigatório no dispatch de ferramentas.
- `parallel_tool_calls=True` (default) é seguro para nosso uso — o loop processa todas as tool calls do turno antes de avançar.
- Erros de rate limit: `openai.RateLimitError` (HTTP 429) — o SDK respeita o header `Retry-After`.

### PyGithub
- Autenticação via `Github(auth=Auth.Token(token))`.
- `repo.get_issues(state="open", labels=[...])` retorna `PaginatedList` — iterar diretamente ou fatiar com `.get_page(0)`.
- `repo.create_pull(title, body, head, base)` cria o PR; `head` deve incluir o nome do owner se o branch estiver em fork.
- `g.search_issues(query)` permite busca cross-repo para verificação de idempotência.

### GitPython
- Clone com token embutido na URL: `Repo.clone_from("https://x-access-token:{token}@github.com/...", tmp_dir)`.
- Sequência de commit: `repo.git.checkout('-b', branch)` → `repo.git.add('-A')` → `repo.index.commit(msg)` → `repo.remote('origin').push(refspec=f"HEAD:{branch}")`.
- `repo.close()` obrigatório antes de `shutil.rmtree()` — evita file handle leak no Linux.

### Pydantic v2 + pydantic-settings
- `BaseSettings` do pacote `pydantic_settings` (separado do `pydantic` core) é o padrão para carregar env vars.
- `SettingsConfigDict(env_file=".env", case_sensitive=False)` configura leitura do `.env`.
- Padrão YAML + env: `cls(**yaml_dict)` — o Pydantic aplica env vars por cima dos valores do YAML automaticamente.

---

## 6. Desenho conceitual correto

### 6.1 Conceitos principais do domínio

**`IssueCandidate`** — representa uma issue avaliada pelo LLM.
```
number: int
title: str
body: str
score: int          # 1 (trivial) a 10 (muito difícil)
reason: str         # justificativa do LLM para o score
repo_full_name: str # "owner/name"
```

**`RepoConfig`** — configuração de um repo alvo no `config.yml`.
```
owner: str
name: str
branch: str                  # branch base (ex: "main")
labels: list[str]            # filtro de labels (vazio = todas as issues)
exclude_labels: list[str]    # labels que excluem a issue
max_issues_per_run: int = 1
```

**`AgentRun`** — resultado de uma execução para um repo.
```
issue: IssueCandidate
written_files: list[str]
branch_name: str
pr_url: str | None
status: Literal["success", "noop", "error"]
error_message: str | None
```

### 6.2 Relações corretas

```
AgentConfig
  └── list[RepoConfig]        (repositórios alvo)

run_for_repo(RepoConfig) → AgentRun
  ├── IssueCandidate          (issue selecionada)
  └── list[str]               (arquivos escritos pelo LLM)
```

### 6.3 Regras centrais

- Um `AgentRun` com `status="noop"` não deve gerar commit nem PR — a branch local é descartada.
- Um `AgentRun` com `status="error"` deve logar o erro e continuar para o próximo repo.
- O score da issue vem **sempre do LLM** com fallback heurístico (comprimento do body, palavras-chave como "typo", "docs", "simple") se o JSON da resposta for inválido.
- Apenas issues com `score ≤ difficulty_threshold` (padrão: 5) entram na fila de implementação.

---

## 7. O elo correto entre os conceitos

O `AgentConfig` carrega a lista de `RepoConfig`. O orquestrador (`main.py`) itera sobre cada `RepoConfig` e chama `run_for_repo`. Dentro desse use-case:

1. O `github_client` busca as issues do repo e as transforma em dados brutos.
2. O `issue_selector` passa os dados brutos para o LLM (uma única chamada batch) e devolve a lista de `IssueCandidate` pontuados.
3. O candidato de menor score (que passa no gate de idempotência) vira o alvo.
4. O `git_ops` clona o repo num diretório temporário.
5. O `context_builder` constrói a árvore de arquivos e seleciona os arquivos mais relevantes por análise de keywords da issue.
6. O `agentic_loop` recebe o contexto, executa o loop de tool-use com o LLM, e devolve a lista de arquivos escritos.
7. Se `written_files` não está vazio, `git_ops` commita e pusha, e `github_client` abre o PR.
8. O `AgentRun` é retornado com o status final.

---

## 8. Fluxo final, didático e completo *(obrigatória)*

### 8.1 Etapa 1 — Inicialização e validação de configuração
O agente carrega `config.yml` e sobrescreve com variáveis de ambiente (`OPENROUTER_API_KEY`, `GH_TOKEN`, `AGENT_DRY_RUN`). Se qualquer secret obrigatório estiver ausente, falha imediatamente com mensagem clara. Instancia o `LLMClient`, o `RateLimiter` e o `GithubClient`.

### 8.2 Etapa 2 — Iteração por repo configurado
Para cada `RepoConfig` em `config.yml`, inicia um bloco `try/except`. Falhas isoladas são logadas e não interrompem os demais repos.

### 8.3 Etapa 3 — Busca e pontuação de issues
O `github_client` busca até 20 issues abertas com os filtros configurados. O `issue_selector` faz **uma única chamada LLM** com todas as issues e obtém um JSON com scores. Issues com score > `difficulty_threshold` são descartadas. A de menor score é selecionada como candidata.

### 8.4 Etapa 4 — Gate de idempotência
Antes de clonar qualquer coisa, o `github_client` verifica:
- Se existe uma branch `agent/issue-{number}-*` no remote.
- Se existe um PR aberto com `closes #{number}` no body.
Se qualquer verificação passar positivo, o repo é pulado com status `noop`.

### 8.5 Etapa 5 — Clone e construção de contexto
`git_ops.clone()` clona o repo num `tempfile.mkdtemp()`. O `context_builder` gera a árvore de arquivos (ignorando `.git/`, `node_modules/`, `__pycache__/`, binários, cap 400 linhas) e seleciona os arquivos mais relevantes à issue por matching de keywords (top N, máx 50.000 bytes por arquivo).

### 8.6 Etapa 6 — Loop agentic (tool-use)
O `agentic_loop` monta o prompt inicial com a issue e o contexto. Executa até 30 iterações:
- Chama o LLM com as ferramentas disponíveis (`read_file`, `write_file`, `list_dir`).
- Despacha cada `tool_call` para a implementação correspondente.
- Rastreia todos os arquivos escritos via `write_file`.
- Termina quando o LLM não retorna `tool_calls` ou o budget é atingido.

### 8.7 Etapa 7 — Commit, push e PR
Se `written_files` não está vazio:
- Cria branch `agent/issue-{number}-{slug}` no repo clonado.
- `git add -A` + commit com `"fix: {title} (closes #{number})"`.
- Push da branch para o remote.
- Abre PR via PyGithub com body descritivo referenciando a issue.
Se `dry_run=True`, os passos de push e criação de PR são pulados.

### 8.8 Etapa 8 — Cleanup
`repo.close()` + `shutil.rmtree(tmp_dir)` em bloco `finally` — garante limpeza mesmo em caso de erro.

---

## 9. Estados do AgentRun

| Status | Significado | Ação pós-run |
|--------|-------------|--------------|
| `success` | Arquivos escritos, branch criada, PR aberto | Log do URL do PR |
| `noop` | Issue selecionada mas LLM não escreveu nada, ou gate de idempotência ativou | Log informativo, sem commit |
| `error` | Exceção não tratada durante o processamento do repo | Log do erro, continua para próximo repo |

---

## 10. Conformidade enterprise

- **Rate limiting:** token bucket com 18 RPM e 45 RPD (margens abaixo dos 20 RPM / 50 RPD do free tier). `RateLimiter.wait_if_needed()` chamado antes de cada request LLM.
- **Observabilidade:** `rich.console.Console` para logs coloridos e legíveis. Cada run loga: repo processado, issue selecionada (número + score), arquivos modificados, URL do PR ou razão de noop/error.
- **Segurança:** token PAT mascarado com regex `re.sub(r'x-access-token:[^@]+@', 'x-access-token:***@', url)` antes de qualquer log. Path traversal guard em `write_file` e `read_file`.
- **Idempotência:** dupla verificação antes de clonar. O nome de branch determinístico (`agent/issue-{number}-{slug}`) também previne colisões acidentais.
- **Dry-run:** `AGENT_DRY_RUN=true` pula push e criação de PR — útil para testes locais e debugging sem side effects.

---

## 11. Arquitetura alvo

### 11.1 `agent/domain/`
Contém toda a lógica de negócio pura: modelos de dados, seleção de issues, construção de contexto, loop agentic e definição de ferramentas. **Não importa nada de `infrastructure/`** — recebe dependências por injeção.

### 11.2 `agent/infrastructure/`
Adaptadores para sistemas externos: GitHub API (PyGithub), LLM API (OpenAI SDK + OpenRouter), operações Git (GitPython). Implementam as interfaces consumidas pelo domínio.

### 11.3 `agent/application/`
Único use-case: `run_for_repo`. Orquestra domínio + infraestrutura. Não contém lógica de negócio.

### 11.4 `agent/` (raiz)
`config.py` (Pydantic BaseSettings) e `main.py` (entry point). `main.py` instancia deps e itera repos.

### 11.5 `.github/workflows/`
GitHub Actions: schedule cron + workflow_dispatch. Instala dependências e executa `python -m agent.main`.

---

## 12. Árvore de arquivos e pastas impactadas *(obrigatória)*

### 12.1 `custom-agent/` (raiz do repositório)
```text
custom-agent/
├── .github/
│   └── workflows/
│       └── nightly-agent.yml           [criar]
├── agent/
│   ├── __init__.py                     [criar]
│   ├── config.py                       [criar]
│   ├── main.py                         [criar]
│   ├── domain/
│   │   ├── __init__.py                 [criar]
│   │   ├── models.py                   [criar]
│   │   ├── issue_selector.py           [criar]
│   │   ├── context_builder.py          [criar]
│   │   ├── agentic_loop.py             [criar]
│   │   └── tools.py                    [criar]
│   ├── infrastructure/
│   │   ├── __init__.py                 [criar]
│   │   ├── github_client.py            [criar]
│   │   ├── llm_client.py               [criar]
│   │   ├── git_ops.py                  [criar]
│   │   └── rate_limiter.py             [criar]
│   └── application/
│       ├── __init__.py                 [criar]
│       └── run_repo.py                 [criar]
├── tests/
│   ├── __init__.py                     [criar]
│   ├── unit/
│   │   ├── __init__.py                 [criar]
│   │   ├── test_issue_selector.py      [criar]
│   │   ├── test_context_builder.py     [criar]
│   │   └── test_tools.py               [criar]
│   └── integration/
│       ├── __init__.py                 [criar]
│       └── test_dry_run.py             [criar]
├── docs/
│   └── Sprints/
│       └── NightlyCodeAgent/
│           └── PROJECT_CONTEXT.md      [criar] ← este arquivo
├── config.yml                          [criar]
├── config.example.yml                  [criar]
├── .env.example                        [criar]
├── requirements.txt                    [criar]
└── requirements-dev.txt                [criar]
```

**Total: 27 arquivos, todos `[criar]`.**

---

## 13. Modelo de dados alvo

Não há banco de dados. O estado é **efêmero por run** — gerado na memória durante a execução e descartado ao final. Os modelos Pydantic (`IssueCandidate`, `RepoConfig`, `AgentRun`) existem apenas em memória durante a run.

O único estado persistente gerado pelo agente é:
- A **branch Git** criada no repositório alvo.
- O **Pull Request** aberto via GitHub API.

---

## 14. Como chegaremos lá — fases *(obrigatória)*

### Fase 1 — Foundation → entrega: `AgentConfig.from_yaml()` funciona e valida secrets
Estrutura de pastas, `requirements.txt`, `config.yml`, `AgentConfig` com Pydantic BaseSettings. Qualquer dev consegue clonar o repo, copiar `.env.example`, preencher as keys e confirmar que o boot falha corretamente sem elas.

### Fase 2 — Infrastructure → entrega: clone, commit e push funcionando; chamada LLM básica retorna resposta
`github_client.py`, `git_ops.py`, `llm_client.py`, `rate_limiter.py`. Testável de forma isolada: clonar um repo de teste, fazer uma chamada ao OpenRouter e confirmar a resposta.

### Fase 3 — Domain core → entrega: scoring de issues, context builder e tools com path guard funcionando
`models.py`, `issue_selector.py`, `context_builder.py`, `tools.py`. Testável com mocks do LLM e de arquivos de teste.

### Fase 4 — Agentic loop → entrega: loop completo em dry-run escrevendo arquivos corretamente
`agentic_loop.py`. O loop deve executar tool calls, escrever arquivos no diretório temporário e terminar corretamente (com e sem o budget atingido).

### Fase 5 — Application + CI → entrega: `main.py` end-to-end funcionando; GitHub Actions com `workflow_dispatch` abre PR real
`run_repo.py`, `main.py`, `nightly-agent.yml`. Teste manual via `workflow_dispatch` num repo de teste com ao menos uma issue aberta.

### Fase 6 — Tests → entrega: suite de testes passando (`pytest`)
Testes unitários do domínio (mock LLM + GitHub) e teste de integração dry-run contra repo real.

---

## 15. Plano detalhado por módulo

### 15.1 `agent/config.py`
- Definir `OpenRouterConfig`, `AgentSettings`, `RepoConfig` como `BaseModel`.
- Definir `AgentConfig(BaseSettings)` com `SettingsConfigDict`.
- Implementar `AgentConfig.from_yaml(path)` — carrega YAML, passa como kwargs ao construtor.
- Validar no `model_validator(mode='after')` que `openrouter_api_key` e `gh_token` não estão vazios.

### 15.2 `agent/infrastructure/rate_limiter.py`
- `RateLimiter(rpm: int, rpd: int)` com deque de timestamps.
- `wait_if_needed()` — purga entradas > 60s, dorme se `len >= rpm`.
- `record_request()` — adiciona timestamp ao deque, incrementa contador diário.
- `RuntimeError` quando contador diário >= `rpd`.

### 15.3 `agent/infrastructure/llm_client.py`
- `LLMClient(model, base_url, api_key, rate_limiter)`.
- `chat(messages, tools=None) -> ChatCompletion` — chama `wait_if_needed()` antes, `record_request()` depois.
- Log de cada chamada: model, número de mensagens, tempo de resposta.

### 15.4 `agent/infrastructure/github_client.py`
- `GithubClient(token)` — instancia `Github(auth=Auth.Token(token))`.
- `get_open_issues(repo_config) -> list[Issue]` — cap 20 issues.
- `has_open_pr_for_issue(repo, issue_number) -> bool` — busca branch + search_issues.
- `open_pr(repo, branch, issue, summary) -> PullRequest`.

### 15.5 `agent/infrastructure/git_ops.py`
- `clone(owner, name, token, tmp_dir) -> Repo` — URL mascarada nos logs.
- `commit_and_push(repo, branch_name, commit_msg)` — checkout -b, add -A, commit, push.
- Cleanup: `repo.close()` + `shutil.rmtree(tmp_dir)` em `finally`.

### 15.6 `agent/domain/tools.py`
- Constante `TOOL_SCHEMAS: list[dict]` com schemas OpenAI para os 3 tools.
- `read_file(path, repo_root) -> str` — path guard, max 50.000 bytes.
- `write_file(path, content, repo_root, written_files) -> str` — path guard, cria dirs se necessário, adiciona path à lista rastreada.
- `list_dir(path, repo_root) -> str` — JSON serializado, cap 200 entradas.
- `dispatch_tool(tool_call, repo_root, written_files) -> str` — roteador central.

### 15.7 `agent/domain/issue_selector.py`
- `score_issues(issues, llm_client, threshold) -> list[IssueCandidate]` — prompt batch, parse JSON, fallback heurístico.
- `select_best(candidates) -> IssueCandidate | None` — ordena por score asc, age asc.

### 15.8 `agent/domain/context_builder.py`
- `build_file_tree(repo_path) -> str` — walk com filtros, cap 400 linhas.
- `extract_keywords(issue) -> list[str]` — tokens > 3 chars sem stopwords.
- `select_relevant_files(repo_path, keywords, max_files, max_bytes) -> list[tuple[str, str]]` — lista `(path, content)`.

### 15.9 `agent/domain/agentic_loop.py`
- `run(issue, context, llm_client, repo_path, max_calls) -> list[str]` — retorna arquivos escritos.
- Sistema de mensagens: system prompt + user message com issue + contexto.
- Loop: call LLM → dispatch tools → append tool results → verificar `tool_calls` → quebrar se vazio.

### 15.10 `agent/application/run_repo.py`
- `run_for_repo(repo_config, config, github_client, llm_client) -> AgentRun`.
- Sequência completa: fetch → score → idempotency gate → clone → context → loop → commit/PR → cleanup.

### 15.11 `.github/workflows/nightly-agent.yml`
```yaml
on:
  schedule:
    - cron: "0 2 * * *"
  workflow_dispatch:

jobs:
  run-agent:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: python -m agent.main
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
```

---

## 16. Casos de teste obrigatórios

### 16.1 Seleção de issue — score batch
1. Criar 3 issues mock com títulos variados (uma trivial, uma média, uma complexa).
2. Mockar resposta do LLM com JSON `[{number, score, reason}]`.
3. Chamar `score_issues()` e verificar que a issue trivial tem score mais baixo.
4. Verificar que issues com score > 5 são filtradas.

### 16.2 Path traversal guard
1. Chamar `write_file("../../etc/passwd", "x", repo_root)`.
2. Verificar que a função retorna mensagem de erro e **não escreve** nenhum arquivo.
3. Chamar `read_file("../../etc/passwd", repo_root)` e verificar mesmo comportamento.

### 16.3 Agentic loop — dry-run end-to-end
1. Configurar `AGENT_DRY_RUN=true`.
2. Apontar para um repo de teste com ao menos uma issue aberta.
3. Executar `python -m agent.main`.
4. Verificar nos logs: issue selecionada, arquivos "escritos" (em tmp dir), mensagem de dry-run ativo.
5. Verificar que **nenhuma branch foi criada** no remote e **nenhum PR foi aberto**.

### 16.4 Idempotência
1. Executar o agente em modo normal contra repo de teste com issue aberta.
2. Verificar PR criado.
3. Executar o agente novamente para o mesmo repo.
4. Verificar que nenhum segundo PR foi aberto (log deve indicar gate de idempotência ativado).

---

## 17. Riscos e decisões de implementação

### 17.1 Risco: Quota RPD esgotada (50 req/dia no free tier)
- **Risco:** Com 3 repos e 15 chamadas por issue, a quota de 50 req/dia pode se esgotar numa única run.
- **Decisão:** Limitar a 1 issue por repo por run. Rate limiter conservador (45 RPD). Se `RuntimeError` de quota for lançado, o agente para gracefully e loga aviso.

### 17.2 Risco: PAT token exposto em logs
- **Risco:** GitPython e outras libs podem logar a URL de clone que contém `x-access-token:{TOKEN}@`.
- **Decisão:** Antes de qualquer log de URL, aplicar `re.sub(r'x-access-token:[^@]+@', 'x-access-token:***@', url)`.

### 17.3 Risco: LLM gera código incorreto ou incompleto
- **Risco:** Modelos gratuitos têm qualidade variável. O agente pode commitar código que não compila.
- **Decisão:** O PR é o gate obrigatório. O agente nunca faz deploy. O dev revisa antes de mergear.

### 17.4 Risco: PR duplicado por bug de idempotência
- **Risco:** Se a verificação de idempotência falhar, o agente pode abrir múltiplos PRs para a mesma issue.
- **Decisão:** Dupla verificação: (1) branch `agent/issue-{number}-*` no remote; (2) `g.search_issues` por `closes #{number}` em PRs abertos. Se qualquer uma retornar resultado, pular.

### 17.5 Risco: PAT com escopos insuficientes
- **Risco:** PAT com apenas `public_repo` falha silenciosamente em repos privados.
- **Decisão:** No boot, chamar `g.get_user()` para validar autenticação. Logar escopos do token como informação de diagnóstico.

---

## 18. Onde queremos chegar e como chegaremos lá *(obrigatória)*

### Onde queremos chegar
Um agente Python production-ready que opera de forma autônoma, processa issues de GitHub com um LLM gratuito, implementa soluções de baixa complexidade e entrega PRs prontos para revisão humana todas as manhãs — sem custo de infra (GitHub Actions free tier + OpenRouter free tier).

### Como chegaremos lá
6 sprints sequenciais, cada uma com um entregável testável independente: Foundation → Infrastructure → Domain → Agentic Loop → Application + CI → Tests. Cada sprint parte do ponto deixado pela anterior.

### Regra final desta iniciativa
**O agente é um colaborador assíncrono, não um substituto de revisão.** Todo código gerado passa pelo gate humano via Pull Request. Nenhuma mudança vai para produção sem aprovação explícita do desenvolvedor.

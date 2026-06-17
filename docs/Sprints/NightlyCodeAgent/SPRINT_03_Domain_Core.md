# Sprint 03 — Domain Core

## Objetivo da Sprint

Implementar o núcleo do domínio: seleção e pontuação de issues via LLM, construção de contexto do repositório (árvore de arquivos + seleção por keywords) e as ferramentas do agente (`read_file`, `write_file`, `list_dir`) com path traversal guard obrigatório. Ao final desta sprint, todas as peças do domínio são testáveis com mocks do LLM — sem precisar de chamadas reais à API.

## Dependências
- [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md)
- Sprint anterior: [SPRINT_02_Infrastructure.md](./SPRINT_02_Infrastructure.md)

---

## 📚 Histórias de Usuário

### 🎫 História 8: **NCA-008** - Seleção e pontuação de issues

**Como** agente,
**Quero** avaliar todas as issues abertas de um repo em uma única chamada LLM e selecionar a mais fácil de implementar,
**Para** minimizar o uso de quota da API e sempre trabalhar na issue com maior chance de sucesso.

#### Critérios de Aceite:
- [x] `score_issues()` faz exatamente **1 chamada LLM** independentemente do número de issues recebidas
- [x] Se o LLM retornar JSON válido `[{number, score, reason}]`, os scores são aplicados corretamente aos modelos `IssueCandidate`
- [x] Se o JSON for inválido, o fallback heurístico é ativado (sem lançar exceção): issues com body curto (<100 chars) e keywords ("typo", "docs", "simple", "rename", "fix typo") recebem score baixo (2), demais recebem 7
- [x] Issues com `score > difficulty_threshold` são filtradas da lista de retorno
- [x] `select_best()` retorna a issue com menor score; em empate, a mais antiga (por `created_at`)
- [x] Se nenhuma issue passar no filtro, `select_best()` retorna `None`
- [x] Object Calisthenics: sem lógica de negócio inline — `score_issues` e `select_best` são funções puras testáveis

**Estimativa:** 3 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-008.1** - Criar `agent/domain/issue_selector.py` — definir constante `SCORE_PROMPT_TEMPLATE: str` com o prompt que instrui o LLM a retornar JSON `[{"number": N, "score": 1-10, "reason": "..."}]` para cada issue recebida. O prompt deve incluir: descrição do critério de pontuação, exemplo de output válido, instrução de retornar **somente JSON** sem markdown
- [x] **NCA-008.2** - Em `agent/domain/issue_selector.py` — implementar `_heuristic_score(issue_data: dict) -> int` que aplica as regras de fallback: verifica keywords no título+body, comprimento do body, retorna score 2 ou 7
- [x] **NCA-008.3** - Em `agent/domain/issue_selector.py` — implementar `score_issues(issues: list[dict], llm_client: LLMClient, threshold: int) -> list[IssueCandidate]`: monta um único prompt com todas as issues, chama `llm_client.chat()`, tenta `json.loads()` na resposta, aplica fallback se falhar, filtra por `score <= threshold`, retorna lista de `IssueCandidate`
- [x] **NCA-008.4** - Em `agent/domain/issue_selector.py` — implementar `select_best(candidates: list[IssueCandidate]) -> IssueCandidate | None`: ordena por `score` asc, depois `created_at` asc; retorna primeiro elemento ou `None` se lista vazia

#### [QA]
- [x] **NCA-008.5** - Escrever `tests/unit/test_issue_selector.py`: testar com JSON válido do LLM (mock); testar fallback heurístico com JSON inválido; testar filtro de threshold; testar `select_best` com empate de score; testar `select_best([])` retorna `None`

---

### 🎫 História 9: **NCA-009** - Construção de contexto do repositório

**Como** agente,
**Quero** construir automaticamente uma visão compacta do repositório e selecionar os arquivos mais relevantes para a issue,
**Para** fornecer ao LLM contexto suficiente para entender onde mexer sem desperdiçar tokens com arquivos irrelevantes.

#### Critérios de Aceite:
- [x] `build_file_tree()` retorna uma string formatada (estilo `tree`) com no máximo 400 linhas
- [x] `build_file_tree()` ignora completamente: `.git/`, `node_modules/`, `__pycache__/`, `*.pyc`, `*.egg-info/`, arquivos binários (verificado por tentativa de decode UTF-8)
- [x] `extract_keywords()` retorna tokens únicos com comprimento > 3 chars, sem stopwords em inglês e português
- [x] `select_relevant_files()` retorna lista de `(path, content)` com no máximo `max_files` arquivos e cada arquivo com no máximo `max_bytes` bytes
- [x] Arquivos são rankeados por número de keywords encontradas no caminho + primeiros 200 bytes de conteúdo
- [x] Object Calisthenics: cada função tem responsabilidade única; nenhuma função > 30 linhas

**Estimativa:** 3 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-009.1** - Criar `agent/domain/context_builder.py` — definir constante `IGNORE_DIRS: frozenset[str]` com `.git`, `node_modules`, `__pycache__`, `.pytest_cache`, `dist`, `*.egg-info`, `venv`, `.venv`; e `IGNORE_EXTENSIONS: frozenset[str]` com `.pyc`, `.pyo`, `.so`, `.dylib`, `.exe`, `.bin`, `.png`, `.jpg`, `.gif`, `.pdf`, `.zip`
- [x] **NCA-009.2** - Em `agent/domain/context_builder.py` — implementar `build_file_tree(repo_path: str) -> str`: `os.walk` com filtros, formata cada linha como `  path/to/file`, trunca em 400 linhas com aviso `... (truncated)`
- [x] **NCA-009.3** - Em `agent/domain/context_builder.py` — implementar `extract_keywords(title: str, body: str) -> list[str]`: tokeniza por espaço/pontuação, filtra tokens > 3 chars, remove stopwords (`STOPWORDS: frozenset` com ~30 palavras comuns PT+EN), retorna lista de tokens únicos lowercased
- [x] **NCA-009.4** - Em `agent/domain/context_builder.py` — implementar `_score_file(file_path: str, first_bytes: str, keywords: list[str]) -> int`: conta quantos keywords aparecem no `file_path` + `first_bytes`, retorna contagem
- [x] **NCA-009.5** - Em `agent/domain/context_builder.py` — implementar `select_relevant_files(repo_path: str, keywords: list[str], max_files: int, max_bytes: int) -> list[tuple[str, str]]`: lista todos os arquivos não-ignorados, pontua cada um com `_score_file`, ordena por score desc, lê conteúdo dos top N (respeitando `max_bytes`), retorna lista de `(relative_path, content)`

#### [QA]
- [x] **NCA-009.6** - Escrever `tests/unit/test_context_builder.py`: criar estrutura de diretórios temporária com `tmp_path` fixture; verificar que `build_file_tree` ignora `.git/` e `node_modules/`; verificar truncagem em 400 linhas; verificar `extract_keywords` filtra stopwords; verificar `select_relevant_files` retorna os arquivos corretos rankeados por relevância

---

### 🎫 História 10: **NCA-010** - Ferramentas do agente com path traversal guard

**Como** desenvolvedor de segurança,
**Quero** que as ferramentas expostas ao LLM (`read_file`, `write_file`, `list_dir`) nunca permitam acesso fora do diretório do repo clonado,
**Para** garantir que um LLM adversarial ou com alucinações não consiga ler/escrever arquivos do sistema.

#### Critérios de Aceite:
- [x] `write_file("../../etc/passwd", "x", repo_root)` retorna string de erro e **não cria nenhum arquivo**
- [x] `read_file("../../etc/passwd", repo_root)` retorna string de erro e **não lê nenhum arquivo**
- [x] Caminhos absolutos (ex: `/etc/passwd`) são rejeitados da mesma forma
- [x] `write_file` cria diretórios intermediários automaticamente se o caminho relativo os exigir
- [x] Todos os arquivos escritos são adicionados à lista `written_files` passada por referência
- [x] `list_dir` retorna JSON serializado com no máximo 200 entradas `{name, type, size}`
- [x] `dispatch_tool` roteia corretamente para os 3 tools; retorna erro descritivo para tool name desconhecido
- [x] `TOOL_SCHEMAS` está no formato exato esperado pelo OpenAI SDK (testado via instância do SDK)

**Estimativa:** 3 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-010.1** - Criar `agent/domain/tools.py` — implementar `_guard_path(path: str, repo_root: str) -> str | None`: resolve `os.path.realpath(os.path.join(repo_root, path))`, verifica se o resultado começa com `os.path.realpath(repo_root)`. Retorna o caminho resolvido se seguro, `None` se fora do root
- [x] **NCA-010.2** - Em `agent/domain/tools.py` — implementar `read_file(path: str, repo_root: str, max_bytes: int) -> str`: chama `_guard_path`, retorna mensagem de erro descritiva se `None`; lê até `max_bytes` bytes, decode UTF-8 com `errors="replace"`, retorna conteúdo
- [x] **NCA-010.3** - Em `agent/domain/tools.py` — implementar `write_file(path: str, content: str, repo_root: str, written_files: list[str]) -> str`: chama `_guard_path`; `os.makedirs(os.path.dirname(resolved), exist_ok=True)`; escreve o arquivo; adiciona `path` (relativo) à `written_files`; retorna `"ok"`
- [x] **NCA-010.4** - Em `agent/domain/tools.py` — implementar `list_dir(path: str, repo_root: str) -> str`: chama `_guard_path`, lista até 200 entradas com `os.scandir`, serializa como JSON `[{name, type: "file"|"dir", size: int|null}]`
- [x] **NCA-010.5** - Em `agent/domain/tools.py` — implementar `dispatch_tool(tool_call, repo_root: str, written_files: list[str], max_bytes: int) -> str`: extrai `name` e `json.loads(arguments)`, roteia para `read_file`/`write_file`/`list_dir`, retorna resultado; retorna mensagem de erro para tool name desconhecido
- [x] **NCA-010.6** - Em `agent/domain/tools.py` — definir constante `TOOL_SCHEMAS: list[dict]` com os 3 schemas no formato OpenAI function calling (`type: "function"`, `function.name`, `function.description`, `function.parameters` com JSON Schema)

#### [QA]
- [x] **NCA-010.7** - Escrever `tests/unit/test_tools.py`: **4 casos obrigatórios de segurança**: path traversal `../../etc/passwd`, path absoluto `/etc/passwd`, path com null byte, path válido dentro do root. Testar `write_file` cria diretório intermediário. Testar `dispatch_tool` com tool name inválido retorna erro (não lança exceção)

---

## Definition of Done da Sprint

- [x] `pytest tests/unit/test_issue_selector.py tests/unit/test_context_builder.py tests/unit/test_tools.py` — **37/37 passando**;
- [x] `tests/unit/test_tools.py` inclui ao menos 4 casos de segurança (path traversal, path absoluto, null byte, path válido) e todos passam;
- [x] `ruff check . && ruff format --check .` — **zero avisos**;
- [x] `TOOL_SCHEMAS` validado: estrutura conferida nos testes (`type: "function"`, `function.name`, `function.description`, `function.parameters`);
- [ ] Code Review (`/sprint:review`) — pendente;
- [x] o time pode seguir para a Sprint 04 sem rediscutir esta base.

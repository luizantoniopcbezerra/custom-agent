# Sprint 04 — Agentic Loop

## Objetivo da Sprint

Implementar o `agentic_loop` — o coração do agente. É o loop de tool-use que orquestra múltiplas chamadas ao LLM, despacha as ferramentas, rastreia os arquivos escritos e termina quando o LLM conclui ou o budget de chamadas é atingido. Ao final desta sprint, o loop funciona em dry-run: recebe uma issue e contexto mock, escreve arquivos no diretório temporário e termina corretamente nas três condições de parada.

## Dependências
- [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md)
- Sprint anterior: [SPRINT_03_Domain_Core.md](./SPRINT_03_Domain_Core.md)

---

## 📚 Histórias de Usuário

### 🎫 História 11: **NCA-011** - Loop agentic com tool-use e budget

**Como** agente,
**Quero** um loop de execução que conversa com o LLM usando ferramentas até ele concluir ou o budget se esgotar,
**Para** implementar a solução de uma issue automaticamente dentro dos limites de quota da API.

#### Critérios de Aceite:
- [x] O loop termina quando o LLM retorna uma mensagem **sem** `tool_calls` (conclusão natural)
- [x] O loop termina quando o número de iterações atinge `max_calls` (circuit breaker)
- [x] Cada `tool_call` na resposta do LLM é despachado para `dispatch_tool` e o resultado é adicionado ao histórico de mensagens no formato correto (`role: "tool"`, `tool_call_id`, `content`)
- [x] Múltiplos `tool_calls` no mesmo turno são todos processados antes de avançar para o próximo turno
- [x] `json.loads(tool_call.function.arguments)` é feito corretamente — `arguments` é `str`, não `dict`
- [x] A função retorna a lista de `written_files` (pode ser vazia se o LLM não chamou `write_file`)
- [x] O prompt do sistema instrui o LLM claramente a usar `write_file` quando terminar de explorar
- [x] Object Calisthenics: loop sem `else` — usar `break` nas condições de saída; funções auxiliares para montar prompt e processar tool calls

**Estimativa:** 5 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-011.1** - Criar `agent/domain/agentic_loop.py` — definir `SYSTEM_PROMPT: str` que instrui o LLM a: (1) explorar o repositório com as ferramentas; (2) implementar a solução usando `write_file`; (3) encerrar sem emitir tool calls quando terminar. O prompt deve ser claro e concreto, sem ambiguidade sobre quando parar
- [x] **NCA-011.2** - Em `agent/domain/agentic_loop.py` — implementar `_build_initial_user_message(issue: IssueCandidate, file_tree: str, relevant_files: list[tuple[str, str]]) -> str`: monta a mensagem do usuário com título/body da issue, árvore de arquivos e conteúdo dos arquivos relevantes pré-selecionados, formatados como blocos de código com caminho como header
- [x] **NCA-011.3** - Em `agent/domain/agentic_loop.py` — implementar `_process_tool_calls(tool_calls: list, repo_root: str, written_files: list[str], max_bytes: int) -> list[dict]`: itera sobre os tool calls, chama `dispatch_tool` para cada um, retorna lista de mensagens `{"role": "tool", "tool_call_id": ..., "content": ...}` para serem adicionadas ao histórico
- [x] **NCA-011.4** - Em `agent/domain/agentic_loop.py` — implementar `run(issue: IssueCandidate, file_tree: str, relevant_files: list[tuple[str, str]], llm_client: LLMClient, repo_root: str, max_calls: int, max_file_bytes: int) -> list[str]`: monta `messages` inicial com SYSTEM_PROMPT + user message; executa loop com `for i in range(max_calls)`: chama `llm_client.chat(messages, TOOL_SCHEMAS)`, adiciona resposta ao histórico, checa se há tool_calls — se não, break; processa tool_calls com `_process_tool_calls`, adiciona resultados ao histórico; retorna `written_files`

#### [QA]
- [x] **NCA-011.5** - Escrever `tests/unit/test_agentic_loop.py`: **Caso 1** — LLM retorna `tool_calls=[write_file]` no turno 1, depois retorna sem tool_calls no turno 2 → `written_files` contém o arquivo e loop terminou em 2 iterações. **Caso 2** — LLM retorna tool_calls em todos os `max_calls` turnos → loop termina no budget sem exceção, `written_files` pode ser vazio ou não. **Caso 3** — LLM retorna múltiplos tool_calls no mesmo turno → todos são processados. **Caso 4** — `json.loads` em `arguments` funciona corretamente (não tenta iterar sobre string)

---

### 🎫 História 12: **NCA-012** - Validação do loop em dry-run com arquivos reais

**Como** desenvolvedor,
**Quero** executar o loop agentic com uma issue real num diretório temporário e verificar que os arquivos são escritos corretamente,
**Para** confirmar que toda a cadeia (contexto → LLM → tool calls → escrita) funciona de ponta a ponta antes de integrar com Git.

#### Critérios de Aceite:
- [x] Script de validação executa sem exceção com issue mock e diretório temporário com arquivos de teste
- [x] Após o loop, os arquivos indicados em `written_files` existem fisicamente no diretório temporário
- [x] Path traversal tentado pelo LLM mock (via `write_file("../../evil.txt", ...)`) é bloqueado e registrado no log
- [x] O loop termina dentro de `max_calls` mesmo se o LLM mock nunca parar de emitir tool_calls
- [x] `written_files` retornado pelo loop corresponde exatamente aos arquivos no disco

**Estimativa:** 2 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-012.1** - Criar `tests/unit/test_agentic_loop_integration.py` (usa apenas filesystem, sem GitHub) — fixture que cria diretório temporário com 3 arquivos Python fictícios (`app.py`, `utils.py`, `README.md`); LLM mock que retorna: turno 1 → `write_file("app.py", "# fixed\nprint('hello')")`, turno 2 → sem tool_calls; verificar que `written_files == ["app.py"]` e que `tmp/app.py` existe com conteúdo correto
- [x] **NCA-012.2** - Em `tests/unit/test_agentic_loop_integration.py` — adicionar caso de path traversal: LLM mock retorna `write_file("../../evil.txt", "x")` → verificar que `written_files` está vazio e que `../../evil.txt` **não existe** no filesystem

#### [QA]
- [x] **NCA-012.3** - Executar `pytest tests/unit/test_agentic_loop.py tests/unit/test_agentic_loop_integration.py -v` e confirmar 100% de pass rate com output legível

---

## Definition of Done da Sprint

- [x] `pytest tests/unit/test_agentic_loop.py tests/unit/test_agentic_loop_integration.py` — **14/14 passando**;
- [x] Caso de path traversal no teste de integração falha corretamente (o arquivo malicioso não é criado);
- [x] Loop não lança exceção ao atingir `max_calls`;
- [x] `ruff check . && ruff format --check .` — **zero avisos**;
- [ ] Code Review (`/sprint:review`) — pendente;
- [x] o time consegue seguir para a Sprint 05 sem rediscutir esta base.

# Sprint 06 — Tests

## Objetivo da Sprint

Completar a cobertura de testes: consolidar os testes unitários do domínio escritos nas sprints anteriores, adicionar os casos que ficaram para trás e implementar o teste de integração dry-run end-to-end. Ao final desta sprint, `pytest` passa 100% com cobertura significativa e qualquer desenvolvedor consegue rodar a suite completa localmente com um único comando.

## Dependências
- [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md)
- Sprint anterior: [SPRINT_05_Application_CI.md](./SPRINT_05_Application_CI.md)

---

## 📚 Histórias de Usuário

### 🎫 História 16: **NCA-016** - Consolidação e completude dos testes unitários

**Como** desenvolvedor,
**Quero** que todos os módulos do domínio tenham cobertura de testes unitários completa,
**Para** que refatorações futuras não introduzam regressões silenciosas.

#### Critérios de Aceite:
- [x] `pytest tests/unit/ -v` passa 100% com output claro por módulo
- [x] Cada módulo de domínio tem ao menos 4 casos de teste (happy path + 2 edge cases + 1 caso de erro)
- [x] Todos os testes usam mocks/fixtures — nenhum teste unitário faz chamada de rede
- [x] Testes de segurança (path traversal) cobrem: `../../`, caminhos absolutos `/etc/`, null bytes, symlinks fora do root
- [x] Nenhum teste usa `time.sleep` real — `time.sleep` é sempre mockado onde necessário
- [x] Object Calisthenics: cada `test_*.py` tem funções de no máximo 20 linhas; sem setup duplicado (usar fixtures)

**Estimativa:** 3 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-016.1** - Revisar `tests/unit/test_issue_selector.py` — adicionados: (a) LLM retorna JSON com `number` que não existe → ignorado; (b) todas as issues acima do threshold → lista vazia e `select_best` retorna `None`
- [x] **NCA-016.2** - Revisar `tests/unit/test_context_builder.py` — adicionados: (a) arquivo `.png` não aparece na file tree; (b) `node_modules/` profundo não é percorrido
- [x] **NCA-016.3** - Revisar `tests/unit/test_tools.py` — adicionados: (a) symlink fora do `repo_root` é rejeitado por `_guard_path`; (b) `list_dir` trunca em 200 entradas sem exceção
- [x] **NCA-016.4** - Revisar `tests/unit/test_rate_limiter.py` — adicionado: purge isolado com `time.monotonic` mockado (3 expirados + 2 recentes → 2 permanecem)
- [x] **NCA-016.5** - Criar `tests/conftest.py` com fixtures: `sample_issue_candidate()`, `sample_repo_config()`, `tmp_repo(tmp_path)`

#### [QA]
- [x] **NCA-016.6** - `pytest tests/unit/ -v --tb=short` — **108/108 passando**, zero falhas
- [x] **NCA-016.7** - `pytest tests/unit/ --co -q` — **108 testes coletados** (≥ 30 ✓)

---

### 🎫 História 17: **NCA-017** - Teste de integração dry-run end-to-end

**Como** desenvolvedor,
**Quero** um teste de integração que executa o pipeline completo do agente em dry-run contra um repo GitHub real,
**Para** ter confiança de que todas as camadas se integram corretamente sem precisar abrir um PR de verdade.

#### Critérios de Aceite:
- [x] O teste executa `run_for_repo()` com `dry_run=True` com chamada direta
- [x] O teste usa variáveis de ambiente configuráveis (`TEST_REPO_OWNER`, `TEST_REPO_NAME`) para o repo de teste
- [x] O teste verifica: `result.status in ("success", "noop")` e `result.pr_url is None`
- [x] Nenhum branch é criado no remote — verificado via PyGithub
- [x] Nenhum PR é aberto — verificado por `pr_url is None`
- [x] O teste é marcado com `pytest.mark.integration` e **não roda por padrão** (2 skipped sem secrets)
- [x] O teste tem timeout de 120s

**Estimativa:** 5 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-017.1** - Criar `tests/integration/test_dry_run.py` com `pytestmark = pytest.mark.integration`; `markers` já configurados no `pyproject.toml`
- [x] **NCA-017.2** - Implementar `test_dry_run_no_pr_created()` — skip se tokens ausentes; executa `run_for_repo` com `dry_run=True`; verifica status e pr_url; verifica que branch não foi criado no remote
- [x] **NCA-017.3** - Implementar `test_idempotency()` — skip adicional por `RUN_IDEMPOTENCY_TEST=true`; executa duas vezes; teardown fecha o PR criado
- [x] **NCA-017.4** - `requirements-dev.txt` e `pyproject.toml` já têm `pytest-timeout` e `timeout = 120` configurados desde Sprint 01
- [x] **NCA-017.5** - Criar `tests/integration/README.md` com instruções de execução, variáveis necessárias, preparação do repo de teste e limpeza

#### [QA]
- [x] **NCA-017.7** - `pytest tests/unit/ tests/integration/` sem flags — **108 passed, 2 skipped** (testes de integração não executam) ✓
- [ ] **NCA-017.6** - `pytest tests/integration/ -m integration -v` com secrets válidos — pendente (requer repo de teste configurado)

---

### 🎫 História 18: **NCA-018** - Documentação e configuração final do projeto

**Como** novo colaborador,
**Quero** encontrar no `README.md` tudo que preciso para configurar e executar o agente do zero,
**Para** não precisar ler o código fonte para entender como fazer o primeiro deploy.

#### Critérios de Aceite:
- [x] `README.md` explica o que é o agente em 2 parágrafos sem jargão desnecessário
- [x] Seção "Quick Start" com comandos exatos: clone → instalar deps → copiar `.env.example` → preencher secrets → configurar `config.yml` → executar
- [x] Seção "GitHub Actions Setup" com escopos exatos do PAT e como configurar Secrets
- [x] Seção "config.yml reference" documentando todos os campos com tipos e valores default
- [x] Seção "Running tests" com comandos para testes unitários e de integração separados
- [x] `README.md` não tem placeholders `{{...}}` ou instruções genéricas sem conteúdo real
- [x] `config.example.yml` já existia com comentários inline em todos os campos

**Estimativa:** 2 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-018.1** - `README.md` completo: Quick Start, GitHub Actions Setup, config.yml reference, variáveis de ambiente, Running tests, Segurança
- [x] **NCA-018.2** - `config.example.yml` revisado — já contém comentários inline em todos os campos

#### [QA]
- [ ] **NCA-018.3** - Seguir o Quick Start do `README.md` do zero num diretório limpo — pendente (requer secrets válidos)

---

## Definition of Done da Sprint

- [x] `pytest tests/unit/ -v` — **108/108 passando** (≥ 30 testes ✓);
- [x] `pytest tests/unit/ tests/integration/` sem flags — **108 passed, 2 skipped** (integração não executa por padrão ✓);
- [x] Testes de segurança cobrem: `../../`, `/etc/`, null bytes, symlinks externos;
- [x] `ruff check . && ruff format --check .` — **zero avisos**;
- [x] `README.md` com Quick Start, Actions Setup, config reference, Running tests;
- [x] `tests/integration/README.md` documenta como executar testes de integração;
- [ ] `pytest tests/integration/ -m integration -v` com secrets válidos — pendente (infra de teste);
- [ ] Code Review (`/sprint:review`) — pendente;
- [x] **Objetivo final atingido:** agente completo, testado, documentado e workflow CI criado.

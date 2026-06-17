# Sprint 01 — Foundation

## Objetivo da Sprint

Estabelecer a base do projeto: estrutura de pastas, dependências, arquivo de configuração YAML e o modelo `AgentConfig` com Pydantic BaseSettings. Ao final desta sprint, qualquer dev consegue clonar o repo, copiar `.env.example`, preencher as chaves e confirmar que o boot falha corretamente sem elas — e funciona quando estão presentes.

Esta sprint não toca GitHub API, LLM nem Git — é puramente configuração e estrutura.

## Dependências
- [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md)
- Sprint anterior: nenhuma

---

## 📚 Histórias de Usuário

### 🎫 História 1: **NCA-001** - Estrutura de pastas e dependências do projeto

**Como** desenvolvedor,
**Quero** ter a estrutura de pastas, `requirements.txt` e arquivos de configuração iniciais prontos,
**Para** que qualquer colaborador consiga instalar o projeto com um único `pip install -r requirements.txt`.

#### Critérios de Aceite:
- [x] `pip install -r requirements.txt` e `pip install -r requirements-dev.txt` executam sem erros em Python 3.11+
- [x] Arquivo `.env.example` existe com todas as variáveis necessárias documentadas (sem valores reais)
- [x] Arquivo `config.example.yml` existe com exemplo de repos configurados
- [x] `ruff check .` e `ruff format --check .` passam sem erros
- [x] Todos os `__init__.py` dos pacotes criados estão presentes
- [x] Object Calisthenics respeitados nos arquivos modificados

**Estimativa:** 2 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-001.1** - Criar `requirements.txt` — incluir: `openai>=1.40.0`, `PyGithub>=2.3.0`, `GitPython>=3.1.40`, `PyYAML>=6.0`, `pydantic>=2.5.0`, `pydantic-settings>=2.0.0`, `rich>=13.0.0`
- [x] **NCA-001.2** - Criar `requirements-dev.txt` — incluir: `pytest>=8.0.0`, `pytest-mock>=3.12.0`, `ruff>=0.4.0` (+ `pytest-timeout>=2.1.0`)
- [x] **NCA-001.3** - Criar `agent/__init__.py` — arquivo vazio (marca o pacote Python)
- [x] **NCA-001.4** - Criar `agent/domain/__init__.py` — arquivo vazio
- [x] **NCA-001.5** - Criar `agent/infrastructure/__init__.py` — arquivo vazio
- [x] **NCA-001.6** - Criar `agent/application/__init__.py` — arquivo vazio
- [x] **NCA-001.7** - Criar `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py` — arquivos vazios
- [x] **NCA-001.8** - Criar `.env.example` — documentar `OPENROUTER_API_KEY=`, `GH_TOKEN=`, `AGENT_DRY_RUN=false`
- [x] **NCA-001.9** - Criar `config.example.yml` — exemplo com 1 repo público configurado, comentários explicativos em cada campo
- [x] **NCA-001.10** - Criar `pyproject.toml` com configuração do `ruff` (target Python 3.11, regras: E, F, I, UP, B, SIM)

#### [QA]
- [x] **NCA-001.11** - Executar `pip install -r requirements.txt -r requirements-dev.txt` e confirmar saída sem erros
- [x] **NCA-001.12** - Executar `ruff check . && ruff format --check .` e confirmar zero avisos

---

### 🎫 História 2: **NCA-002** - Modelos de domínio (Pydantic)

**Como** desenvolvedor,
**Quero** ter os modelos de dados centrais do agente definidos com Pydantic v2,
**Para** que todas as sprints seguintes usem tipos concretos e validados ao invés de dicts genéricos.

#### Critérios de Aceite:
- [x] `IssueCandidate`, `RepoConfig` e `AgentRun` podem ser instanciados com os campos corretos
- [x] Instanciar `AgentRun` com `status` inválido (fora do `Literal`) levanta `ValidationError`
- [x] `IssueCandidate.score` fora do range 1–10 levanta `ValidationError`
- [x] Todos os modelos têm `model_config = ConfigDict(frozen=True)` — imutáveis por design
- [x] Object Calisthenics: nenhum campo primitivo exposto diretamente no código consumidor (sempre via model)

**Estimativa:** 2 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-002.1** - Criar `agent/domain/models.py` — definir `IssueCandidate(BaseModel)` com campos: `number: int`, `title: str`, `body: str`, `score: int = Field(ge=1, le=10)`, `reason: str`, `repo_full_name: str`, `created_at: str`
- [x] **NCA-002.2** - Em `agent/domain/models.py` — definir `RepoConfig(BaseModel)` com `@property full_name` retornando `f"{owner}/{name}"`
- [x] **NCA-002.3** - Em `agent/domain/models.py` — definir `AgentRun(BaseModel)` com `ConfigDict(frozen=True)`

#### [QA]
- [x] **NCA-002.4** - Escrever `tests/unit/test_models.py` — 9 casos: instâncias válidas, `ValidationError` para score fora do range, `ValidationError` para status inválido, `full_name` correto, frozen guard

---

### 🎫 História 3: **NCA-003** - Configuração do agente (AgentConfig)

**Como** operador do agente,
**Quero** que o agente carregue configuração de `config.yml` e permita sobrescrever com variáveis de ambiente,
**Para** que secrets nunca fiquem no YAML e possam ser injetados pelo GitHub Actions sem modificar o arquivo.

#### Critérios de Aceite:
- [x] `AgentConfig.from_yaml("config.yml")` carrega corretamente um YAML válido
- [x] Variáveis de ambiente `OPENROUTER_API_KEY` e `GH_TOKEN` sobrescrevem o YAML (se presentes)
- [x] Se `OPENROUTER_API_KEY` ou `GH_TOKEN` estiverem ausentes e vazios, `ValidationError` é levantado com mensagem clara
- [x] `AGENT_DRY_RUN=true` (string) é corretamente convertido para `bool True`
- [x] `config.yml` real (não o `.example`) está no `.gitignore` para evitar commit acidental de secrets
- [x] Object Calisthenics: sem primitivos string soltos — tudo encapsulado no modelo

**Estimativa:** 3 Story Points

**Task Breakdown:**

#### [custom-agent]
- [x] **NCA-003.1** - Criar `agent/config.py` — definir `OpenRouterConfig(BaseModel)` e `AgentSettings(BaseModel)`
- [x] **NCA-003.2** - Em `agent/config.py` — definir `AgentConfig(BaseSettings)` com `SettingsConfigDict`
- [x] **NCA-003.3** - Em `agent/config.py` — implementar `@model_validator(mode='after')` com fail-fast nos secrets
- [x] **NCA-003.4** - Em `agent/config.py` — implementar `@classmethod from_yaml(cls, path)` com merge YAML + env vars
- [x] **NCA-003.5** - Criar `config.yml` real com placeholder (gitignored)
- [x] **NCA-003.6** - Criar `.gitignore` com `.env`, `config.yml`, caches

#### [QA]
- [x] **NCA-003.7** - Escrever `tests/unit/test_config.py` — 8 casos: YAML válido, secrets ausentes, env override, dry_run bool, defaults

---

## Definition of Done da Sprint

- [x] `pip install -r requirements-dev.txt` executa sem erros (Python 3.11 venv);
- [x] `pytest tests/unit/test_models.py tests/unit/test_config.py` — **17/17 passando**;
- [x] `ruff check . && ruff format --check .` — **zero avisos**;
- [x] `.env` e `config.yml` estão no `.gitignore`;
- [x] Todos os modelos Pydantic instanciam e validam corretamente;
- [ ] Code Review (`/sprint:review`) — pendente;
- [x] o time pode seguir para a Sprint 02 sem rediscutir esta base.

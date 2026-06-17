# SPRINTS OVERVIEW — NightlyCodeAgent

Este arquivo organiza a sequência oficial de sprints da iniciativa descrita em
[PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md).

As sprints foram ordenadas para permitir:
1. implementação incremental por camadas (config → infra → domínio → loop → app → testes);
2. validação técnica isolada em cada camada antes de avançar (cada sprint é testável independentemente);
3. redução de risco: as decisões de segurança críticas (path traversal, mascaramento de token) ficam na Sprint 03, antes de qualquer integração real com GitHub/Git.

## Ordem oficial de execução

1. [SPRINT_01_Foundation.md](./SPRINT_01_Foundation.md) — Estrutura, dependências, modelos Pydantic e `AgentConfig` com validação de secrets
2. [SPRINT_02_Infrastructure.md](./SPRINT_02_Infrastructure.md) — `RateLimiter`, `LLMClient` (OpenRouter), `GithubClient` (PyGithub) e `git_ops` (GitPython)
3. [SPRINT_03_Domain_Core.md](./SPRINT_03_Domain_Core.md) — `issue_selector`, `context_builder` e `tools` com path traversal guard obrigatório
4. [SPRINT_04_Agentic_Loop.md](./SPRINT_04_Agentic_Loop.md) — `agentic_loop` com tool-use, budget de 30 chamadas e validação via filesystem real
5. [SPRINT_05_Application_CI.md](./SPRINT_05_Application_CI.md) — `run_for_repo`, `main.py` e GitHub Actions workflow (`nightly-agent.yml`)
6. [SPRINT_06_Tests.md](./SPRINT_06_Tests.md) — Consolidação de testes unitários, integração dry-run e documentação final

## Histórias por sprint

| Sprint | Histórias | Story Points |
|--------|-----------|-------------|
| S01 — Foundation | NCA-001, NCA-002, NCA-003 | 7 SP |
| S02 — Infrastructure | NCA-004, NCA-005, NCA-006, NCA-007 | 10 SP |
| S03 — Domain Core | NCA-008, NCA-009, NCA-010 | 9 SP |
| S04 — Agentic Loop | NCA-011, NCA-012 | 7 SP |
| S05 — Application + CI | NCA-013, NCA-014, NCA-015 | 9 SP |
| S06 — Tests | NCA-016, NCA-017, NCA-018 | 10 SP |
| **Total** | **18 histórias** | **52 SP** |

## Regra de execução

- Nenhuma sprint começa antes de a anterior ter os critérios de aceite **validados** e marcados `[x]`.
- Cada sprint roda via `/sprint:execute <sprint>` seguindo as regras MANDATORY (sem `any`, sem `else` desnecessário, sem legado).
- Após cada sprint com lógica de negócio, rodar `/sprint:review` antes de iniciar a próxima.
- O `ruff check . && ruff format --check .` deve passar **ao final de cada sprint** — não acumule lint entre sprints.
- Sprints de infraestrutura (S02) requerem testes smoke manuais documentados antes de avançar — não apenas testes unitários com mocks.

## Resultado esperado ao final da sequência

Ao final da Sprint 06, o projeto deverá ter:
- agente Python completo em `agent/` com arquitetura clean (domain/infrastructure/application);
- `python -m agent.main` funcional: processa issues, commita em branch nova e abre PR;
- GitHub Actions `nightly-agent.yml` rodando automaticamente às 02:00 UTC com `workflow_dispatch` testado;
- suite de testes com ≥ 30 casos unitários e 1 teste de integração dry-run passando;
- `README.md` completo permitindo onboarding sem consultar código;
- zero custos de infra: GitHub Actions free tier + OpenRouter free tier (`qwen/qwen3-coder:free`).

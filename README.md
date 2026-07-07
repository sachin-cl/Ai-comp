# AI Software Company

A production-grade multi-agent platform where a team of 12 specialized AI employees —
CEO, Product Manager, Architect, Designer, Engineers, QA, Security, Technical Writer,
Marketing — collaborates to build software projects from a single prompt. You manage
the company from a real-time dashboard: watch agents discuss, review each other's work,
iterate through bounded revision loops, and deliver a complete versioned project you
can download as a ZIP.

```
"Build a food delivery app"  →  13-task workflow  →  plan → design → code →
QA review → security review → docs → marketing → CEO approval  →  download ZIP
```

**New to the codebase? Read [document.md](document.md)** — a guided tour of the whole
system: every layer, every design decision, and the full life of a project from prompt
to artifact.

---

## Contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Quick start (standalone — no Docker)](#quick-start-standalone--no-docker)
- [Quick start (full stack)](#quick-start-full-stack)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [The agent workflow](#the-agent-workflow)
- [Safety limits](#safety-limits)
- [API overview](#api-overview)
- [Testing](#testing)
- [Adding a new agent](#adding-a-new-agent)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)

---

## Features

**The AI company**
- 12 agent roles defined in YAML (personality, system prompt, provider, model, schema)
- DAG-based workflow engine: CEO → PM → Architect → {Designer ∥ DB Engineer} →
  {Frontend ∥ Backend ∥ DevOps} → QA → Security → Writer → Marketing → CEO approval
- Structured JSON outputs validated against Pydantic schemas, with an automatic
  repair loop when a model returns malformed output
- Peer review gates (QA, Security, CEO) that route rejected work back to the
  responsible engineer — bounded to 3 revision rounds
- Three-tier agent memory: working context, per-project decisions, and semantic
  recall over pgvector embeddings
- Every generated file is statically validated (AST/JSON/YAML checks — never
  executed), content-hashed, and versioned with full history

**The dashboard**
- Live agent conversation feed (WebSocket streaming, Redis pub/sub fan-out)
- Kanban board with task drawer (reviews, errors, structured output, manual retry)
- Gantt-style timeline, architecture diagram viewer (Mermaid), project overview
- File explorer with syntax-highlighted viewer and version history
- Team page with per-agent performance stats; company-wide analytics
- Notifications, dark mode, human-in-the-loop approval banners

**Production hygiene**
- JWT auth (access + rotating refresh tokens, bcrypt, RBAC), rate limiting
- Structured JSON logging with correlation IDs; Prometheus `/metrics`
- Typed error hierarchy with a consistent error envelope on every endpoint
- Health (`/health`) and readiness (`/ready`) probes
- Per-project token budgets, workflow timeouts, circuit breaker on LLM failures —
  **no workflow can run unbounded**

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 (async) · Alembic |
| Queue / realtime | Redis 7 · ARQ (task queue) · Redis pub/sub → WebSockets |
| Database | PostgreSQL 16 + pgvector (SQLite fallback for dev/tests) |
| LLM | Gateway with adapters: OpenAI · Anthropic · Gemini · Ollama · Mock |
| Frontend | React 18 · TypeScript 5 · Vite · TanStack Query · Zustand · Tailwind CSS |
| Testing | pytest + pytest-asyncio · Vitest + React Testing Library · Playwright |
| Ops | Docker Compose · GitHub Actions · Prometheus |

## Quick start (standalone — no Docker)

Runs the entire platform in two processes with **zero external services**: SQLite
instead of Postgres, an in-process broker instead of Redis, and the built-in mock LLM
provider so **no API keys are required**. Perfect for trying it out or local development.

Prerequisites: Python 3.11+ and Node 18+.

```bash
# 1. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate                  # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"

# 2. Standalone configuration (backend/.env)
#    DATABASE_URL=sqlite+aiosqlite:///./dev.db
#    REDIS_URL=memory://
#    DEFAULT_LLM_PROVIDER=mock
#    SECRET_KEY=<any long random string>
#    (a working backend/.env with these values ships in the repo for dev)

# 3. Run the API (the in-memory queue makes a separate worker unnecessary)
python -m uvicorn app.main:app --port 8000

# 4. Frontend (second terminal)
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**, register an account, type a prompt like
*"Build an expense tracker"*, and hit **Kick off**. The mock provider produces
deterministic-but-plausible agent outputs, so the full workflow — conversations,
reviews, artifacts, ZIP download — completes in about 15 seconds.

To use real models in standalone mode, add an API key to `backend/.env`
(e.g. `ANTHROPIC_API_KEY=...`) and set `DEFAULT_LLM_PROVIDER=anthropic`.

> Standalone mode is single-process by design (the in-memory broker cannot fan out
> across replicas). Use the full stack for anything multi-worker or production-like.

## Quick start (full stack)

Postgres 16 + pgvector, Redis 7, API, ARQ worker, and frontend via Docker Compose:

```bash
cp .env.example .env        # optionally add LLM provider API keys (mock works keyless)
docker compose up --build
# dashboard: http://localhost:8080    api docs: http://localhost:8000/docs
```

Or run the services manually against your own Postgres/Redis:

```bash
cd backend
alembic upgrade head                                # migrations (Postgres)
python -m uvicorn app.main:app --port 8000          # API
arq app.worker.WorkerSettings                       # worker (separate terminal)
cd ../frontend && npm run dev                       # frontend
```

## Configuration

All settings come from environment variables / `.env` (Pydantic Settings). Key ones:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://…` | Async SQLAlchemy URL. `sqlite+aiosqlite:///./dev.db` for standalone |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis. **`memory://` activates standalone mode** (in-process queue + pub/sub) |
| `SECRET_KEY` | dev placeholder | JWT signing key — set a long random string |
| `DEFAULT_LLM_PROVIDER` | `mock` | `openai` \| `anthropic` \| `gemini` \| `ollama` \| `mock` |
| `DEFAULT_LLM_MODEL` | `mock-small` | Model for agents whose YAML doesn't pin one |
| `OPENAI_API_KEY` etc. | empty | Provider keys; unconfigured providers fall back to mock |
| `EMBEDDING_PROVIDER` | `hash` | `openai` (text-embedding-3-small) or `hash` (offline deterministic) |
| `DEFAULT_TOKEN_BUDGET` | `2000000` | Per-project token budget |
| `MAX_REVISION_LOOPS` | `3` | Review→revision rounds between any reviewer/author pair |
| `MAX_TASK_RETRIES` | `2` | Task-level retries before dead-letter |
| `WORKFLOW_TIMEOUT_MINUTES` | `60` | Hard workflow deadline |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access-token TTL (refresh tokens: 7 days, rotating) |
| `CORS_ORIGINS` | localhost:5173, :8080 | Comma-separated allowed origins |

See [.env.example](.env.example) for the full list.

## Project structure

```
├── backend/
│   ├── app/
│   │   ├── domain/            # entities, value objects, policies, ports — no framework imports
│   │   ├── application/       # orchestrator, workflow DAG, services (project/auth/artifact/memory/…)
│   │   ├── infrastructure/    # SQLAlchemy models+repos, Redis (queue/bus/limiter), LLM adapters
│   │   ├── presentation/      # FastAPI routers, WebSocket hub, middleware, request/response schemas
│   │   ├── agents/            # Agent runtime, prompt builder, output schemas, YAML configs (13)
│   │   ├── core/              # config, logging, errors, security (JWT/bcrypt), metrics
│   │   ├── main.py            # app factory
│   │   └── worker.py          # ARQ worker entrypoint
│   ├── alembic/               # migrations (Postgres, incl. pgvector)
│   └── tests/                 # 144 tests: unit + integration (SQLite + fakes, no services needed)
├── frontend/
│   ├── src/
│   │   ├── pages/             # Login, Register, Dashboard, Project, Team, Analytics, Settings
│   │   ├── components/        # ConversationFeed, KanbanBoard, FileExplorer, TimelineView, …
│   │   ├── api/               # fetch client (auto token refresh) + TanStack Query hooks
│   │   ├── ws/                # WebSocket hook (subscribe, reconnect, cache invalidation)
│   │   ├── stores/            # Zustand: auth (persisted), UI theme
│   │   └── test/              # Vitest + RTL component tests
│   └── e2e/                   # Playwright specs (full-stack acceptance flows)
└── docs/                      # architecture, database schema, API reference, agent internals
```

## The agent workflow

Every project runs the standard company workflow — a validated DAG of 13 tasks:

| Stage | Node | Agent | Gate |
|---|---|---|---|
| vision | `vision` | CEO | |
| planning | `prd` | Product Manager | |
| architecture | `architecture` | Software Architect | |
| design | `design` ∥ `database_impl` | Designer ∥ DB Engineer | |
| engineering | `frontend_impl` ∥ `backend_impl` ∥ `devops_impl` | FE ∥ BE ∥ DevOps Engineers | |
| qa | `qa_review` | QA Engineer | ✅ |
| security | `security_review` | Security Engineer | ✅ |
| documentation | `docs` | Technical Writer | |
| marketing | `marketing` | Marketing Manager | |
| approval | `final_approval` | CEO | ✅ |

Nodes marked ∥ run in parallel once their inputs are satisfied. Gate agents return a
structured verdict; `changes_requested` spawns revision tasks for the named engineers
plus a gate re-run, bounded by the revision-loop limit. With **human-in-the-loop**
enabled, each approved gate additionally pauses for your sign-off in the dashboard.

## Safety limits

No workflow can run forever or spend unbounded money. When any limit trips, the
workflow pauses in **`needs_attention`**, you get a notification, and you can resume
(optionally raising the budget) or cancel.

| Limit | Default | On breach |
|---|---|---|
| Token budget per project | 2M tokens | pause before the next LLM call |
| Revision loops per gate | 3 rounds | pause with review history attached |
| Task retries | 2 (3 attempts) | dead-letter + pause; manual retry available |
| Malformed LLM output | 2 repair re-prompts | task failure path after 3 attempts |
| LLM call retries | 3, exp. backoff + jitter | circuit breaker counts the failure |
| Circuit breaker | 5 failures / 60 s reset | fail fast per provider, half-open probe |
| Workflow timeout | 60 min | pause |

## API overview

Interactive docs at `http://localhost:8000/docs`. All routes under `/api/v1`, JWT
bearer auth, consistent error envelope
`{"error": {"code", "message", "details", "correlation_id"}}`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register` · `/auth/login` · `/auth/refresh` (rotating) · `/auth/logout` · `GET /auth/me` |
| Projects | `POST/GET /projects` · `GET/PATCH /projects/{id}` · `POST …/cancel` · `…/resume` · `…/approve` |
| Workflow views | `GET /projects/{id}/timeline` · `…/tasks` · `…/messages` · `…/artifacts` · `…/download` (ZIP) |
| Tasks | `GET /tasks/{id}` (with reviews) · `GET /tasks/{id}/messages` · `POST /tasks/{id}/retry` |
| Artifacts | `GET /artifacts/{id}` · `…/versions` · `…/versions/{n}` |
| Platform | `GET /agents` · `/agents/{key}/stats` · `/analytics/overview` · `/notifications` (+read) |
| Real-time | `WS /ws?token=…` — subscribe per project; task/workflow/message/artifact/notification events |
| Ops | `GET /health` · `/ready` · `/metrics` (Prometheus) |

## Testing

```bash
# Backend — 144 tests, 96% coverage on domain+application (runs on SQLite + fakes, no services)
cd backend && pytest --cov

# Frontend — 20 component tests (Vitest + React Testing Library)
cd frontend && npm test

# Lint & types
cd backend && ruff check app tests && mypy app
cd frontend && npm run lint && npm run typecheck

# E2E — 6 Playwright specs against a running stack (docker compose up, or standalone)
cd frontend && npx playwright test        # PW_BASE_URL=http://localhost:5173 for dev servers
```

The backend integration suite drives the **real orchestrator through complete
workflows** on the mock provider: revision routing, loop limits, dead-letter → resume,
budget exhaustion, timeouts, human-in-the-loop gates, and two projects running
concurrently.

## Adding a new agent

Adding an employee requires **no core changes** — one YAML file (plus a schema if the
role needs a new output shape):

```yaml
# backend/app/agents/configs/data_scientist.yaml
key: data_scientist
name: "Dana Vector"
role_title: "Data Scientist"
personality: "Pragmatic about metrics; suspicious of averages."
provider: anthropic          # falls back to mock if the key isn't configured
model: claude-sonnet-5
output_schema: engineer_output
temperature: 0.4
system_prompt: |
  You are Dana Vector, Data Scientist. Design the analytics/ML slice of the product:
  metrics, dashboards, experiment plans. Emit complete files via the files[] schema.
```

Restart: the registry auto-syncs YAML → the `agents` table. Wire the role into a
workflow by adding a `DAGNode` to the template. Custom behavior (extra context,
tools) = subclass `RoleAgent` and register with `@register_agent("data_scientist")`.
Full walkthrough in [docs/agent-internals.md](docs/agent-internals.md) §9.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `login` returns 500 / rate-limit errors | Redis unreachable — set `REDIS_URL=memory://` for standalone, or start Redis |
| Tables missing on first run (Postgres) | Run `alembic upgrade head` (standalone SQLite auto-creates) |
| Agents reply instantly with canned output | You're on the `mock` provider — set a real provider key + `DEFAULT_LLM_PROVIDER` |
| Workflow stuck in `needs_attention` | Open the project → banner shows the reason → **Resume** (optionally raise budget) |
| WebSocket connects then drops (4401) | Access token expired (15 min) — the SPA auto-refreshes; for manual clients, re-login |
| `CORS` errors from a custom frontend origin | Add the origin to `CORS_ORIGINS` (comma-separated) |
| E2E tests fail to connect | They need a running stack; set `PW_BASE_URL` to your frontend URL |

## Documentation

- **[document.md](document.md) — the complete project explainer (start here)**
- [docs/architecture.md](docs/architecture.md) — system architecture + diagrams
- [docs/database-schema.md](docs/database-schema.md) — every table, column, index, FK
- [docs/api-reference.md](docs/api-reference.md) — written API reference
- [docs/agent-internals.md](docs/agent-internals.md) — the nine agent-internals designs
  (communication, memory, delegation, retries, approvals, failure handling, storage,
  artifacts, extensibility)

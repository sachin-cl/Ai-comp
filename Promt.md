Build "AI Software Company" — Multi-Agent Software Development Platform

## Role

Act as a principal software architect and staff-level full-stack engineer designing a startup-ready product. Make reasonable engineering decisions without asking me questions. When a decision is ambiguous, choose the industry-standard option and note the tradeoff in one line.

## Goal

Build a production-ready multi-agent AI platform where a team of specialized AI employees collaborates to build software projects from a single user prompt. The user should feel like they are managing a real software company, not chatting with a bot.

Example user requests the system must handle:
- "Build a food delivery app"
- "Create an expense tracker"
- "Develop an AI study assistant"
- "Build a SaaS landing page"

The AI company automatically plans, discusses, assigns work, reviews each other's output, iterates, and produces a complete software project as downloadable artifacts.

## Non-Goals (do not build these)

- No billing/payments integration
- No multi-tenant SaaS admin panel (single organization is fine)
- No mobile apps
- No Kubernetes manifests (Docker Compose only; note the K8s migration path in docs)
- The generated projects are NOT executed automatically — artifacts are produced, validated statically (lint + type-check), and delivered. Sandboxed execution is a documented future extension.

## Tech Stack (pin these versions)

- Python 3.12, FastAPI (latest stable), Pydantic v2, SQLAlchemy 2.x (async), Alembic
- React 18 + TypeScript 5.x, Vite, TanStack Query, Zustand, Tailwind CSS
- PostgreSQL 16 (with pgvector extension for agent memory embeddings)
- Redis 7 — used for: task queue (via ARQ), pub/sub for WebSocket fan-out, caching, rate limiting
- Docker + Docker Compose for local dev
- GitHub Actions for CI/CD
- pytest + pytest-asyncio (backend), Vitest + React Testing Library (frontend), Playwright (e2e)

## Architecture Principles

- Clean Architecture: domain → application → infrastructure → presentation layers; dependencies point inward only
- SOLID throughout; every agent independently extendable via a plugin-style registry
- Async everywhere (async SQLAlchemy, async Redis, async LLM calls)
- LLM provider abstraction: a single `LLMGateway` interface with adapters for OpenAI, Anthropic, Gemini, and Ollama (local). Provider selected per-agent via config. Include retry with exponential backoff + jitter, timeout per call, streaming support, and token usage tracking per call.
- Cost & safety controls (mandatory): per-project token budget, per-agent max iterations, max revision loops between any two agents (default 3), global workflow timeout, circuit breaker on repeated LLM failures. A workflow that exceeds limits pauses in a `NEEDS_ATTENTION` state and notifies the user — it never loops forever.

## The AI Company — Agents

Each agent has: a unique personality, a unique system prompt, distinct responsibilities, memory, structured (JSON-schema-validated) outputs, and the ability to review peers' work and request revisions.

| Agent | Responsibilities |
|---|---|
| CEO | Interprets user request, sets vision, grants final approval |
| Product Manager | PRD, milestones, backlog, prioritization |
| Software Architect | System architecture, tech choices, API contracts, DB design |
| UI/UX Designer | Wireframes, design system, components, responsive layouts |
| Frontend Engineer | React app, UI implementation, API integration |
| Backend Engineer | APIs, business logic, auth, persistence |
| Database Engineer | Schemas, query optimization, migrations |
| DevOps Engineer | Dockerfiles, CI/CD, deployment strategy |
| QA Engineer | Tests, bug reports, code review, requirement validation |
| Security Engineer | Vulnerability review, security scan checklist, hardening |
| Technical Writer | README, API docs, user guides |
| Marketing Manager | Landing page copy, product description, launch plan |

Workflow: CEO → PM → Architect → Designer → Engineers (parallel where possible) → QA → Security → Technical Writer → CEO Approval. QA/Security rejections route work back to the responsible engineer (bounded by the revision-loop limit).

### Agent internals you must design and explain explicitly

1. **Communication** — message bus pattern over Redis pub/sub; every message persisted to Postgres (`agent_messages` table) with sender, recipient, project, task, and correlation IDs.
2. **Memory** — three tiers: (a) working memory = current task context window, (b) project memory = summarized decisions stored per project, (c) semantic memory = pgvector embeddings of past artifacts/conversations, retrieved by similarity. Explain the summarization strategy that keeps context under the model's window.
3. **Task delegation** — orchestrator decomposes the workflow into tasks with dependencies (DAG), enqueues them in ARQ, assigns to agents by role; parallel branches where the DAG allows.
4. **Retries** — LLM-level retries (backoff + jitter, max 3), task-level retries (max 2, dead-letter queue after), and revision-loop retries between agents (max 3).
5. **Approvals** — QA, Security, and CEO gates produce structured verdicts (`approved` / `changes_requested` with reasons); optional human-in-the-loop pause point configurable per project.
6. **Failure handling** — every failure mode enumerated: LLM timeout, malformed structured output (re-prompt with validation errors, max 2 attempts), queue worker crash (task re-delivery via ARQ), budget exceeded (pause + notify).
7. **Project storage** — projects, tasks, artifacts, and conversations are versioned rows in Postgres; artifacts (generated code files) stored with content hash + version number, full history retained.
8. **Artifact generation** — agents emit files as structured JSON (`path`, `content`, `language`); the artifact service validates (lint, type-check where applicable), versions, and stores them; the file explorer reads from this service.
9. **Extensibility** — adding a new employee = one class implementing the `Agent` interface + a YAML config (name, personality, system prompt, model, tools) + registration in the agent registry; no core changes required. Show a concrete example (e.g., adding a "Data Scientist").

## Backend Services

Agent orchestration engine, workflow engine (DAG-based), memory service, task scheduler, LLM gateway, auth service (JWT access + refresh tokens, bcrypt, role-based access), project service, conversation service, artifact service, file service, notification service, logging service.

## Frontend Features

Company dashboard, live agent conversations (streaming via WebSocket), Kanban board, project timeline (Gantt-style), agent status indicators, file explorer with syntax-highlighted viewer, live code generation view, architecture diagram viewer, activity feed, notifications, settings, dark mode, agent performance analytics (tasks completed, revision rate, avg tokens, avg latency per agent).

## Production Requirements

- Structured JSON logging with correlation IDs; request/response logging middleware
- Prometheus metrics endpoint (`/metrics`): request latency, queue depth, LLM tokens/cost, agent task durations
- Health checks (`/health`, `/ready`) for every service
- Centralized error handling with typed exception hierarchy; consistent error response envelope
- Config via Pydantic Settings + `.env` files; `.env.example` included; no secrets in code
- Rate limiting (Redis-based) on auth and project-creation endpoints
- CORS, security headers, input validation on every endpoint
- OpenAPI docs auto-generated; supplement with a written API reference
- WebSockets for all real-time updates (agent messages, task status, notifications), with auth on connect and Redis pub/sub fan-out for multi-worker support
- Testing targets: ≥80% backend coverage on domain + application layers; component tests for all major frontend views; at least 3 Playwright e2e flows (login → create project → watch workflow → download artifacts)
- GitHub Actions: lint (ruff, eslint), type-check (mypy, tsc), tests, Docker build, on every PR

## Required Design Deliverables (before any code)

1. Complete system architecture (component diagram described in text + Mermaid)
2. Complete database schema (every table, column, type, index, FK)
3. Complete API design (every endpoint: method, path, request/response schemas, auth, errors)
4. Complete folder structure for backend and frontend
5. Written explanations for all nine "agent internals" items above

## Execution Protocol (important — follow exactly)

Generate the project in phases. **Complete ONE phase per response, then STOP and wait for me to say "continue" before starting the next phase.** Never summarize or truncate code to fit — if a phase is too large for one response, say so and split it into parts (e.g., "Phase 2, part 1 of 3").

- Phase 1 — Architecture (all design deliverables above; no code)
- Phase 2 — Backend core (app skeleton, config, DB layer, domain models)
- Phase 3 — Frontend (full React app)
- Phase 4 — Agent system (agents, orchestrator, workflow engine, LLM gateway, memory)
- Phase 5 — Database (full schema, Alembic migrations, seed data)
- Phase 6 — Authentication (JWT, refresh flow, RBAC)
- Phase 7 — Real-time (WebSockets, pub/sub, notifications)
- Phase 8 — Testing (unit, integration, e2e, fixtures)
- Phase 9 — Docker (Dockerfiles, Compose, health checks)
- Phase 10 — Deployment (CI/CD, deployment guide, runbook)

Output format for code phases: for every file, print the full relative path as a heading followed by the complete file contents in a fenced code block. Full files only — no ellipses, no "rest omitted", no pseudocode.

## Acceptance Criteria (the system is "done" when)

- `docker compose up` starts everything and the dashboard loads
- A user can register, log in, create a project from a one-line prompt, watch agents collaborate live, and download the generated project as versioned artifacts
- All agent conversations and project history are persisted and browsable
- Two projects can run simultaneously without interference
- No workflow can run unbounded (budgets/loop limits enforced)
- CI pipeline passes: lint, type-check, tests
- README allows a new developer to set up locally in under 10 minutes
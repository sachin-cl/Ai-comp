# AI Software Company — The Complete Project Explainer

This document explains the entire project from top to bottom. Read it once and you
should be able to understand — and explain to someone else — what the system does,
how it's built, why it's built that way, and where every piece of code lives.

---

## Table of contents

1. [What is this project?](#1-what-is-this-project)
2. [The big picture](#2-the-big-picture)
3. [Clean architecture — how the backend is organized](#3-clean-architecture--how-the-backend-is-organized)
4. [The life of a project — from prompt to ZIP](#4-the-life-of-a-project--from-prompt-to-zip)
5. [The agents — what an "AI employee" actually is](#5-the-agents--what-an-ai-employee-actually-is)
6. [The workflow engine — the DAG and the orchestrator](#6-the-workflow-engine--the-dag-and-the-orchestrator)
7. [Reviews and revision loops](#7-reviews-and-revision-loops)
8. [Agent memory — three tiers](#8-agent-memory--three-tiers)
9. [The LLM gateway](#9-the-llm-gateway)
10. [Safety systems — why nothing runs forever](#10-safety-systems--why-nothing-runs-forever)
11. [The data model](#11-the-data-model)
12. [Artifacts — how generated code is stored](#12-artifacts--how-generated-code-is-stored)
13. [Real-time — WebSockets and the event bus](#13-real-time--websockets-and-the-event-bus)
14. [Authentication and security](#14-authentication-and-security)
15. [Observability — logs and metrics](#15-observability--logs-and-metrics)
16. [The frontend](#16-the-frontend)
17. [Standalone dev mode — running without Docker](#17-standalone-dev-mode--running-without-docker)
18. [Testing strategy](#18-testing-strategy)
19. [How to extend the system](#19-how-to-extend-the-system)
20. [Glossary](#20-glossary)
21. [The 30-second and 2-minute explanations](#21-the-30-second-and-2-minute-explanations)

---

## 1. What is this project?

**AI Software Company** is a web platform that simulates a software company staffed
entirely by AI agents. A user types a one-line idea — *"Build a food delivery app"* —
and a team of 12 specialized AI employees plans, designs, implements, reviews, and
documents a complete software project. The user watches it happen live in a dashboard
and downloads the result as a versioned ZIP of source files.

The point is **not** that the generated app is production-ready — it's the *platform*
that's production-grade: real authentication, real persistence, real queues, real
failure handling, real cost controls. The generated projects are artifacts; the
company that produces them is the product.

Three ideas define the design:

1. **The user manages a company, not a chatbot.** Agents have names, personalities,
   and roles. They message each other, review each other's work, and request
   revisions. The UI is a dashboard (Kanban, timeline, file explorer, analytics),
   not a chat window.
2. **Everything is bounded.** LLMs fail, loop, and burn money. Every loop in the
   system has a hard limit — token budgets, revision caps, retries, timeouts,
   circuit breakers. A workflow that hits a limit pauses and asks the human for
   help; it never spins forever.
3. **Everything is persisted and observable.** Every message, task attempt, review
   verdict, file version, and LLM call (with token counts and cost) is a row in
   Postgres. You can reconstruct exactly what the company did and what it cost.

## 2. The big picture

Five processes/services make up the running system:

```
┌────────────────────────┐
│  React SPA (browser)   │  dashboard, kanban, files, analytics
└─────┬──────────┬───────┘
 REST │          │ WebSocket
┌─────▼──────────▼───────┐        ┌──────────────┐
│  FastAPI API server    │◄──────►│  PostgreSQL  │  all state: users, projects,
│  (any number of        │        │  + pgvector  │  tasks, messages, artifacts,
│   replicas)            │        └──────────────┘  reviews, llm_calls, memories
└─────┬──────────▲───────┘
      │ enqueue  │ pub/sub
┌─────▼──────────┴───────┐
│        Redis 7         │  ARQ task queue · pub/sub event bus · rate limiter
└─────┬──────────────────┘
      │ jobs
┌─────▼──────────────────┐        ┌──────────────┐
│  ARQ worker            │───────►│ LLM providers │  OpenAI / Anthropic / Gemini /
│  (runs agent tasks,    │        └──────────────┘  Ollama / built-in Mock
│   horizontally scales) │
└────────────────────────┘
```

- The **API server** handles HTTP + WebSocket. It never runs agents itself (except in
  standalone mode) — it enqueues jobs.
- The **worker** pulls jobs from Redis and runs the orchestrator: it executes agent
  tasks, which call LLMs, produce structured output, and write results to Postgres.
- **Redis** decouples them (queue) and connects them back (pub/sub): when the worker
  finishes a task, it publishes an event; every API replica forwards it to its
  connected WebSocket clients. This is why the system scales horizontally.
- **Postgres** is the single source of truth. Redis holds nothing durable.

## 3. Clean architecture — how the backend is organized

The backend follows Clean Architecture: four layers, dependencies point **inward only**.

```
presentation  →  application  →  domain  ←  infrastructure
```

| Layer | Directory | Contains | May import |
|---|---|---|---|
| **Domain** | `backend/app/domain/` | Entities (dataclasses: `Project`, `Task`, `Artifact`…), value objects (`Budget`, `Verdict`, enums), policies (`RevisionLoopPolicy`, `BudgetPolicy`…), and **ports** (abstract interfaces: `LLMGateway`, `TaskQueue`, `EventBus`, repositories) | nothing but stdlib |
| **Application** | `backend/app/application/` | The orchestrator, the workflow DAG, and services (`ProjectService`, `AuthService`, `ArtifactService`, `MemoryService`, `NotificationService`, `AnalyticsService`) — the use-cases | domain |
| **Infrastructure** | `backend/app/infrastructure/` | Implementations of the ports: SQLAlchemy models/repositories, Redis queue/bus/rate-limiter, LLM provider adapters, pgvector store, static validators | domain (implements its ports) |
| **Presentation** | `backend/app/presentation/` | FastAPI routers, WebSocket hub, middleware, request/response schemas | application + domain |

Why it matters here concretely:

- The orchestrator depends on `TaskQueue` and `EventBus` **interfaces** — so tests
  swap in in-memory fakes, and standalone mode swaps in an inline queue, without
  touching orchestrator code.
- Domain entities are plain dataclasses with no SQLAlchemy — mappers in
  `infrastructure/db/mappers.py` translate rows ↔ entities. Business rules
  (`BudgetPolicy.can_spend`, `RevisionLoopPolicy.can_request_revision`) are pure
  functions, trivially unit-testable.
- Cross-cutting pieces live in `backend/app/core/`: Pydantic Settings config, structlog
  logging with correlation IDs, the typed error hierarchy, JWT/bcrypt helpers, and
  Prometheus metric definitions.

## 4. The life of a project — from prompt to ZIP

This is the core narrative of the system. Follow one project end to end:

**① Register / login** — `POST /api/v1/auth/register` then `/auth/login`
(`presentation/api/auth.py` → `AuthService`). The user gets a 15-minute JWT access
token and a 7-day refresh token (rotated on every use).

**② Create the project** — `POST /api/v1/projects` with `{name, prompt}`
(`presentation/api/projects.py`). `ProjectService.create` inserts a `projects` row
(status `pending`, default 2M token budget), the transaction commits, and the API
enqueues a `start_workflow` job. The HTTP response returns immediately — everything
else is async.

**③ The workflow starts** — the worker picks up the job and calls
`Orchestrator.start_workflow` (`application/orchestration/orchestrator.py`). It:
- builds the standard **DAG** of 13 nodes (`templates.py`), validates it (Kahn's
  algorithm — no cycles), and stores it as JSON on a new `workflows` row;
- creates one `tasks` row per node with dependency links;
- stamps a deadline (`now + 60 min`), sets the project `in_progress`,
- writes a "Kickoff" system message, publishes a `workflow.updated` event,
- and calls `_advance`.

**④ `_advance` — the scheduling heartbeat.** This method re-scans the DAG every time
anything finishes: for each node not yet satisfied, if all its input nodes are
satisfied, its task is marked `queued` and enqueued. The first pass enqueues only
`vision` (the CEO). Later passes enqueue `design` and `database_impl` *in parallel*,
then the three engineers in parallel, and so on. `_advance` is also where completion
("every node satisfied → project `completed`") and timeout are detected.

**⑤ An agent runs a task** — the worker calls `Orchestrator.run_agent_task`:
1. **Claim** — `try_mark_running` flips the task `queued → running` atomically; if
   another delivery already claimed it, this one exits (idempotency under ARQ
   re-delivery).
2. **Assemble context** — upstream outputs (the architect gets the PRD; engineers
   get architecture + design), tier-2 project memories, tier-3 semantic recall hits,
   and revision feedback if this is a revision round.
3. **Build the prompt** — `agents/prompt_builder.py` composes system + user messages
   with per-section token caps, so prompt size is O(1) no matter how big the project
   history grows.
4. **Call the LLM** — through the gateway (§9): budget check → circuit breaker →
   provider adapter → retries with backoff.
5. **Validate the output** — the response must be a single JSON object matching the
   agent's Pydantic schema (`agents/schemas.py`). Malformed output triggers a
   *repair loop*: the validation errors are appended and the model re-prompted, max
   2 repairs (3 attempts total).

**⑥ Completion side-effects** — `_complete_task` persists everything in one
transaction: the task's structured `output`; a human-readable conversation message
(`humanize_output` turns JSON into chat text); any emitted `files[]` through the
artifact service (§12); any `decisions[]` into project memory (§8); a `reviews` row
if the output is a verdict; and an embedding job for semantic memory. Then it
publishes `task.updated` + `messages.changed` events and calls `_advance` again.

**⑦ Gates** — `qa_review`, `security_review`, and `final_approval` are gate nodes.
A gate is only "satisfied" if its verdict is `approved` (and, with human-in-the-loop
on, additionally confirmed by the user in the dashboard). A `changes_requested`
verdict routes revisions instead (§7).

**⑧ Done** — when every node is satisfied, the workflow and project flip to
`completed`, a 🎉 system message is written, and the owner gets a notification.
`GET /projects/{id}/download` streams a ZIP built from the **latest version of every
artifact**.

Meanwhile the browser saw all of it live: every event published on Redis was fanned
out over WebSocket, and the SPA invalidated the right TanStack Query caches so the
conversation feed, Kanban board, and file explorer updated in real time.

## 5. The agents — what an "AI employee" actually is

An agent = **a YAML config + a shared runtime.**

Each of the 13 YAML files in `backend/app/agents/configs/` defines one employee:

```yaml
key: qa_engineer
name: "Quinn Park"
role_title: "QA Engineer"
personality: "Politely relentless. Assumes everything is broken until proven otherwise."
provider: openai          # falls back to mock if no API key is configured
model: gpt-4o
output_schema: review_verdict
temperature: 0.2
system_prompt: |
  You are Quinn Park, QA Engineer... issue a structured verdict; route problems
  to the responsible node via target_node.
```

On startup, `agents/registry.py::sync_agents_to_db` upserts every YAML into the
`agents` table (if a provider's API key isn't configured, that agent is silently
switched to the mock provider so demos never 401).

The runtime is `RoleAgent` (`agents/base.py`): build prompt → call gateway →
`extract_json` (tolerates markdown fences and prose around the JSON) → validate
against the Pydantic schema registered under `output_schema` → repair loop on
failure. Every agent uses this same loop; only the config differs. A role needing
custom behavior subclasses `RoleAgent` and registers with `@register_agent(key)` —
the registry falls back to `RoleAgent` for everyone else.

**The roster** (12 roles; the CEO has a second "final approval" persona, hence 13 configs):

| Agent | Output schema | Job |
|---|---|---|
| CEO | `ceo_vision` / `ceo_approval` | vision, success criteria; final ship/no-ship verdict |
| Product Manager | `pm_prd` | PRD: milestones, prioritized user stories, out-of-scope |
| Software Architect | `architect_output` | components, API contracts, DB design, Mermaid diagram |
| UI/UX Designer | `designer_output` | design system, wireframes, component inventory |
| Frontend Engineer | `engineer_output` | React app files |
| Backend Engineer | `engineer_output` | API implementation files |
| Database Engineer | `engineer_output` | DDL, migrations, seed data |
| DevOps Engineer | `engineer_output` | Dockerfiles, compose, CI pipeline |
| QA Engineer | `review_verdict` | reviews everything against the PRD (gate) |
| Security Engineer | `review_verdict` | security review + hardening notes (gate) |
| Technical Writer | `docs_output` | README, API reference, user guide |
| Marketing Manager | `marketing_output` | tagline, landing copy, launch plan |

Structured output is the contract that makes multi-agent collaboration reliable:
downstream agents consume upstream **JSON**, not prose, and the platform can act on
fields like `files[]`, `decisions[]`, and `verdict` mechanically.

## 6. The workflow engine — the DAG and the orchestrator

The workflow is a **directed acyclic graph** (`application/orchestration/dag.py`):
each `DAGNode` has a `key`, an `agent_key`, `inputs` (node keys whose outputs feed its
prompt), a `stage` label, and an `is_gate` flag. `validate()` rejects unknown
dependencies and cycles (Kahn's algorithm). The graph is serialized to JSON on the
workflow row, so a running workflow is self-contained — the template can evolve
without breaking in-flight projects.

The standard template (`templates.py`):

```
vision → prd → architecture → { design ∥ database_impl }
       → { frontend_impl ∥ backend_impl ∥ devops_impl }
       → qa_review ✅ → security_review ✅ → docs → marketing → final_approval ✅
```

The orchestrator is deliberately **stateless**: every method opens its own transaction
scope, reads current state, acts, and publishes events. There is no in-memory workflow
state anywhere — which means any worker replica can process any job, and a crashed
worker loses nothing (ARQ re-delivers; every entry point is idempotent).

Two helper concepts to know:

- `_latest_by_node` — revision rounds create *new* task rows for the same node; this
  picks the highest-round task per node, so the rest of the logic always sees the
  current attempt.
- `_node_satisfied` — completed, plus (for gates) verdict approved, plus (for
  human-in-the-loop projects) `human_approved` stamped on the output by the user's
  approval API call.

## 7. Reviews and revision loops

Gate agents return a structured verdict:

```json
{
  "verdict": "changes_requested",
  "summary": "Login endpoint missing rate limiting",
  "reasons": [
    {"severity": "high", "area": "security", "target_node": "backend_impl",
     "description": "…", "suggestion": "…"}
  ]
}
```

On rejection, `_route_revisions`:
1. checks `RevisionLoopPolicy` — if the gate has already been through 3 rounds, the
   workflow **pauses** in `needs_attention` instead (a hostile reviewer can't loop
   forever);
2. groups reasons by `target_node` (only nodes in the `REVISABLE_NODES` allowlist
   count; a rejection naming no valid node also pauses);
3. creates a **new task** for each target node at `revision_round + 1`, with the
   reviewer's feedback appended to the instructions
   (`…\n\nREVISION FEEDBACK:\n- [high] … Suggestion: …`);
4. creates a re-run of the gate itself at the new round;
5. calls `_advance`, which schedules the revision tasks.

Every verdict is also persisted as a `reviews` row, so the dashboard's task drawer can
show the full review history per round.

**Human-in-the-loop** (a per-project flag): when an agent gate passes, the workflow
pauses in `review` status and notifies the owner. Approving via
`POST /projects/{id}/approve {gate, approved: true}` stamps `human_approved` and
resumes. Rejecting with feedback synthesizes a `changes_requested` verdict from the
owner and routes it through the same revision machinery.

## 8. Agent memory — three tiers

LLMs have finite context windows; a busy project generates far more history than fits.
The memory design (`application/services/memory_service.py`) keeps prompts small and
relevant:

| Tier | What | Where | How it's kept bounded |
|---|---|---|---|
| 1 — Working | The prompt for the current task: instructions + upstream outputs + tiers 2/3 | built per-call by `prompt_builder.py` | fixed per-section token caps with truncation markers |
| 2 — Project | Key decisions each agent declared (`decisions[]` in outputs) | `project_memories` table | max 5 per task; above 60 rows, the oldest 20 are merged into one summary row |
| 3 — Semantic | Embeddings of artifacts and conversation summaries | `memory_embeddings` (pgvector; JSON+cosine fallback on SQLite) | top-5 similarity ≥ 0.75 retrieved per task |

So the working prompt is always: *task instructions + direct inputs + a bounded list
of project decisions + a handful of semantically relevant recalls* — O(1) size
regardless of project age. Embeddings are computed out-of-band (a queue job), with
OpenAI embeddings in production or a deterministic hash-based embedding offline.

## 9. The LLM gateway

Nothing in the system talks to a model except through `DefaultLLMGateway`
(`infrastructure/llm/gateway.py`), which implements the domain port and layers on:

- **Provider adapters** — `openai`, `anthropic`, `gemini`, `ollama`, `mock`, each a
  small class implementing `complete` / `stream` / `embed`, self-registered via
  `@register_provider`. Provider/model is chosen **per agent** in YAML.
- **Budget enforcement** — before every call, the project's `tokens_used` vs
  `token_budget`; over budget raises `BudgetExceededError`, which pauses the workflow.
- **Retries** — up to 3 attempts on timeouts / retryable HTTP statuses
  (408/429/5xx), exponential backoff with **full jitter**.
- **Circuit breaker** (`circuit_breaker.py`) — 5 consecutive failures opens the
  circuit per provider; calls fail fast for 60 s, then one half-open probe decides
  whether to close it. Protects against burning retries into a provider outage.
- **Accounting** — every call (success or failure) becomes an `llm_calls` row:
  provider, model, prompt/completion tokens, computed cost (`pricing.py`), latency,
  and attribution (project/task/agent/correlation id). Token/cost totals also
  increment on the project row and Prometheus counters.

**The mock provider** deserves a mention: it returns canned-but-plausible structured
outputs keyed on the `OUTPUT_SCHEMA:` line the prompt builder embeds. That one design
decision makes the entire platform runnable with zero API keys — demos, CI, the
integration test suite, and standalone mode all exercise the *real* orchestrator,
queue, and artifact pipeline against fake model output.

## 10. Safety systems — why nothing runs forever

Every failure mode has an enumerated handler; every loop has a cap. When a cap trips,
the workflow moves to **`needs_attention`**, a system message explains why, the owner
gets a notification, and the dashboard offers Resume (optionally with a raised budget)
or Cancel.

| Failure / loop | Handling | Where |
|---|---|---|
| LLM timeout / 5xx / connection error | 3 retries, backoff+jitter; then task failure | gateway |
| Provider outage | circuit breaker: fail fast, half-open probe after 60 s | `circuit_breaker.py` |
| Malformed structured output | re-prompt with validation errors, max 2 repairs | `RoleAgent.execute` |
| Task failure (any exception) | task retried (max 2), then **dead-letter** + pause | `_handle_task_failure` |
| Reviewer rejects repeatedly | max 3 revision rounds per gate, then pause | `_route_revisions` |
| Token budget exhausted | checked *before* each call; pause | gateway `_check_budget` |
| Workflow runs too long | 60-min deadline checked on every `_advance`; pause | `WorkflowTimeoutPolicy` |
| Worker crash mid-task | ARQ re-delivers; `try_mark_running` claim + idempotent entry points | orchestrator |
| Queue flooding of one user | Redis sliding-window rate limits on auth + project creation | `rate_limiter.py` |

Resume (`POST /projects/{id}/resume`) re-queues dead-lettered tasks with reset
attempt counters and re-enters the normal scheduling loop.

## 11. The data model

Thirteen tables (see `docs/database-schema.md` for every column/index). The ones that
carry the design:

- **`projects`** — prompt, status, `token_budget` / `tokens_used` / `cost_usd`,
  `human_in_loop`, per-project settings JSON.
- **`workflows`** — 1:1 with project; the serialized DAG, current stage, deadline,
  `paused_reason`.
- **`tasks`** — one per DAG node **per revision round**
  (unique `(workflow_id, node_key, revision_round)`); status, attempt count,
  structured `output` JSON, error text; `task_dependencies` join table.
- **`agent_messages`** — the company chat: sender/recipient agents, type (assignment /
  result / review / revision_request / status / system), a global `seq` for stable
  ordering, correlation id, payload JSON.
- **`artifacts`** + **`artifact_versions`** — see §12.
- **`reviews`** — verdicts with `reasons` JSON and round number.
- **`project_memories`** / **`memory_embeddings`** — memory tiers 2 and 3.
- **`llm_calls`** — the cost ledger; powers per-agent analytics.
- **`users`** / **`refresh_tokens`** / **`notifications`** — auth + notify.

Statuses are enforced with CHECK constraints; everything is UUID-keyed; timestamps are
timezone-aware (a custom `TZDateTime` type keeps SQLite honest in tests).

## 12. Artifacts — how generated code is stored

Agents emit files as structured JSON: `{path, content, language}`. The artifact
service (`application/services/artifact_service.py`) processes each file:

1. **Hash** — SHA-256 of the content. If it matches the current latest version,
   nothing is written (no version-spam when an agent re-emits identical files).
2. **Validate** — static checks only, generated code is **never executed**:
   Python → `ast.parse`; JSON/YAML → parse; TS/JS → brace-balance sanity check;
   size and binary guards. Failures don't block storage — they're recorded on the
   version and surfaced to QA and the UI (⚠ badges).
3. **Version** — an immutable `artifact_versions` row (content, hash, size,
   validation report), and the artifact's `latest_version` pointer bumps. Full
   history is retained; the API serves any historical version.
4. **Announce** — an `artifact.created` event (live file-explorer updates) and an
   embedding job for semantic memory.

`build_zip` streams the latest version of every artifact into the download ZIP.

## 13. Real-time — WebSockets and the event bus

- **Publish** — everything interesting publishes to Redis pub/sub via the `EventBus`
  port: `task.updated`, `workflow.updated`, `messages.changed`, `artifact.created`,
  `notification`. Channels are `events:{project_id}` and `events:user:{user_id}`.
- **Connect** — the SPA opens `WS /ws?token=<JWT>`. The server authenticates
  **before** accepting, then subscribes the socket to the user's channel.
- **Subscribe** — the client sends `{action: "subscribe", project_id}`; the server
  checks ownership, then bridges that project's Redis channel onto the socket.
- **Consume** — `frontend/src/ws/useProjectSocket.ts` maps event types to TanStack
  Query cache invalidations (e.g. `task.updated` → refetch that project's tasks).
  The REST responses stay the single source of truth; events are just "something
  changed" nudges — which makes the UI naturally self-healing (polling fallbacks
  exist on every query).

Because fan-out goes through Redis, any API replica can serve any client no matter
which worker produced the event.

## 14. Authentication and security

- **Passwords** — bcrypt with per-password salt.
- **Access tokens** — 15-minute JWTs (HS256) carrying `sub` (user id) and `role`.
- **Refresh tokens** — opaque 48-byte random strings, stored **hashed** (SHA-256),
  7-day expiry, **rotated on every use** — a replayed old token is rejected. Logout
  revokes. The frontend client auto-refreshes on 401 and replays the failed request.
- **RBAC** — `member` sees own projects; `admin` sees all (`ProjectService` scoping +
  `require_admin` dependency).
- **Rate limiting** — Redis sliding-window on auth endpoints (per IP) and project
  creation (per user).
- **Transport hygiene** — strict CORS allowlist; security headers
  (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`); Pydantic validation on every request body/query.
- **Generated code is never executed** — static validation only (§12).
- **Errors** — a typed hierarchy (`core/errors.py`) maps every failure to a stable
  envelope: `{"error": {"code", "message", "details", "correlation_id"}}` — the
  frontend switches on `code`, and `correlation_id` links the response to the logs.

## 15. Observability — logs and metrics

- **Logging** — structlog, JSON lines. A middleware assigns each request a
  **correlation id** (honoring an incoming `X-Correlation-Id`), stores it in a
  contextvar, returns it in the response, and stamps it on every log line. Agent
  task runs get their own correlation ids stitched through messages and LLM calls.
- **Metrics** — Prometheus at `/metrics`: HTTP request counts/latency by route,
  LLM calls/tokens/cost by provider·model·agent, agent task duration histograms,
  queue depth, WebSocket connection gauge.
- **Health** — `/health` (liveness, always ok) and `/ready` (checks DB + Redis,
  503 when degraded) for orchestrators and load balancers.

## 16. The frontend

A React 18 + TypeScript SPA (Vite), styled with Tailwind (class-based dark mode).

**State model** — two kinds of state, two tools:
- *Server state* → *TanStack Query*: every API resource is a typed hook in
  `src/api/hooks.ts` (`useProjects`, `useProjectTasks`, `useArtifact`…), with polling
  intervals as a WebSocket fallback. Mutations invalidate precisely the queries they
  affect.
- *Client state* → *Zustand*: `stores/auth.ts` (tokens + user, persisted to
  localStorage) and `stores/ui.ts` (theme).

**API client** (`src/api/client.ts`) — a small fetch wrapper: attaches the bearer
token, parses the error envelope into a typed `ApiError`, and on 401 transparently
refreshes the token (single-flight) and retries.

**Pages** — Login/Register; **Dashboard** (project grid + "start a new project" form
with example prompts and a human-in-loop toggle); **Project** (tabs: Conversation
feed, Kanban Board, Files, Timeline, Overview with the architect's Mermaid diagram and
review-gate history); **Team** (agent cards with personalities + per-agent stats);
**Analytics** (tokens/cost tiles, per-agent performance table); **Settings**.

**Live updates** — `useProjectSocket` (§13). The layout keeps one global socket for
notifications; each project page subscribes to its project channel.

## 17. Standalone dev mode — running without Docker

Set two env values and the whole platform runs in a single process with **zero
external services and zero API keys**:

```
DATABASE_URL=sqlite+aiosqlite:///./dev.db
REDIS_URL=memory://
```

`memory://` activates `infrastructure/redis/memory_backend.py`:
- **`MemoryRedis`** — an in-process stand-in implementing exactly the redis-py
  surface the app uses: `publish`/`pubsub` (so WebSockets work), a pipeline with
  sorted-set ops (so the rate limiter works), `ping` (so `/ready` works).
- **`InlineTaskQueue`** — replaces ARQ by running orchestrator jobs as asyncio
  background tasks inside the API process.
- On startup, the SQLite schema is created directly from the models
  (`ensure_sqlite_schema`) since Alembic targets Postgres.

Because both swaps happen behind the existing seams (`get_redis()`,
`get_task_queue()` — both return port implementations), **zero orchestrator,
service, or endpoint code changes**. The trade-off: single process only; multi-replica
deployments need real Redis. This works precisely because of the clean-architecture
ports — a good example to cite when explaining why the layering pays off.

## 18. Testing strategy

**Backend — 144 tests, 96% line coverage on domain + application** (`backend/tests/`):

- The suite runs on **SQLite + fakes** — no Postgres, Redis, or network. The models
  were built dual-dialect (`JSONVariant`, `TZDateTime`, SQL fallbacks) to make this
  possible.
- `conftest.py` provides `FakeEventBus` / `FakeTaskQueue` (implementing the domain
  ports) and a `drain()` helper that *plays the worker*: pop queued task ids, call
  `orchestrator.run_agent_task`, repeat. Combined with the mock LLM provider, the
  integration tests execute **complete real workflows in-process**.
- Unit tests: policies, budget math, DAG validation, JWT/bcrypt, circuit breaker
  (fake clock), static validators, JSON extraction, agent repair loop.
- Integration tests: happy path (13 tasks → completed, artifacts + messages + ledger
  verified), idempotent starts, two projects concurrently, human-in-the-loop gates,
  revision routing and recovery, revision-loop limit, dead-letter → resume →
  complete, budget exhaustion, timeout, cancellation — plus API tests for every
  router through the real ASGI app (auth rotation/replay, ownership 403s, ZIP
  download, notifications, analytics, security headers).

**Frontend — 20 Vitest + React Testing Library tests** (`frontend/src/test/`): fetch
is mocked at the network boundary (a `"METHOD /path"` routing table), so the real
hooks, query cache, and components are exercised. Covers Login, Dashboard, Kanban
(+drawer, +retry), ConversationFeed, FileExplorer, Analytics.

**E2E — 6 Playwright specs** (`frontend/e2e/`) against a running stack: the full
acceptance flow (register → create project → watch agents → completed → browse files
→ download ZIP), parallel projects, and auth journeys.

**CI-ready gates:** `ruff` + `mypy` (backend), `eslint` + `tsc` (frontend) — all clean.

## 19. How to extend the system

| You want to… | Do this |
|---|---|
| **Add an employee** | Drop a YAML in `agents/configs/` (key, personality, system_prompt, provider/model, output_schema). Registry syncs it to the DB on startup. No core changes. |
| **Give a role custom logic** | Subclass `RoleAgent`, override `build_inputs` (or `execute`), register with `@register_agent("key")`. |
| **Add a new output shape** | Pydantic model in `agents/schemas.py` with `@register_schema("name")`; reference it from the YAML. |
| **Change the workflow** | Edit `standard_workflow()` in `templates.py` — add a `DAGNode` with `inputs`; `validate()` catches mistakes. Add the node to `REVISABLE_NODES` if reviewers may route work to it. |
| **Add an LLM provider** | One adapter class in `infrastructure/llm/adapters/` implementing `complete/stream/embed`, decorated `@register_provider("name")`; add pricing in `pricing.py`. |
| **Add an API endpoint** | Router in `presentation/api/`, logic in an application service, schemas in `presentation/schemas/`. Follow the session/`CurrentUser` dependency pattern. |
| **Add a dashboard view** | Page in `frontend/src/pages/` + route in `App.tsx` + nav item in `Layout.tsx`; data via a hook in `api/hooks.ts`. |

## 20. Glossary

| Term | Meaning |
|---|---|
| **Agent / employee** | A YAML-configured persona executed by the `RoleAgent` runtime |
| **Workflow** | One run of the company DAG for one project |
| **Node** | A step in the DAG (e.g. `backend_impl`); becomes one task per revision round |
| **Gate** | A node whose structured verdict controls progress (QA, Security, CEO) |
| **Revision round** | A numbered retry of a node triggered by a gate rejection |
| **Dead letter** | A task that failed all retries; workflow pauses, manual retry possible |
| **`needs_attention`** | Paused-for-human state — any safety limit lands here |
| **Human-in-the-loop** | Per-project option: approved gates also wait for user sign-off |
| **Artifact** | A generated file; immutable versions with content hashes |
| **Verdict** | `approved` / `changes_requested` + reasons with `target_node` routing |
| **Correlation ID** | UUID linking one request/task across logs, messages, and LLM calls |
| **Standalone mode** | `REDIS_URL=memory://` + SQLite: single-process, no external services |
| **Mock provider** | Keyless deterministic LLM adapter powering demos, CI, and tests |

## 21. The 30-second and 2-minute explanations

**30 seconds.** *"It's a platform where 12 AI agents — CEO, PM, architect, engineers,
QA, security, writer, marketing — collaborate to build a software project from one
prompt. A DAG orchestrator assigns tasks over a Redis queue, agents return
schema-validated JSON through a multi-provider LLM gateway, reviewers can bounce work
back in bounded revision loops, and everything — messages, file versions, costs — is
persisted in Postgres and streamed live to a React dashboard over WebSockets. Hard
budgets, retries, timeouts, and circuit breakers guarantee no workflow ever runs
unbounded."*

**2 minutes — add these five points:**

1. **Clean architecture**: domain (entities/policies/ports) ← application
   (orchestrator/services) ← infrastructure (SQLAlchemy/Redis/LLM adapters) ←
   presentation (FastAPI/WebSockets). The ports are why tests use fakes and why the
   whole thing can also run without Docker (SQLite + an in-memory broker behind the
   same interfaces).
2. **Reliability of agent output**: agents must return JSON matching a Pydantic
   schema; malformed output triggers a bounded repair loop with the validation
   errors fed back to the model.
3. **Peer review as a first-class mechanism**: QA/Security/CEO gates return
   structured verdicts whose `target_node` routes new revision tasks to the
   responsible engineer — max 3 rounds, then the workflow pauses for a human.
4. **Memory that scales**: three tiers — a token-capped working prompt, consolidated
   per-project decisions, and pgvector semantic recall — keep prompts O(1) no matter
   how long the project runs.
5. **Proof it works**: 144 backend tests at 96% domain/application coverage run
   complete real workflows in-process on a mock provider — revision loops,
   dead-letter recovery, budget exhaustion, concurrent projects — plus 20 frontend
   component tests and 6 Playwright acceptance flows.

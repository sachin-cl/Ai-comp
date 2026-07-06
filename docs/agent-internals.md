# Agent Internals — Design Explanations

The nine mechanisms that make the AI company work. Each maps to concrete modules in
`backend/app/`.

## 1. Communication — message bus over Redis pub/sub, persisted to Postgres

Agents never call each other directly. All communication flows through the
`EventBus` port (`domain/ports/event_bus.py`), implemented by
`RedisEventBus` (`infrastructure/redis/event_bus.py`).

Publishing an agent message is a two-step, persistence-first operation:

1. **Persist** — insert into `agent_messages` with `sender_agent_id`,
   `recipient_agent_id` (NULL = broadcast), `project_id`, `task_id`,
   `correlation_id`, a monotonic `seq`, a `message_type`, human-readable `content`,
   and machine-readable `payload`.
2. **Publish** — the committed row is serialized and published to Redis channel
   `events:{project_id}`, which fans out to every API replica's WebSocket hub.

Because Postgres is written first, Redis is purely a delivery optimization: a client
that misses a pub/sub event (reconnect, replica restart) re-syncs with
`GET /projects/{id}/messages?after_seq=n`. The `correlation_id` is generated when the
orchestrator dispatches a task and threads through: assignment message → LLM call rows →
result message → review message, so an entire exchange is traceable in logs and the DB.

## 2. Memory — three tiers

Implemented in `application/services/memory_service.py` +
`infrastructure/memory/`.

- **Tier 1 — working memory** (ephemeral): the prompt assembled for the current LLM
  call: task instructions, upstream task outputs the DAG marks as inputs, and the last
  revision feedback. Never persisted as "memory" — it *is* the context window.
- **Tier 2 — project memory** (Postgres `project_memories`): after every completed
  task, the agent's structured output includes a `decisions` array (≤5 one-line bullets:
  choices made, constraints discovered). These are stored by category and injected into
  every later prompt in that project as a compact "Project decisions so far" block.
- **Tier 3 — semantic memory** (pgvector `memory_embeddings`): artifacts, verdicts, and
  key conversations are chunked (~1,000 chars), embedded, and stored. At prompt-build
  time the memory service embeds the task description and retrieves top-k (default 5,
  cosine similarity ≥ 0.75) chunks — enabling "we solved auth like this in a past
  project" recall across projects.

**Summarization strategy (keeping under the context window):** prompts are assembled by
a token-budgeted composer. Each section has a cap (system prompt: fixed; project
decisions: 1,500 tok; upstream outputs: 6,000 tok; semantic recall: 2,000 tok; revision
feedback: 1,500 tok). If a section exceeds its cap, it is reduced in order of
preference: (a) drop lowest-similarity semantic chunks, (b) replace full upstream file
contents with path + interface signatures + the agent's own summary, (c) if still over,
an *extractive summarization LLM call* (cheap model) compresses tier-2 bullets. Tier-2
itself is bounded: when a project exceeds 60 memory rows, the oldest 20 in category
'summary' are merged into one consolidated row by the same cheap model. Net effect:
prompt size is O(1) in project length, not O(n).

## 3. Task delegation — DAG orchestration over ARQ

`application/orchestration/` contains:

- `dag.py` — `WorkflowDAG`: nodes (`node_key`, `agent_key`, instruction template,
  input node list) + edges; validated acyclic at compile time (Kahn's algorithm).
- `templates.py` — the standard company workflow template (CEO → PM → Architect →
  {Designer ∥ DB Engineer} → {Frontend ∥ Backend ∥ DevOps} → QA → Security → Writer →
  Marketing → CEO approval).
- `orchestrator.py` — compiles the template into `tasks` + `task_dependencies` rows,
  then enqueues every node whose dependencies are satisfied into ARQ
  (`run_agent_task(task_id)`). When a task completes, the orchestrator's
  `on_task_completed` re-scans the DAG and enqueues all newly-unblocked nodes — parallel
  branches run concurrently across worker processes; no polling.

ARQ was chosen over Celery for native asyncio (one event loop, no thread pools around
async LLM calls). Tradeoff: smaller ecosystem, fewer ops dashboards.

## 4. Retries — three independent layers

| Layer | Where | Policy |
|---|---|---|
| LLM call | `infrastructure/llm/gateway.py` | max 3 attempts, exponential backoff `base 1s × 2^n` + full jitter, per-call timeout (default 120 s). Retries on timeout/429/5xx; **not** on 4xx auth/validation. Circuit breaker: 5 consecutive failures per provider opens circuit 60 s → calls fail fast → half-open probe. |
| Task | ARQ + `tasks.attempt` | max 2 re-deliveries (`max_tries=3` total). Exhausted → status `dead_letter`, workflow pauses `NEEDS_ATTENTION`, user notified; `POST /tasks/{id}/retry` re-enqueues manually. |
| Revision loop | `domain/policies.py` | QA/Security `changes_requested` creates a revision task for the responsible engineer, incrementing `revision_round`. `RevisionLoopPolicy` caps any (reviewer → author) pair at 3 rounds; breach → `NEEDS_ATTENTION` with the unresolved verdict attached. |

## 5. Approvals — structured verdicts + optional human gate

QA, Security, and CEO gate outputs are JSON-schema-validated
(`agents/schemas.py::ReviewVerdict`):

```json
{ "verdict": "approved" | "changes_requested",
  "summary": "…",
  "reasons": [ { "severity": "high", "area": "backend", "target_node": "backend_impl",
                 "description": "…", "suggestion": "…" } ] }
```

`changes_requested` must include ≥1 reason with a `target_node`, so the orchestrator
knows exactly which engineer gets the revision task. If the project has
`human_in_loop=true`, gate nodes transition the workflow to a paused `review` state
and emit an `approval_required` notification; `POST /projects/{id}/approve` records the
human decision and either resumes the DAG or injects the human feedback as a revision.

## 6. Failure handling — enumerated modes

| Failure | Detection | Response |
|---|---|---|
| LLM timeout / 5xx / 429 | gateway exception | retry w/ backoff (max 3) → task failure path |
| Provider outage | circuit breaker open | fail fast; task retried later; after task retries → dead-letter |
| Malformed structured output | Pydantic validation of LLM JSON | re-prompt **with the validation errors appended**, max 2 attempts, then task failure |
| Queue worker crash | ARQ job heartbeat expiry | ARQ re-delivers the job (idempotent: task row status guards double-execution) |
| Token budget exceeded | pre-call budget check in gateway | `BudgetExceededError` → workflow `NEEDS_ATTENTION` + notification; resumable with raised budget |
| Global workflow timeout | `deadline_at` checked at every orchestrator step | workflow `NEEDS_ATTENTION`, in-flight tasks finish but no new dispatch |
| Revision loop limit | `RevisionLoopPolicy` | workflow `NEEDS_ATTENTION` with unresolved verdict |
| DB unavailable | health checks, SQLAlchemy errors | request path: 503 via `/ready`; worker: task re-delivery |

Nothing loops forever: every path terminates in `completed`, `failed`, `cancelled`, or
a user-resumable `needs_attention`.

## 7. Project storage — versioned rows

`projects`, `workflows`, `tasks`, `agent_messages`, `reviews` are append-mostly rows in
Postgres (full conversation and decision history browsable in the UI). Generated code
lives in `artifacts` (one row per logical path) + `artifact_versions` (one row per
write: full content, SHA-256 `content_hash`, `version` 1..n, validation results,
authoring task). Nothing is overwritten — a revision produces version n+1 and bumps
`artifacts.latest_version`. Identical content (same hash) short-circuits to a no-op to
avoid noise versions. The ZIP download endpoint streams latest versions; any historical
version remains addressable.

## 8. Artifact generation — structured emission + static validation

Engineer agents emit `files: [{path, content, language}]` in their JSON output
(schema-validated; paths sanitized against traversal — must be relative, no `..`).
`ArtifactService.save_files()`:

1. normalizes the path, computes SHA-256;
2. runs **static validation** per language — Python: `ruff check` + `python -ast` parse;
   TS/JS: syntax parse via `esprima-python` fallback to none; JSON/YAML: parse;
   others: size/encoding checks only. Results stored in `validation` JSONB — failures
   don't block storage but are surfaced to QA (which may request changes);
3. inserts the version row, bumps `latest_version`, publishes `artifact.created`;
4. queues the content for tier-3 embedding.

Generated projects are **never executed** — sandboxed execution (Firecracker/gVisor
runner) is the documented future extension.

## 9. Extensibility — one class + one YAML

The registry (`agents/registry.py`) maps `agent_key → (AgentClass, AgentConfig)`.
Configs are YAML files in `agents/configs/`, loaded and seeded to the `agents` table at
startup. The default `RoleAgent` class covers any role whose behavior is fully described
by prompt + output schema, so most new employees need **zero Python**:

```yaml
# agents/configs/data_scientist.yaml
key: data_scientist
name: "Dr. Priya Nair"
role_title: "Data Scientist"
personality: "Methodical, loves a good baseline, allergic to unvalidated claims."
provider: anthropic
model: claude-sonnet-5
temperature: 0.3
output_schema: engineer_output        # reuse: emits files + decisions
system_prompt: |
  You are Dr. Priya Nair, Data Scientist at an AI software company. You design data
  models, analysis notebooks, and ML integration plans. You produce complete,
  runnable code files and concise decision notes. ...
```

Then either rely on auto-discovery (any YAML in `configs/` becomes a `RoleAgent`) or,
for custom behavior, subclass:

```python
@register_agent("data_scientist")
class DataScientistAgent(RoleAgent):
    async def build_context(self, task): ...   # e.g. pull dataset profiles
```

Wiring it into workflows = adding a node to a workflow template (or a project setting
that inserts the node after `backend_impl`). No orchestrator, gateway, or API changes.

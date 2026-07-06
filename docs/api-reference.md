# API Reference

Base URL: `/api/v1`. All responses are JSON. Authenticated endpoints require
`Authorization: Bearer <access_token>`. OpenAPI docs live at `/docs` (Swagger) and
`/redoc`.

## Conventions

**Error envelope** (every non-2xx):
```json
{ "error": { "code": "PROJECT_NOT_FOUND", "message": "…", "details": {}, "correlation_id": "uuid" } }
```
Common codes: `VALIDATION_ERROR` (422), `UNAUTHORIZED` (401), `FORBIDDEN` (403),
`NOT_FOUND` (404), `CONFLICT` (409), `RATE_LIMITED` (429), `BUDGET_EXCEEDED` (409),
`INTERNAL_ERROR` (500).

**Pagination**: `?limit=50&offset=0` → `{ "items": [...], "total": n, "limit": 50, "offset": 0 }`.

## Auth  (rate-limited: 10 req/min/IP)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | — | Create account |
| POST | `/auth/login` | — | Get access + refresh tokens |
| POST | `/auth/refresh` | — | Rotate refresh token, new access token |
| POST | `/auth/logout` | ✔ | Revoke refresh token |
| GET | `/auth/me` | ✔ | Current user profile |

`POST /auth/register` — body `{email, password (min 8), full_name}` → 201
`{id, email, full_name, role}`. Errors: 409 `EMAIL_TAKEN`, 422.

`POST /auth/login` — body `{email, password}` → 200
`{access_token, refresh_token, token_type: "bearer", expires_in}`. Errors: 401 `INVALID_CREDENTIALS`.

`POST /auth/refresh` — body `{refresh_token}` → 200 same shape as login (old refresh
token revoked). Errors: 401 `INVALID_REFRESH_TOKEN`.

## Projects  (creation rate-limited: 5/min/user)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/projects` | ✔ | Create project from prompt; kicks off workflow |
| GET | `/projects` | ✔ | List own projects (admin: all) |
| GET | `/projects/{id}` | ✔ owner/admin | Project detail incl. workflow + budget usage |
| PATCH | `/projects/{id}` | ✔ owner/admin | Update name / settings / human_in_loop |
| POST | `/projects/{id}/cancel` | ✔ owner/admin | Cancel workflow |
| POST | `/projects/{id}/resume` | ✔ owner/admin | Resume from NEEDS_ATTENTION (optionally raise budget) |
| POST | `/projects/{id}/approve` | ✔ owner/admin | Human-in-the-loop gate approval `{gate, approved, feedback?}` |
| GET | `/projects/{id}/timeline` | ✔ | Gantt data: stages + task spans |
| GET | `/projects/{id}/download` | ✔ | ZIP of latest artifact versions |

`POST /projects` — body `{name, prompt, token_budget?, human_in_loop?, settings?}` → 201
project object; workflow starts asynchronously. Errors: 429, 422.

Project object:
```json
{ "id": "…", "name": "…", "prompt": "…", "status": "in_progress",
  "token_budget": 2000000, "tokens_used": 15230, "cost_usd": 0.4831,
  "human_in_loop": false, "workflow": { "id": "…", "status": "in_progress",
  "current_stage": "engineering", "started_at": "…", "paused_reason": null },
  "created_at": "…", "updated_at": "…" }
```

## Tasks

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/projects/{id}/tasks` | ✔ | All tasks (Kanban); filter `?status=` |
| GET | `/tasks/{id}` | ✔ | Task detail incl. output, reviews, dependencies |
| POST | `/tasks/{id}/retry` | ✔ owner/admin | Re-enqueue a failed / dead-letter task |

## Conversations

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/projects/{id}/messages` | ✔ | Paginated agent messages; `?after_seq=` for gap re-sync |
| GET | `/tasks/{id}/messages` | ✔ | Messages scoped to one task |

## Artifacts

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/projects/{id}/artifacts` | ✔ | File tree (path, language, latest_version, size) |
| GET | `/artifacts/{id}` | ✔ | Latest version content + validation results |
| GET | `/artifacts/{id}/versions` | ✔ | Version history |
| GET | `/artifacts/{id}/versions/{n}` | ✔ | Specific version content |

## Agents & analytics

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/agents` | ✔ | Roster: key, name, role, personality, provider, model, status |
| GET | `/agents/{key}/stats` | ✔ | tasks_completed, revision_rate, avg_tokens, avg_latency_ms |
| GET | `/analytics/overview` | ✔ | Company-wide: projects by status, tokens/cost over time, per-agent table |

## Notifications

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/notifications` | ✔ | Own notifications, `?unread=true` |
| POST | `/notifications/{id}/read` | ✔ | Mark read |
| POST | `/notifications/read-all` | ✔ | Mark all read |

## Ops (no auth)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | liveness `{"status":"ok"}` |
| GET | `/ready` | readiness — pings Postgres + Redis |
| GET | `/metrics` | Prometheus exposition |

## WebSocket

`GET /ws?token=<access_token>` → upgrades; then client sends
`{"action":"subscribe","project_id":"…"}` (multiple allowed) or `{"action":"unsubscribe",…}`.

Server events (all carry `project_id`, `seq`, `ts`):

| type | payload |
|---|---|
| `agent.message` | full agent_message row |
| `task.updated` | `{task_id, node_key, status, agent_key, revision_round}` |
| `workflow.updated` | `{status, current_stage, paused_reason?}` |
| `artifact.created` | `{artifact_id, path, version, language}` |
| `notification` | notification row (sent on `events:user:{id}`) |
| `budget.updated` | `{tokens_used, cost_usd, token_budget}` |

Auth failure closes with code 4401; unknown project subscription → `{"type":"error","code":"FORBIDDEN"}`.

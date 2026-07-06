# AI Software Company

A production-grade multi-agent platform where a team of 12 specialized AI employees —
CEO, PM, Architect, Designer, Engineers, QA, Security, Writer, Marketing — collaborates
to build software projects from a single prompt. You manage the company from a
real-time dashboard: watch agents discuss, review each other, iterate, and deliver a
complete versioned project you can download.

> Status: under active construction. See [docs/](docs/) for the full design.

## Documentation

- [System architecture](docs/architecture.md)
- [Database schema](docs/database-schema.md)
- [API reference](docs/api-reference.md)
- [Agent internals (communication, memory, delegation, retries, approvals, failure handling, storage, artifacts, extensibility)](docs/agent-internals.md)

## Stack

Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 (async) · Alembic · ARQ ·
PostgreSQL 16 + pgvector · Redis 7 · React 18 · TypeScript 5 · Vite · TanStack Query ·
Zustand · Tailwind CSS · Docker Compose · GitHub Actions

## Quick start

```bash
cp .env.example .env       # add at least one LLM provider API key
docker compose up --build
# dashboard: http://localhost:5173   api docs: http://localhost:8000/docs
```

Full setup, deployment guide, and runbook land with the Docker/CI phase.

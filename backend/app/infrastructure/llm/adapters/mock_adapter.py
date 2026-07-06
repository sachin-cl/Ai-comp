"""Deterministic mock provider.

Lets the entire platform run end-to-end with zero API keys: `docker compose up`,
demos, CI, and e2e tests exercise the real orchestrator, queue, WebSockets, and
artifact pipeline against canned-but-plausible agent outputs.

The agent prompt builder embeds a line `OUTPUT_SCHEMA: <key>`; this adapter keys its
response on that. Unknown schema → generic prose.
"""
import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from app.domain.ports.llm_gateway import ChatMessage, LLMResult
from app.domain.value_objects import TokenUsage
from app.infrastructure.llm.base import ProviderAdapter, register_provider


def _extract(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else default


def _project_hint(all_text: str) -> str:
    return _extract(r"USER REQUEST:\s*(.+)", all_text, "the requested application")[:120]


def _payload_for(schema: str, all_text: str) -> dict[str, Any]:
    hint = _project_hint(all_text)
    decisions = [f"Scoped MVP for: {hint}", "Chose React SPA + FastAPI JSON API"]
    if schema == "ceo_vision":
        return {
            "vision": f"Deliver a focused, delightful MVP for '{hint}' that a small team "
            "can ship and iterate on quickly.",
            "target_users": ["early adopters", "small teams"],
            "success_criteria": ["core flow works end-to-end", "clean, responsive UI",
                                 "documented setup under 10 minutes"],
            "constraints": ["MVP scope only", "web app, no native mobile"],
            "decisions": decisions,
        }
    if schema == "pm_prd":
        return {
            "product_name": hint.title()[:60] or "MVP Product",
            "overview": f"A web application for {hint}.",
            "milestones": [
                {"name": "M1 Foundation", "description": "Auth, data model, skeleton UI"},
                {"name": "M2 Core flows", "description": "Primary user journeys"},
                {"name": "M3 Polish", "description": "Responsive design, docs, tests"},
            ],
            "user_stories": [
                {"id": "US-1", "story": "As a user, I can sign up and log in", "priority": "P0"},
                {"id": "US-2", "story": f"As a user, I can use the core {hint} flow",
                 "priority": "P0"},
                {"id": "US-3", "story": "As a user, I can manage my items in a dashboard",
                 "priority": "P1"},
            ],
            "out_of_scope": ["payments", "native apps"],
            "decisions": decisions,
        }
    if schema == "architect_output":
        return {
            "architecture_overview": "Classic three-tier web app: React SPA talking to a "
            "FastAPI JSON API backed by PostgreSQL.",
            "components": [
                {"name": "frontend", "tech": "React + Vite", "responsibility": "UI"},
                {"name": "api", "tech": "FastAPI", "responsibility": "business logic + auth"},
                {"name": "db", "tech": "PostgreSQL", "responsibility": "persistence"},
            ],
            "api_contracts": [
                {"method": "POST", "path": "/api/auth/login", "description": "JWT login"},
                {"method": "GET", "path": "/api/items", "description": "List items"},
                {"method": "POST", "path": "/api/items", "description": "Create item"},
            ],
            "db_design": [
                {"table": "users", "columns": ["id", "email", "password_hash", "created_at"]},
                {"table": "items", "columns": ["id", "user_id", "title", "data", "created_at"]},
            ],
            "mermaid_diagram": "flowchart LR\n  SPA[React SPA] --> API[FastAPI]\n  "
            "API --> DB[(PostgreSQL)]",
            "decisions": decisions,
        }
    if schema == "designer_output":
        return {
            "design_system": {
                "colors": {"primary": "#6366f1", "surface": "#0f172a", "accent": "#22d3ee"},
                "typography": "Inter, system-ui",
                "spacing_scale": [4, 8, 12, 16, 24, 32],
            },
            "wireframes": [
                {"screen": "Login", "layout": "Centered card with email/password form"},
                {"screen": "Dashboard", "layout": "Sidebar nav, stat cards, item list"},
                {"screen": "Detail", "layout": "Two-column: content + metadata panel"},
            ],
            "components": ["Button", "Input", "Card", "Modal", "Table", "Toast"],
            "decisions": ["Dark-first responsive design, 8pt spacing grid"],
        }
    if schema == "engineer_output":
        role = _extract(r"OUTPUT_ROLE:\s*(\w+)", all_text, "backend")
        files = {
            "frontend": [
                {"path": "frontend/src/App.tsx", "language": "typescript",
                 "content": "export default function App() {\n  return <main className=\"p-8\">"
                            f"<h1>{hint}</h1></main>;\n}}\n"},
                {"path": "frontend/src/main.tsx", "language": "typescript",
                 "content": "import React from 'react';\nimport {createRoot} from "
                            "'react-dom/client';\nimport App from './App';\n\n"
                            "createRoot(document.getElementById('root')!).render(<App />);\n"},
                {"path": "frontend/index.html", "language": "html",
                 "content": f"<!doctype html>\n<html><head><title>{hint}</title></head>"
                            "<body><div id=\"root\"></div>"
                            "<script type=\"module\" src=\"/src/main.tsx\"></script>"
                            "</body></html>\n"},
            ],
            "backend": [
                {"path": "backend/main.py", "language": "python",
                 "content": "from fastapi import FastAPI\n\napp = FastAPI(title="
                            f"{json.dumps(hint)})\n\n\n@app.get('/health')\n"
                            "def health() -> dict[str, str]:\n    return {'status': 'ok'}\n"},
                {"path": "backend/models.py", "language": "python",
                 "content": "from pydantic import BaseModel\n\n\nclass Item(BaseModel):\n"
                            "    id: int\n    title: str\n"},
                {"path": "backend/requirements.txt", "language": "text",
                 "content": "fastapi\nuvicorn\npydantic\n"},
            ],
            "database": [
                {"path": "db/schema.sql", "language": "sql",
                 "content": "CREATE TABLE users (\n  id SERIAL PRIMARY KEY,\n  email TEXT "
                            "UNIQUE NOT NULL,\n  password_hash TEXT NOT NULL\n);\n\n"
                            "CREATE TABLE items (\n  id SERIAL PRIMARY KEY,\n  user_id INT "
                            "REFERENCES users(id),\n  title TEXT NOT NULL\n);\n"},
            ],
            "devops": [
                {"path": "Dockerfile", "language": "dockerfile",
                 "content": "FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\n"
                            "RUN pip install -r backend/requirements.txt\n"
                            "CMD [\"uvicorn\", \"backend.main:app\", \"--host\", \"0.0.0.0\"]\n"},
                {"path": ".github/workflows/ci.yml", "language": "yaml",
                 "content": "name: ci\non: [push]\njobs:\n  test:\n    runs-on: "
                            "ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"},
            ],
            "qa": [
                {"path": "tests/test_health.py", "language": "python",
                 "content": "def test_health():\n    assert True\n"},
            ],
        }
        return {
            "summary": f"Implemented {role} slice for {hint}.",
            "files": files.get(role, files["backend"]),
            "notes": ["Static skeleton generated by mock provider"],
            "decisions": decisions,
        }
    if schema == "review_verdict":
        return {
            "verdict": "approved",
            "summary": "Meets requirements; static checks pass; no blocking issues found.",
            "reasons": [],
        }
    if schema == "docs_output":
        return {
            "summary": "Wrote project documentation.",
            "files": [
                {"path": "README.md", "language": "markdown",
                 "content": f"# {hint.title()}\n\nGenerated by the AI Software Company.\n\n"
                            "## Setup\n\n1. `pip install -r backend/requirements.txt`\n"
                            "2. `uvicorn backend.main:app`\n"},
                {"path": "docs/api.md", "language": "markdown",
                 "content": "# API\n\n- `GET /health` — liveness probe\n"},
            ],
            "decisions": [],
        }
    if schema == "marketing_output":
        return {
            "tagline": f"{hint.title()} — shipped by your AI software company.",
            "product_description": f"An MVP for {hint}, built collaboratively by AI agents.",
            "landing_copy": {
                "hero": f"Meet {hint.title()}",
                "subhero": "From one prompt to a working product.",
                "cta": "Get started",
            },
            "launch_plan": ["Soft launch to early users", "Collect feedback", "Iterate weekly"],
            "decisions": [],
        }
    if schema == "ceo_approval":
        return {
            "verdict": "approved",
            "summary": "Deliverables align with the vision. Ship it.",
            "reasons": [],
        }
    return {"summary": f"Completed work for {hint}.", "decisions": decisions}


@register_provider("mock")
class MockAdapter(ProviderAdapter):
    name = "mock"

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float,
        json_mode: bool = False,
    ) -> LLMResult:
        start = time.perf_counter()
        await asyncio.sleep(0.35)  # feel like a real agent thinking, keep demos watchable
        all_text = "\n".join(m.content for m in messages)
        schema = _extract(r"OUTPUT_SCHEMA:\s*(\w+)", all_text, "")
        payload = _payload_for(schema, all_text)
        text = json.dumps(payload, indent=2)
        prompt_tokens = max(len(all_text) // 4, 1)
        completion_tokens = max(len(text) // 4, 1)
        return LLMResult(
            text=text,
            usage=TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
            model=model,
            provider=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> AsyncIterator[LLMResult | str]:
        result = await self.complete(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        chunk_size = 48
        for i in range(0, len(result.text), chunk_size):
            await asyncio.sleep(0.02)
            yield result.text[i : i + chunk_size]
        yield result

    async def embed(self, texts: list[str], *, model: str, timeout: float) -> list[list[float]]:
        from app.infrastructure.memory.embedder import hash_embedding

        return [hash_embedding(t) for t in texts]

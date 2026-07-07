"""Shared fixtures: SQLite database, fake Redis ports, orchestrator, API client.

Environment is pinned BEFORE any app import so get_settings() (lru_cached) sees it.
"""
import os
import tempfile
import uuid

_TEST_DB = os.path.join(
    tempfile.gettempdir(), f"aicompany-test-{os.getpid()}.db"
).replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB}"
os.environ["REDIS_URL"] = "redis://localhost:63790/0"  # never actually contacted
os.environ["DEFAULT_LLM_PROVIDER"] = "mock"
os.environ["DEFAULT_LLM_MODEL"] = "mock-small"
os.environ["EMBEDDING_PROVIDER"] = "hash"
os.environ["SECRET_KEY"] = "test-secret-key-0123456789-abcdefghijklmnop"
os.environ["ENVIRONMENT"] = "test"

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.domain.entities import Project, User  # noqa: E402
from app.domain.ports.event_bus import EventBus  # noqa: E402
from app.domain.ports.task_queue import TaskQueue  # noqa: E402
from app.domain.value_objects import UserRole  # noqa: E402


class FakeEventBus(EventBus):
    """Records every published event for assertions."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    async def publish_project_event(self, project_id, event_type, payload):
        self.events.append((str(project_id), event_type, payload))

    async def publish_user_event(self, user_id, event_type, payload):
        self.events.append((f"user:{user_id}", event_type, payload))

    async def subscribe(self, channels):
        return
        yield  # pragma: no cover

    def types(self) -> list[str]:
        return [t for _, t, _ in self.events]


class FakeTaskQueue(TaskQueue):
    """Collects enqueued work so tests can drive the worker loop themselves."""

    def __init__(self) -> None:
        self.agent_tasks: list[uuid.UUID] = []
        self.workflow_starts: list[uuid.UUID] = []
        self.embeddings: list[tuple] = []

    async def enqueue_agent_task(self, task_id):
        self.agent_tasks.append(task_id)

    async def enqueue_workflow_start(self, project_id):
        self.workflow_starts.append(project_id)

    async def enqueue_embedding(self, project_id, kind, ref_id, content):
        self.embeddings.append((project_id, kind, ref_id, content))

    async def queue_depth(self):
        return len(self.agent_tasks)


@pytest.fixture(autouse=True)
def _fast_mock_llm(monkeypatch):
    """Strip the mock adapter's demo-pacing sleeps so workflows run instantly."""
    from types import SimpleNamespace

    import app.infrastructure.llm.adapters.mock_adapter as mock_mod

    async def instant(*_args, **_kwargs):
        return None

    monkeypatch.setattr(mock_mod, "asyncio", SimpleNamespace(sleep=instant))


@pytest.fixture
async def db():
    """Fresh schema per test on a file-backed SQLite DB; engine disposed after."""
    from app.infrastructure.db.engine import dispose_engine, get_engine
    from app.infrastructure.db.models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()


@pytest.fixture
def fake_bus():
    return FakeEventBus()


@pytest.fixture
def fake_queue():
    return FakeTaskQueue()


@pytest.fixture
def orchestrator(db, fake_bus, fake_queue):
    from app.application.orchestration.orchestrator import Orchestrator

    orch = Orchestrator()
    orch.event_bus = fake_bus
    orch.queue = fake_queue
    return orch


@pytest.fixture
async def seeded_agents(db):
    from app.agents.registry import sync_agents_to_db

    await sync_agents_to_db()


@pytest.fixture
def make_user(db):
    async def _make(email: str = "owner@example.com", role: UserRole = UserRole.MEMBER) -> User:
        from app.infrastructure.db.engine import session_scope
        from app.infrastructure.db.repositories import SqlUserRepository

        async with session_scope() as session:
            return await SqlUserRepository(session).add(
                User(
                    id=uuid.uuid4(),
                    email=email,
                    password_hash=hash_password("password123"),
                    full_name="Test User",
                    role=role,
                )
            )

    return _make


@pytest.fixture
def make_project(db):
    async def _make(owner: User, **overrides) -> Project:
        from app.infrastructure.db.engine import session_scope
        from app.infrastructure.db.repositories import SqlProjectRepository

        defaults: dict = {
            "id": uuid.uuid4(),
            "owner_id": owner.id,
            "name": "Test Project",
            "prompt": "Build an expense tracker",
        }
        defaults.update(overrides)
        async with session_scope() as session:
            return await SqlProjectRepository(session).add(Project(**defaults))

    return _make


async def drain(orchestrator, queue: FakeTaskQueue, max_steps: int = 300) -> int:
    """Play the ARQ worker: pop and run queued agent tasks until the queue is idle."""
    steps = 0
    while queue.agent_tasks and steps < max_steps:
        task_id = queue.agent_tasks.pop(0)
        await orchestrator.run_agent_task(task_id)
        steps += 1
    assert steps < max_steps, "queue never drained — runaway workflow?"
    return steps


@pytest.fixture
async def client(db, fake_bus, fake_queue, monkeypatch):
    """httpx client against the real ASGI app with Redis-touching seams faked out."""

    async def no_rate_limit(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.presentation.api.auth.enforce_rate_limit", no_rate_limit)
    monkeypatch.setattr("app.presentation.api.projects.enforce_rate_limit", no_rate_limit)
    monkeypatch.setattr("app.presentation.api.projects.get_task_queue", lambda: fake_queue)
    monkeypatch.setattr("app.presentation.api.projects.get_event_bus", lambda: fake_bus)
    monkeypatch.setattr("app.presentation.api.tasks.get_task_queue", lambda: fake_queue)

    import app.application.orchestration.orchestrator as orch_mod

    orch = orch_mod.Orchestrator()
    orch.event_bus = fake_bus
    orch.queue = fake_queue
    monkeypatch.setattr(orch_mod, "_orchestrator", orch)

    from app.main import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.orchestrator = orch  # type: ignore[attr-defined]  # handy for workflow tests
        yield c


async def register_and_login(
    client: httpx.AsyncClient, email: str = "owner@example.com"
) -> dict[str, str]:
    """Register a user through the API and return Authorization headers."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "full_name": "Test User"},
    )
    res = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def auth_headers(client):
    return await register_and_login(client)

"""Seed a demo admin user and sync agents. Run inside the backend container:

    python -m scripts.seed
"""
import asyncio
import uuid

from app.agents.registry import sync_agents_to_db
from app.core.security import hash_password
from app.domain.entities import User
from app.domain.value_objects import UserRole
from app.infrastructure.db.engine import session_scope
from app.infrastructure.db.repositories import SqlUserRepository

DEMO_EMAIL = "demo@aicompany.dev"
DEMO_PASSWORD = "demo1234"  # local demo only


async def main() -> None:
    await sync_agents_to_db()
    async with session_scope() as session:
        users = SqlUserRepository(session)
        if await users.get_by_email(DEMO_EMAIL) is None:
            await users.add(
                User(
                    id=uuid.uuid4(),
                    email=DEMO_EMAIL,
                    password_hash=hash_password(DEMO_PASSWORD),
                    full_name="Demo Admin",
                    role=UserRole.ADMIN,
                )
            )
            print(f"Created demo user {DEMO_EMAIL} / {DEMO_PASSWORD}")
        else:
            print("Demo user already exists")
    print("Agents synced.")


if __name__ == "__main__":
    asyncio.run(main())

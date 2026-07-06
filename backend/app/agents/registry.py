"""Plugin-style agent registry.

- Every YAML in agents/configs/ defines an employee; unknown keys default to RoleAgent.
- @register_agent("key") binds a custom Agent subclass to a key.
- sync_agents_to_db() seeds/updates the `agents` table at startup (API and worker).
"""
import uuid
from pathlib import Path
from typing import Any

import yaml

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.entities import AgentProfile
from app.domain.ports.llm_gateway import LLMGateway
from app.agents.base import Agent, RoleAgent

logger = get_logger("agents.registry")

CONFIG_DIR = Path(__file__).parent / "configs"

_AGENT_CLASSES: dict[str, type[Agent]] = {}


def register_agent(key: str):
    def deco(cls: type[Agent]) -> type[Agent]:
        _AGENT_CLASSES[key] = cls
        return cls

    return deco


def load_agent_configs() -> dict[str, dict[str, Any]]:
    configs: dict[str, dict[str, Any]] = {}
    for path in sorted(CONFIG_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "key" not in data:
            logger.warning("invalid_agent_config", file=str(path))
            continue
        configs[data["key"]] = data
    return configs


def profile_from_config(data: dict[str, Any]) -> AgentProfile:
    settings = get_settings()
    config = {
        "output_schema": data.get("output_schema", "engineer_output"),
        "output_role": data.get("output_role", ""),
        "temperature": data.get("temperature", 0.7),
        "max_tokens": data.get("max_tokens", 8192),
        "tools": data.get("tools", []),
    }
    return AgentProfile(
        id=uuid.uuid4(),
        key=data["key"],
        name=data.get("name", data["key"].title()),
        role_title=data.get("role_title", data["key"].replace("_", " ").title()),
        personality=data.get("personality", ""),
        system_prompt=data.get("system_prompt", ""),
        provider=data.get("provider") or settings.default_llm_provider,
        model=data.get("model") or settings.default_llm_model,
        config=config,
        is_active=bool(data.get("is_active", True)),
    )


async def sync_agents_to_db() -> None:
    """Upsert all YAML-configured agents into the agents table."""
    from app.infrastructure.db.engine import session_scope
    from app.infrastructure.db.repositories import SqlAgentRepository

    configs = load_agent_configs()
    settings = get_settings()
    async with session_scope() as session:
        repo = SqlAgentRepository(session)
        for key, data in configs.items():
            profile = profile_from_config(data)
            # If no real provider is configured, force mock so demos never 401.
            if profile.provider != "mock" and not _provider_configured(profile.provider):
                logger.info("provider_unconfigured_using_mock", agent=key,
                            wanted=profile.provider)
                profile.provider = "mock"
                profile.model = settings.default_llm_model
            await repo.upsert(profile)
    logger.info("agents_synced", count=len(configs))


def _provider_configured(provider: str) -> bool:
    settings = get_settings()
    return {
        "openai": bool(settings.openai_api_key),
        "anthropic": bool(settings.anthropic_api_key),
        "gemini": bool(settings.gemini_api_key),
        "ollama": True,  # local; reachable-or-not is a runtime concern
        "mock": True,
    }.get(provider, False)


def build_agent(profile: AgentProfile, gateway: LLMGateway) -> Agent:
    cls = _AGENT_CLASSES.get(profile.key, RoleAgent)
    return cls(profile, gateway)

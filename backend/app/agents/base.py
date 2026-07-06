"""Agent interface and the default RoleAgent runtime.

An Agent turns a Task into a schema-validated structured output using the LLM gateway.
Adding a new employee usually needs no Python at all (a YAML config is enough); custom
behavior = subclass RoleAgent and override hooks. See docs/agent-internals.md §9.
"""
import json
import re
from abc import ABC, abstractmethod
from typing import Any

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.errors import MalformedOutputError
from app.core.logging import get_logger
from app.domain.entities import AgentProfile, Task
from app.domain.ports.llm_gateway import LLMCallContext, LLMGateway
from app.agents.prompt_builder import PromptInputs, build_messages, repair_messages
from app.agents.schemas import get_schema

logger = get_logger("agents")


def extract_json(text: str) -> str:
    """Tolerate models that wrap JSON in markdown fences or prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


class Agent(ABC):
    """The interface every employee implements."""

    def __init__(self, profile: AgentProfile, gateway: LLMGateway) -> None:
        self.profile = profile
        self.gateway = gateway

    @abstractmethod
    async def execute(self, task: Task, inputs: PromptInputs) -> dict[str, Any]:
        """Run the task and return the schema-validated structured output."""
        ...


class RoleAgent(Agent):
    """Default agent: prompt → LLM → validate JSON → (repair loop) → output dict."""

    async def build_inputs(self, task: Task, inputs: PromptInputs) -> PromptInputs:
        """Hook for subclasses to enrich context before the LLM call."""
        return inputs

    async def execute(self, task: Task, inputs: PromptInputs) -> dict[str, Any]:
        settings = get_settings()
        config = self.profile.config or {}
        schema_key = config.get("output_schema", "engineer_output")
        schema = get_schema(schema_key)
        inputs.output_schema_key = schema_key
        inputs.output_role = config.get("output_role", "")
        inputs = await self.build_inputs(task, inputs)

        messages = build_messages(self.profile, inputs)
        context = LLMCallContext(
            project_id=task.project_id,
            task_id=task.id,
            agent_id=self.profile.id,
            agent_key=self.profile.key,
        )
        temperature = float(config.get("temperature", 0.7))
        max_tokens = int(config.get("max_tokens", 8192))

        last_errors = ""
        attempts = settings.structured_output_repair_attempts + 1
        for attempt in range(attempts):
            result = await self.gateway.complete(
                messages,
                provider=self.profile.provider,
                model=self.profile.model,
                context=context,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
            )
            raw = extract_json(result.text)
            try:
                parsed = schema.model_validate(json.loads(raw))
                return parsed.model_dump()
            except (json.JSONDecodeError, ValidationError) as exc:
                last_errors = str(exc)[:2_000]
                logger.warning(
                    "malformed_agent_output",
                    agent=self.profile.key,
                    task_id=str(task.id),
                    attempt=attempt,
                )
                messages = repair_messages(messages, result.text, last_errors)

        raise MalformedOutputError(
            f"Agent '{self.profile.key}' produced invalid structured output after "
            f"{attempts} attempts",
            details={"validation_errors": last_errors},
        )

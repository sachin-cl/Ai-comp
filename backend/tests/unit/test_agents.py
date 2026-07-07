"""Agent runtime: JSON extraction, schema validation, and the repair loop."""
import json
import uuid
from collections.abc import AsyncIterator

import pytest

from app.agents.base import RoleAgent, extract_json
from app.agents.prompt_builder import PromptInputs, build_messages, repair_messages
from app.agents.registry import load_agent_configs, profile_from_config
from app.core.errors import MalformedOutputError
from app.domain.entities import AgentProfile, Task
from app.domain.ports.llm_gateway import ChatMessage, LLMCallContext, LLMGateway, LLMResult
from app.domain.value_objects import TokenUsage


class ScriptedGateway(LLMGateway):
    """Returns pre-scripted completions; records how many calls were made."""

    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls = 0

    async def complete(self, messages, *, provider, model, context, temperature=0.7,
                       max_tokens=4096, json_mode=False) -> LLMResult:
        self.calls += 1
        return LLMResult(
            text=self.texts.pop(0),
            usage=TokenUsage(prompt_tokens=10, completion_tokens=10),
            model=model,
            provider=provider,
        )

    async def stream(self, messages, *, provider, model, context, temperature=0.7,
                     max_tokens=4096) -> AsyncIterator[str]:
        yield ""

    async def embed(self, texts):
        return [[0.0] * 8 for _ in texts]


def make_profile(schema: str = "review_verdict") -> AgentProfile:
    return AgentProfile(
        id=uuid.uuid4(),
        key="qa_engineer",
        name="QA",
        role_title="QA Engineer",
        personality="meticulous",
        system_prompt="You review software.",
        provider="mock",
        model="mock-small",
        config={"output_schema": schema},
    )


def make_task() -> Task:
    return Task(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        node_key="qa_review",
        title="QA review",
    )


def make_inputs() -> PromptInputs:
    return PromptInputs(
        user_request="Build an expense tracker",
        task_title="QA review",
        task_description="Review everything",
        output_schema_key="",
    )


VALID_VERDICT = json.dumps({"verdict": "approved", "summary": "ship it", "reasons": []})


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == '{"a": 1}'

    def test_markdown_fenced(self):
        assert extract_json('Here you go:\n```json\n{"a": 1}\n```\nDone.') == '{"a": 1}'

    def test_prose_wrapped(self):
        assert extract_json('Sure! {"a": {"b": 2}} hope that helps') == '{"a": {"b": 2}}'

    def test_no_json_returned_as_is(self):
        assert extract_json("no json here") == "no json here"


class TestRoleAgent:
    async def test_valid_output_first_try(self):
        gateway = ScriptedGateway([VALID_VERDICT])
        agent = RoleAgent(make_profile(), gateway)
        output = await agent.execute(make_task(), make_inputs())
        assert output["verdict"] == "approved"
        assert gateway.calls == 1

    async def test_repair_loop_recovers(self):
        gateway = ScriptedGateway(["not json at all", VALID_VERDICT])
        agent = RoleAgent(make_profile(), gateway)
        output = await agent.execute(make_task(), make_inputs())
        assert output["verdict"] == "approved"
        assert gateway.calls == 2

    async def test_gives_up_after_repair_attempts(self):
        # settings.structured_output_repair_attempts = 2 → 3 total attempts
        gateway = ScriptedGateway(["bad", "still bad", "hopeless"])
        agent = RoleAgent(make_profile(), gateway)
        with pytest.raises(MalformedOutputError):
            await agent.execute(make_task(), make_inputs())
        assert gateway.calls == 3

    async def test_schema_violation_triggers_repair(self):
        # Valid JSON but wrong shape for review_verdict (verdict is required).
        gateway = ScriptedGateway([json.dumps({"summary": "hi"}), VALID_VERDICT])
        agent = RoleAgent(make_profile(), gateway)
        output = await agent.execute(make_task(), make_inputs())
        assert output["verdict"] == "approved"
        assert gateway.calls == 2


class TestPromptBuilder:
    def test_messages_shape(self):
        messages = build_messages(make_profile(), make_inputs())
        assert [m.role for m in messages] == ["system", "user"]
        assert "OUTPUT_SCHEMA:" in messages[0].content
        assert "USER REQUEST: Build an expense tracker" in messages[1].content

    def test_upstream_outputs_capped(self):
        inputs = make_inputs()
        inputs.upstream_outputs = {"prd": {"overview": "x" * 200_000}}
        messages = build_messages(make_profile(), inputs)
        assert "…[truncated to fit context budget]" in messages[1].content

    def test_revision_feedback_included(self):
        inputs = make_inputs()
        inputs.revision_feedback = "- fix the login endpoint"
        messages = build_messages(make_profile(), inputs)
        assert "REVISION FEEDBACK" in messages[1].content

    def test_repair_messages_append_errors(self):
        original = [ChatMessage(role="system", content="s"), ChatMessage(role="user", content="u")]
        repaired = repair_messages(original, "bad output", "field required")
        assert len(repaired) == 4
        assert repaired[2].role == "assistant"
        assert "field required" in repaired[3].content


class TestRegistry:
    def test_all_twelve_employees_configured(self):
        configs = load_agent_configs()
        assert len(configs) >= 12
        expected = {
            "ceo", "product_manager", "architect", "designer", "frontend_engineer",
            "backend_engineer", "database_engineer", "devops_engineer", "qa_engineer",
            "security_engineer", "technical_writer", "marketing_manager",
        }
        assert expected <= set(configs)

    def test_profile_from_config_defaults(self):
        profile = profile_from_config({"key": "data_scientist"})
        assert profile.key == "data_scientist"
        assert profile.name == "Data_Scientist"
        assert profile.provider == "mock"  # test env default
        assert profile.config["output_schema"] == "engineer_output"


def test_llm_call_context_defaults():
    context = LLMCallContext()
    assert context.project_id is None
    assert context.agent_key == ""

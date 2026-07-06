"""Token-budgeted prompt composer (tier-1 working memory assembly).

Sections are capped; overflow is reduced in a fixed preference order so prompt size is
O(1) in project length. See docs/agent-internals.md §2.
"""
import json
from dataclasses import dataclass, field

from app.domain.entities import AgentProfile, ProjectMemory
from app.domain.ports.llm_gateway import ChatMessage
from app.domain.ports.memory_store import MemoryHit

# Rough chars-per-token heuristic; deliberately conservative.
CHARS_PER_TOKEN = 4

CAPS_TOKENS = {
    "project_memory": 1_500,
    "upstream": 6_000,
    "semantic": 2_000,
    "feedback": 1_500,
}


def _truncate(text: str, max_tokens: int) -> str:
    limit = max_tokens * CHARS_PER_TOKEN
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…[truncated to fit context budget]"


@dataclass
class PromptInputs:
    user_request: str
    task_title: str
    task_description: str
    output_schema_key: str
    output_role: str = ""
    upstream_outputs: dict[str, dict] = field(default_factory=dict)
    project_memories: list[ProjectMemory] = field(default_factory=list)
    semantic_hits: list[MemoryHit] = field(default_factory=list)
    revision_feedback: str = ""


def build_messages(profile: AgentProfile, inputs: PromptInputs) -> list[ChatMessage]:
    schema_line = (
        f"OUTPUT_SCHEMA: {inputs.output_schema_key}\n"
        + (f"OUTPUT_ROLE: {inputs.output_role}\n" if inputs.output_role else "")
    )
    system = (
        f"{profile.system_prompt.strip()}\n\n"
        f"Personality: {profile.personality.strip()}\n\n"
        "You are one employee in an AI software company. Collaborate through structured "
        "output only. Respond with a single valid JSON object matching the required "
        "schema — no markdown fences, no commentary outside the JSON.\n"
        f"{schema_line}"
    )

    parts: list[str] = [f"USER REQUEST: {inputs.user_request}"]

    if inputs.project_memories:
        bullets = "\n".join(
            f"- [{m.category.value}] {m.content}" for m in inputs.project_memories
        )
        parts.append("PROJECT DECISIONS SO FAR:\n" + _truncate(
            bullets, CAPS_TOKENS["project_memory"]))

    if inputs.upstream_outputs:
        upstream_text = "\n\n".join(
            f"### Output from {node}\n{json.dumps(output, indent=1, default=str)}"
            for node, output in inputs.upstream_outputs.items()
        )
        parts.append("UPSTREAM WORK (inputs to your task):\n" + _truncate(
            upstream_text, CAPS_TOKENS["upstream"]))

    if inputs.semantic_hits:
        recall = "\n".join(
            f"- ({hit.kind}, sim {hit.similarity:.2f}) {hit.content[:400]}"
            for hit in inputs.semantic_hits
        )
        parts.append("RELEVANT PAST KNOWLEDGE:\n" + _truncate(recall, CAPS_TOKENS["semantic"]))

    if inputs.revision_feedback:
        parts.append(
            "REVISION FEEDBACK (you MUST address every point):\n"
            + _truncate(inputs.revision_feedback, CAPS_TOKENS["feedback"])
        )

    parts.append(f"YOUR TASK — {inputs.task_title}:\n{inputs.task_description}")

    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content="\n\n".join(parts)),
    ]


def repair_messages(
    original: list[ChatMessage], bad_output: str, errors: str
) -> list[ChatMessage]:
    """Re-prompt after malformed structured output, appending the validation errors."""
    return [
        *original,
        ChatMessage(role="assistant", content=bad_output[: 8_000]),
        ChatMessage(
            role="user",
            content=(
                "Your previous response failed JSON schema validation with these errors:\n"
                f"{errors}\n\n"
                "Respond again with ONLY a corrected, complete JSON object. "
                "No markdown fences, no explanations."
            ),
        ),
    ]

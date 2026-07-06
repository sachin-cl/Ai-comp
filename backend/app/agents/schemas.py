"""JSON-schema-validated structured outputs for every agent role.

Each agent's YAML config names its `output_schema`; the runtime validates the LLM's
JSON against the matching Pydantic model and re-prompts with the validation errors on
failure (max attempts configurable).
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SCHEMAS: dict[str, type[BaseModel]] = {}


def register_schema(key: str):
    def deco(cls: type[BaseModel]) -> type[BaseModel]:
        SCHEMAS[key] = cls
        return cls

    return deco


def get_schema(key: str) -> type[BaseModel]:
    if key not in SCHEMAS:
        raise KeyError(f"Unknown output schema '{key}'. Registered: {sorted(SCHEMAS)}")
    return SCHEMAS[key]


class FileOut(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    content: str
    language: str = "text"

    @field_validator("path")
    @classmethod
    def _safe_path(cls, v: str) -> str:
        norm = v.replace("\\", "/").strip()
        if norm.startswith("/") or norm.startswith("~") or ".." in norm.split("/") or ":" in norm:
            raise ValueError("path must be relative, without '..' or drive letters")
        return norm


@register_schema("ceo_vision")
class CEOVision(BaseModel):
    vision: str
    target_users: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list, max_length=5)


class Milestone(BaseModel):
    name: str
    description: str = ""


class UserStory(BaseModel):
    id: str
    story: str
    priority: str = "P1"


@register_schema("pm_prd")
class PMPrd(BaseModel):
    product_name: str
    overview: str
    milestones: list[Milestone] = Field(default_factory=list)
    user_stories: list[UserStory] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list, max_length=5)


class Component(BaseModel):
    name: str
    tech: str = ""
    responsibility: str = ""


class ApiContract(BaseModel):
    method: str
    path: str
    description: str = ""


class TableDesign(BaseModel):
    table: str
    columns: list[str] = Field(default_factory=list)


@register_schema("architect_output")
class ArchitectOutput(BaseModel):
    architecture_overview: str
    components: list[Component] = Field(default_factory=list)
    api_contracts: list[ApiContract] = Field(default_factory=list)
    db_design: list[TableDesign] = Field(default_factory=list)
    mermaid_diagram: str = ""
    decisions: list[str] = Field(default_factory=list, max_length=5)


class Wireframe(BaseModel):
    screen: str
    layout: str = ""


@register_schema("designer_output")
class DesignerOutput(BaseModel):
    design_system: dict = Field(default_factory=dict)
    wireframes: list[Wireframe] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list, max_length=5)


@register_schema("engineer_output")
class EngineerOutput(BaseModel):
    summary: str
    files: list[FileOut] = Field(default_factory=list, min_length=1)
    notes: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list, max_length=5)


class ReviewReasonOut(BaseModel):
    severity: Literal["high", "medium", "low"] = "medium"
    area: str = ""
    target_node: str = ""
    description: str
    suggestion: str = ""


@register_schema("review_verdict")
class ReviewVerdict(BaseModel):
    verdict: Literal["approved", "changes_requested"]
    summary: str
    reasons: list[ReviewReasonOut] = Field(default_factory=list)

    @field_validator("reasons")
    @classmethod
    def _reasons_required_on_rejection(
        cls, v: list[ReviewReasonOut], info
    ) -> list[ReviewReasonOut]:
        if info.data.get("verdict") == "changes_requested" and not v:
            raise ValueError("changes_requested requires at least one reason")
        return v


@register_schema("ceo_approval")
class CEOApproval(ReviewVerdict):
    pass


@register_schema("docs_output")
class DocsOutput(BaseModel):
    summary: str
    files: list[FileOut] = Field(default_factory=list, min_length=1)
    decisions: list[str] = Field(default_factory=list, max_length=5)


@register_schema("marketing_output")
class MarketingOutput(BaseModel):
    tagline: str
    product_description: str
    landing_copy: dict = Field(default_factory=dict)
    launch_plan: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list, max_length=5)

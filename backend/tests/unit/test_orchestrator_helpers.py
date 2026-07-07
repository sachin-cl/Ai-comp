"""Pure orchestrator helpers that need no database."""
import uuid

from app.application.orchestration.orchestrator import humanize_output
from app.domain.entities import Task
from app.domain.value_objects import TaskStatus


def make_task(node_key: str, status: TaskStatus, revision_round: int = 0) -> Task:
    return Task(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        node_key=node_key,
        title=node_key,
        status=status,
        revision_round=revision_round,
    )


class TestHumanizeOutput:
    def test_vision(self):
        assert humanize_output("ceo", {"vision": "Ship a great MVP"}) == "Ship a great MVP"

    def test_verdict_with_reasons(self):
        text = humanize_output("qa_engineer", {
            "verdict": "changes_requested",
            "summary": "needs work",
            "reasons": [{"severity": "high", "description": "missing auth"}],
        })
        assert "CHANGES_REQUESTED" in text
        assert "missing auth" in text

    def test_files_listed_with_overflow(self):
        files = [{"path": f"src/file{i}.py"} for i in range(10)]
        text = humanize_output("backend_engineer", {"summary": "Done.", "files": files})
        assert "src/file0.py" in text
        assert "(+2 more)" in text

    def test_marketing(self):
        text = humanize_output("marketing_manager", {
            "tagline": "Ship faster", "product_description": "An AI company."
        })
        assert text.startswith("Ship faster")

    def test_architecture(self):
        assert humanize_output("architect", {
            "architecture_overview": "Three tiers."
        }) == "Three tiers."

    def test_wireframes(self):
        text = humanize_output("designer", {
            "wireframes": [{"screen": "Login"}, {"screen": "Dashboard"}]
        })
        assert "Login" in text and "Dashboard" in text

    def test_fallback_summary(self):
        assert humanize_output("x", {"summary": "did things"}) == "did things"
        assert humanize_output("x", {}) == "Task completed."


class TestLatestByNode:
    def test_highest_revision_wins(self):
        from app.application.orchestration.orchestrator import Orchestrator

        older = make_task("backend_impl", TaskStatus.COMPLETED, revision_round=0)
        newer = make_task("backend_impl", TaskStatus.PENDING, revision_round=1)
        latest = Orchestrator._latest_by_node(None, [older, newer])
        assert latest["backend_impl"] is newer

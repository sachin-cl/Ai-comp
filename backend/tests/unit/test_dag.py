"""Workflow DAG model: validation, cycles, serialization, standard template."""
import pytest

from app.application.orchestration.dag import DAGNode, WorkflowDAG
from app.application.orchestration.templates import (
    REVISABLE_NODES,
    STAGE_ORDER,
    standard_workflow,
)


def node(key: str, inputs: tuple[str, ...] = ()) -> DAGNode:
    return DAGNode(key=key, agent_key="ceo", title=key, instructions="", inputs=inputs)


class TestWorkflowDAG:
    def test_duplicate_key_rejected(self):
        dag = WorkflowDAG().add(node("a"))
        with pytest.raises(ValueError, match="Duplicate"):
            dag.add(node("a"))

    def test_unknown_dependency_rejected(self):
        dag = WorkflowDAG().add(node("a", inputs=("ghost",)))
        with pytest.raises(ValueError, match="unknown node"):
            dag.validate()

    def test_cycle_detected(self):
        dag = WorkflowDAG().add(node("a", inputs=("b",))).add(node("b", inputs=("a",)))
        with pytest.raises(ValueError, match="cycle"):
            dag.validate()

    def test_valid_dag_passes(self):
        dag = (
            WorkflowDAG()
            .add(node("a"))
            .add(node("b", inputs=("a",)))
            .add(node("c", inputs=("a", "b")))
        )
        dag.validate()  # no raise

    def test_round_trip_serialization(self):
        dag = WorkflowDAG().add(node("a")).add(node("b", inputs=("a",)))
        restored = WorkflowDAG.from_dict(dag.to_dict())
        assert set(restored.nodes) == {"a", "b"}
        assert restored.nodes["b"].inputs == ("a",)
        restored.validate()


class TestStandardWorkflow:
    def test_template_is_valid(self):
        dag = standard_workflow()
        dag.validate()
        assert len(dag.nodes) == 13

    def test_gates_marked(self):
        dag = standard_workflow()
        gates = {k for k, n in dag.nodes.items() if n.is_gate}
        assert gates == {"qa_review", "security_review", "final_approval"}

    def test_stages_are_known(self):
        dag = standard_workflow()
        assert {n.stage for n in dag.nodes.values()} <= set(STAGE_ORDER)

    def test_revisable_nodes_exist_in_template(self):
        dag = standard_workflow()
        assert REVISABLE_NODES <= set(dag.nodes)

    def test_engineering_nodes_run_in_parallel_branch(self):
        dag = standard_workflow()
        # Frontend and backend implementations do not depend on each other.
        assert "backend_impl" not in dag.nodes["frontend_impl"].inputs
        assert "frontend_impl" not in dag.nodes["backend_impl"].inputs

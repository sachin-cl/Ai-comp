"""Workflow DAG model + cycle validation (Kahn's algorithm)."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DAGNode:
    key: str
    agent_key: str
    title: str
    instructions: str
    inputs: tuple[str, ...] = ()  # node keys whose outputs feed this node's prompt
    stage: str = "engineering"
    is_gate: bool = False  # review/approval nodes


@dataclass
class WorkflowDAG:
    nodes: dict[str, DAGNode] = field(default_factory=dict)

    def add(self, node: DAGNode) -> "WorkflowDAG":
        if node.key in self.nodes:
            raise ValueError(f"Duplicate node key '{node.key}'")
        self.nodes[node.key] = node
        return self

    def validate(self) -> None:
        for node in self.nodes.values():
            for dep in node.inputs:
                if dep not in self.nodes:
                    raise ValueError(f"Node '{node.key}' depends on unknown node '{dep}'")
        # Kahn's algorithm: if we can't pop every node, there's a cycle.
        in_degree = {key: len(node.inputs) for key, node in self.nodes.items()}
        queue = [key for key, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            current = queue.pop()
            visited += 1
            for key, node in self.nodes.items():
                if current in node.inputs:
                    in_degree[key] -= 1
                    if in_degree[key] == 0:
                        queue.append(key)
        if visited != len(self.nodes):
            raise ValueError("Workflow DAG contains a cycle")

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "key": n.key,
                    "agent_key": n.agent_key,
                    "title": n.title,
                    "inputs": list(n.inputs),
                    "stage": n.stage,
                    "is_gate": n.is_gate,
                }
                for n in self.nodes.values()
            ]
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowDAG":
        dag = cls()
        for raw in data.get("nodes", []):
            dag.add(
                DAGNode(
                    key=raw["key"],
                    agent_key=raw["agent_key"],
                    title=raw.get("title", raw["key"]),
                    instructions=raw.get("instructions", ""),
                    inputs=tuple(raw.get("inputs", [])),
                    stage=raw.get("stage", "engineering"),
                    is_gate=bool(raw.get("is_gate", False)),
                )
            )
        return dag

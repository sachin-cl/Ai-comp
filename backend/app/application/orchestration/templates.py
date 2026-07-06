"""The standard company workflow template.

CEO → PM → Architect → {Designer ∥ DB Engineer} → {Frontend ∥ Backend ∥ DevOps}
→ QA → Security → Technical Writer → Marketing → CEO final approval.
"""
from app.application.orchestration.dag import DAGNode, WorkflowDAG

STAGE_ORDER = [
    "vision",
    "planning",
    "architecture",
    "design",
    "engineering",
    "qa",
    "security",
    "documentation",
    "marketing",
    "approval",
]


def standard_workflow() -> WorkflowDAG:
    dag = WorkflowDAG()
    dag.add(DAGNode(
        key="vision", agent_key="ceo", stage="vision",
        title="Set product vision",
        instructions="Interpret the user's request. Define the vision, target users, "
                     "success criteria, and constraints for an MVP the company can ship.",
    ))
    dag.add(DAGNode(
        key="prd", agent_key="product_manager", stage="planning", inputs=("vision",),
        title="Write the PRD",
        instructions="Turn the CEO's vision into a PRD: overview, milestones, prioritized "
                     "user stories (P0 first), and an out-of-scope list.",
    ))
    dag.add(DAGNode(
        key="architecture", agent_key="architect", stage="architecture", inputs=("prd",),
        title="Design the system architecture",
        instructions="Define components, technology choices, REST API contracts, database "
                     "table designs, and a Mermaid diagram for the product in the PRD.",
    ))
    dag.add(DAGNode(
        key="design", agent_key="designer", stage="design",
        inputs=("prd", "architecture"),
        title="Create the UX design",
        instructions="Produce the design system, wireframes for every key screen, and the "
                     "reusable component inventory.",
    ))
    dag.add(DAGNode(
        key="database_impl", agent_key="database_engineer", stage="design",
        inputs=("architecture",),
        title="Implement the database schema",
        instructions="Write complete DDL, migrations, and seed data implementing the "
                     "architect's table designs, with indexes and constraints.",
    ))
    dag.add(DAGNode(
        key="frontend_impl", agent_key="frontend_engineer", stage="engineering",
        inputs=("design", "architecture"),
        title="Implement the frontend",
        instructions="Build the React + TypeScript app implementing the wireframes and "
                     "consuming the architect's API contracts. Emit complete files.",
    ))
    dag.add(DAGNode(
        key="backend_impl", agent_key="backend_engineer", stage="engineering",
        inputs=("architecture", "database_impl"),
        title="Implement the backend",
        instructions="Build the API implementing the architect's contracts on top of the "
                     "database schema: endpoints, business logic, auth, persistence.",
    ))
    dag.add(DAGNode(
        key="devops_impl", agent_key="devops_engineer", stage="engineering",
        inputs=("architecture",),
        title="Set up Docker and CI",
        instructions="Produce Dockerfiles, docker-compose.yml, and a CI pipeline for the "
                     "generated project.",
    ))
    dag.add(DAGNode(
        key="qa_review", agent_key="qa_engineer", stage="qa", is_gate=True,
        inputs=("prd", "frontend_impl", "backend_impl", "database_impl", "devops_impl"),
        title="QA review",
        instructions="Review all delivered files against the PRD's P0 stories and the API "
                     "contracts. Issue a structured verdict; route problems to the "
                     "responsible node via target_node.",
    ))
    dag.add(DAGNode(
        key="security_review", agent_key="security_engineer", stage="security", is_gate=True,
        inputs=("qa_review", "frontend_impl", "backend_impl", "database_impl", "devops_impl"),
        title="Security review",
        instructions="Security-review the delivered files. Issue a structured verdict with "
                     "severities and hardening suggestions.",
    ))
    dag.add(DAGNode(
        key="docs", agent_key="technical_writer", stage="documentation",
        inputs=("security_review", "prd", "architecture"),
        title="Write documentation",
        instructions="Write the README, API reference, and user guide for the delivered "
                     "project.",
    ))
    dag.add(DAGNode(
        key="marketing", agent_key="marketing_manager", stage="marketing",
        inputs=("docs", "prd"),
        title="Prepare launch materials",
        instructions="Write the tagline, product description, landing page copy, and a "
                     "two-week launch plan.",
    ))
    dag.add(DAGNode(
        key="final_approval", agent_key="ceo_approval", stage="approval", is_gate=True,
        inputs=("vision", "qa_review", "security_review", "docs", "marketing"),
        title="CEO final approval",
        instructions="Compare deliverables against your vision and success criteria. "
                     "Approve to ship, or request changes with target_node set.",
    ))
    dag.validate()
    return dag


# Which engineering nodes a reviewer may route revisions to.
REVISABLE_NODES = {"frontend_impl", "backend_impl", "database_impl", "devops_impl",
                   "docs", "marketing", "design", "architecture"}

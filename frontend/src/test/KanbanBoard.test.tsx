import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import KanbanBoard from "../components/KanbanBoard";
import { makeTask, mockFetch, renderWithProviders } from "./utils";

describe("KanbanBoard", () => {
  it("groups tasks into status columns", async () => {
    mockFetch({
      "GET /projects/proj-1/tasks": [
        makeTask({ title: "Set product vision", status: "completed", node_key: "vision" }),
        makeTask({ title: "Implement the backend", status: "running" }),
        makeTask({ title: "QA review", status: "pending", node_key: "qa_review" }),
      ],
    });
    renderWithProviders(<KanbanBoard projectId="proj-1" />);

    expect(await screen.findByText("Set product vision")).toBeInTheDocument();
    const cards = screen.getAllByTestId("kanban-card");
    expect(cards).toHaveLength(3);
    expect(screen.getByText("Implement the backend")).toBeInTheDocument();
  });

  it("marks revision-round tasks", async () => {
    mockFetch({
      "GET /projects/proj-1/tasks": [
        makeTask({ title: "Implement the backend (revision 1)", revision_round: 1 }),
      ],
    });
    renderWithProviders(<KanbanBoard projectId="proj-1" />);
    expect(await screen.findByText("R1")).toBeInTheDocument();
  });

  it("opens the task drawer with details and reviews", async () => {
    const task = makeTask({
      title: "QA review",
      status: "completed",
      description: "Review all delivered files",
      output: { verdict: "approved" },
    });
    mockFetch({
      "GET /projects/proj-1/tasks": [task],
      [`GET /tasks/${task.id}`]: {
        ...task,
        reviews: [
          {
            verdict: "changes_requested",
            round: 0,
            created_at: "2026-07-07T10:00:00Z",
            reasons: [
              {
                severity: "high",
                area: "api",
                target_node: "backend_impl",
                description: "Endpoint missing",
                suggestion: "Add it",
              },
            ],
          },
        ],
      },
    });
    renderWithProviders(<KanbanBoard projectId="proj-1" />);

    await userEvent.click(await screen.findByTestId("kanban-card"));
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText("Review all delivered files")).toBeInTheDocument();
    expect(within(drawer).getByText(/Review round 0/)).toBeInTheDocument();
    expect(within(drawer).getByText("Endpoint missing")).toBeInTheDocument();
  });

  it("offers retry for dead-lettered tasks", async () => {
    const task = makeTask({ status: "dead_letter", error: "provider exploded" });
    const calls = mockFetch({
      "GET /projects/proj-1/tasks": [task],
      [`GET /tasks/${task.id}`]: task,
      [`POST /tasks/${task.id}/retry`]: { ...task, status: "queued", error: null },
    });
    renderWithProviders(<KanbanBoard projectId="proj-1" />);

    await userEvent.click(await screen.findByTestId("kanban-card"));
    await userEvent.click(await screen.findByRole("button", { name: /retry task/i }));
    expect(calls).toContainEqual({
      url: `/tasks/${task.id}/retry`,
      method: "POST",
      body: undefined,
    });
  });
});

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AnalyticsPage from "../pages/AnalyticsPage";
import { mockFetch, renderWithProviders } from "./utils";

const OVERVIEW = {
  projects_by_status: { completed: 2, in_progress: 1 },
  total_tokens: 1_234_567,
  total_cost_usd: 12.34,
  agents: [
    {
      agent_key: "backend_engineer",
      name: "Bo Backend",
      role_title: "Backend Engineer",
      tasks_completed: 5,
      tasks_total: 6,
      revision_rate: 0.25,
      avg_tokens: 900.5,
      avg_latency_ms: 1500,
      cost_usd: 3.21,
      llm_calls: 12,
    },
    {
      agent_key: "qa_engineer",
      name: "Quinn QA",
      role_title: "QA Engineer",
      tasks_completed: 3,
      tasks_total: 3,
      revision_rate: 0,
      avg_tokens: 400,
      avg_latency_ms: 800,
      cost_usd: 1.1,
      llm_calls: 4,
    },
  ],
};

describe("AnalyticsPage", () => {
  it("renders stat tiles and status chips", async () => {
    mockFetch({ "GET /analytics/overview": OVERVIEW });
    renderWithProviders(<AnalyticsPage />);

    expect(await screen.findByText((1_234_567).toLocaleString())).toBeInTheDocument();
    expect(screen.getByText("$12.34")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument(); // total projects
    expect(screen.getByText("completed")).toBeInTheDocument();
  });

  it("renders the agent performance table sorted by tasks completed", async () => {
    mockFetch({ "GET /analytics/overview": OVERVIEW });
    renderWithProviders(<AnalyticsPage />);

    const rows = await screen.findAllByRole("row");
    expect(rows).toHaveLength(3); // header + 2 agents
    expect(rows[1]).toHaveTextContent("Bo Backend");
    expect(rows[1]).toHaveTextContent("5 / 6");
    expect(rows[1]).toHaveTextContent("25%");
    expect(rows[1]).toHaveTextContent("1.5s");
    expect(rows[2]).toHaveTextContent("Quinn QA");
  });

  it("shows the empty state when no agents have worked", async () => {
    mockFetch({
      "GET /analytics/overview": {
        projects_by_status: {},
        total_tokens: 0,
        total_cost_usd: 0,
        agents: [],
      },
    });
    renderWithProviders(<AnalyticsPage />);
    expect(await screen.findByText(/No agent activity yet/)).toBeInTheDocument();
    expect(screen.getByText(/No projects yet/)).toBeInTheDocument();
  });
});

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import DashboardPage from "../pages/DashboardPage";
import { makeProject, mockFetch, page, renderWithProviders } from "./utils";

describe("DashboardPage", () => {
  it("lists projects with status and stage", async () => {
    mockFetch({
      "GET /projects": page([
        makeProject({ name: "Expense Tracker" }),
        makeProject({ name: "Food Delivery", status: "completed" }),
      ]),
    });
    renderWithProviders(<DashboardPage />);

    expect(await screen.findByText("Expense Tracker")).toBeInTheDocument();
    expect(screen.getByText("Food Delivery")).toBeInTheDocument();
    expect(screen.getByText(/2 projects · 1 in flight/)).toBeInTheDocument();
    expect(screen.getAllByText(/Stage: engineering/).length).toBeGreaterThan(0);
  });

  it("shows the empty state when there are no projects", async () => {
    mockFetch({ "GET /projects": page([]) });
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText(/No projects yet/)).toBeInTheDocument();
  });

  it("creates a project from the prompt form", async () => {
    const created = makeProject({ name: "Study Assistant" });
    const calls = mockFetch({
      "GET /projects": page([]),
      "POST /projects": created,
    });
    renderWithProviders(<DashboardPage />);

    await userEvent.type(
      screen.getByLabelText("Project prompt"),
      "Develop an AI study assistant",
    );
    await userEvent.type(screen.getByLabelText("Project name"), "Study Assistant");
    await userEvent.click(screen.getByRole("button", { name: /kick off/i }));

    await waitFor(() =>
      expect(calls).toContainEqual({
        url: "/projects",
        method: "POST",
        body: {
          name: "Study Assistant",
          prompt: "Develop an AI study assistant",
          human_in_loop: false,
        },
      }),
    );
  });

  it("fills the prompt from an example chip", async () => {
    mockFetch({ "GET /projects": page([]) });
    renderWithProviders(<DashboardPage />);
    await userEvent.click(screen.getByRole("button", { name: "Build a food delivery app" }));
    expect(screen.getByLabelText("Project prompt")).toHaveValue("Build a food delivery app");
  });
});

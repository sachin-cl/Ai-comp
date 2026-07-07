import { expect, test } from "@playwright/test";
import { createProject, registerAndLogin, uniqueEmail, waitForCompletion } from "./helpers";

test.describe("project workflow", () => {
  test("create a project and watch the agents collaborate to completion", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("flow"));
    await createProject(page, "Build an expense tracker", "Expense Tracker E2E");

    // Live conversation: the kickoff message and at least one agent result appear.
    await expect(page.getByTestId("message-row").first()).toBeVisible({ timeout: 60_000 });
    await expect(
      page.getByTestId("message-row").filter({ hasText: "Kickoff" }),
    ).toBeVisible();

    // Kanban board fills as tasks move through the workflow.
    await page.getByRole("tab", { name: "Board" }).click();
    await expect(page.getByTestId("kanban-card").first()).toBeVisible();

    // The workflow runs to CEO approval on the mock provider.
    await waitForCompletion(page, "Expense Tracker E2E");

    // Overview shows the architect's work after completion.
    await page.getByRole("tab", { name: "Overview" }).click();
    await expect(page.getByText("Architecture")).toBeVisible();

    // Timeline recorded a span for every task.
    await page.getByRole("tab", { name: "Timeline" }).click();
    await expect(page.getByText("QA review").first()).toBeVisible();
  });

  test("two projects run simultaneously without interference", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("parallel"));
    await createProject(page, "Build a todo app", "Parallel A");
    await page.goto("/");
    await createProject(page, "Build a blog platform", "Parallel B");

    await waitForCompletion(page, "Parallel B");
    await page.goto("/");
    await page.getByRole("link", { name: /Parallel A/ }).click();
    await waitForCompletion(page, "Parallel A");
  });
});

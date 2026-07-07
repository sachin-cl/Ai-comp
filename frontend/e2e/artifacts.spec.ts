import { expect, test } from "@playwright/test";
import { createProject, registerAndLogin, uniqueEmail, waitForCompletion } from "./helpers";

test.describe("artifacts", () => {
  test("browse generated files and download the project ZIP", async ({ page }) => {
    await registerAndLogin(page, uniqueEmail("artifacts"));
    await createProject(page, "Create an expense tracker", "Artifact Hunt");
    await waitForCompletion(page, "Artifact Hunt");

    // File explorer: tree of generated files with a syntax-highlighted viewer.
    await page.getByRole("tab", { name: "Files" }).click();
    const files = page.getByTestId("file-node");
    await expect(files.first()).toBeVisible();
    expect(await files.count()).toBeGreaterThanOrEqual(5);

    await files.filter({ hasText: "README.md" }).first().click();
    await expect(page.getByText("v1", { exact: true })).toBeVisible();
    await expect(page.locator("code")).toContainText(/./);

    // Download delivers a non-empty ZIP named after the project.
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: /Download ZIP/ }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.zip$/);
    const path = await download.path();
    expect(path).toBeTruthy();
  });
});

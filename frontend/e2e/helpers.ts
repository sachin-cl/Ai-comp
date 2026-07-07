import { expect, type Page } from "@playwright/test";

export function uniqueEmail(tag: string): string {
  return `e2e-${tag}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

export const PASSWORD = "password-e2e-123";

/** Register a fresh account and land on the dashboard. */
export async function registerAndLogin(page: Page, email: string): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("E2E Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/Password/).fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Company Dashboard" })).toBeVisible();
}

/** Create a project from the dashboard prompt form and open its page. */
export async function createProject(page: Page, prompt: string, name: string): Promise<void> {
  await page.getByLabel("Project prompt").fill(prompt);
  await page.getByLabel("Project name").fill(name);
  await page.getByRole("button", { name: /Kick off/ }).click();
  await page.getByRole("link", { name: new RegExp(name) }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
}

/** Wait until the project header badge shows `completed` (mock provider ≈ 30s). */
export async function waitForCompletion(page: Page, name: string): Promise<void> {
  const header = page.getByRole("heading", { name }).locator("..");
  await expect(header.getByText("completed", { exact: true })).toBeVisible({
    timeout: 150_000,
  });
}

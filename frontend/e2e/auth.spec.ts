import { expect, test } from "@playwright/test";
import { PASSWORD, registerAndLogin, uniqueEmail } from "./helpers";

test.describe("authentication", () => {
  test("register, sign out, sign back in", async ({ page }) => {
    const email = uniqueEmail("auth");
    await registerAndLogin(page, email);

    // Session survives a reload (persisted tokens).
    await page.reload();
    await expect(page.getByRole("heading", { name: "Company Dashboard" })).toBeVisible();

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("heading", { name: "AI Software Company" })).toBeVisible();

    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Company Dashboard" })).toBeVisible();
  });

  test("wrong password is rejected with a visible error", async ({ page }) => {
    const email = uniqueEmail("badpw");
    await registerAndLogin(page, email);
    await page.getByRole("button", { name: "Sign out" }).click();

    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("definitely-wrong");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toContainText(/invalid/i);
  });

  test("unauthenticated visitors are redirected to login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });
});

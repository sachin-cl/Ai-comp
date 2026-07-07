import { defineConfig, devices } from "@playwright/test";

/**
 * E2E tests run against a fully started stack (API + worker + Postgres + Redis
 * + frontend) with the mock LLM provider, e.g.:
 *
 *   docker compose up -d          # from the repo root
 *   npx playwright test           # PW_BASE_URL defaults to the compose frontend
 *
 * For a dev-server run: `npm run dev` + API on :8000, then
 * PW_BASE_URL=http://localhost:5173 npx playwright test
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.PW_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});

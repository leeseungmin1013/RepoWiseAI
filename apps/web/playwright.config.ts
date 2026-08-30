import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "line",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command:
        "uv run --project apps/api uvicorn app.main:app --host 127.0.0.1 --port 8000",
      cwd: "../..",
      env: {
        ...process.env,
        ASSESSMENT_TIMEOUT_SECONDS: "2",
        AUTH_REQUIRED: "false",
      },
      url: "http://127.0.0.1:8000/api/health/ready",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "pnpm --filter @repowise/web dev --hostname 127.0.0.1 --port 3000",
      cwd: "../..",
      env: {
        ...process.env,
        NEXT_PUBLIC_API_URL: "http://127.0.0.1:8000/api",
        NEXT_PUBLIC_SUPABASE_URL: "",
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "",
      },
      url: "http://127.0.0.1:3000",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});

import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const apiURL = process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000";
const reuseExistingServer = !process.env.CI;

export default defineConfig({
  testDir: "./e2e",
  timeout: 240_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        process.env.CLIPMIND_BACKEND_CMD ??
        "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000",
      cwd: "../backend",
      url: `${apiURL}/api/health`,
      reuseExistingServer,
      timeout: 120_000,
      env: {
        DATA_DIR: "../data",
      },
    },
    {
      command: "npm run dev",
      url: baseURL,
      reuseExistingServer,
      timeout: 120_000,
    },
  ],
});

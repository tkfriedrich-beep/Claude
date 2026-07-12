import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// E2E runs against a REAL control plane on an isolated data dir (port 8788) —
// no mocked HTTP anywhere; the mock *runtime* is the product's own demo mode.
const repoRoot = path.resolve(__dirname, "../..");
const e2eDataDir = path.join(repoRoot, "data", "e2e");

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false, // one shared control plane; specs share state intentionally
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // Sandbox/CI images preinstall Chromium here; never download browsers.
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
      : undefined,
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
      testIgnore: /mobile\.spec\.ts/,
    },
    {
      name: "mobile",
      // emulate the iPhone viewport but run Chromium (the only preinstalled engine)
      use: { ...devices["iPhone 13"], browserName: "chromium" },
      testMatch: /mobile\.spec\.ts/,
    },
  ],
  webServer: [
    {
      command:
        `bash -c "cd ${repoRoot}/services/control-plane && rm -rf ${e2eDataDir} && ` +
        `COCKPIT_DATA_DIR=${e2eDataDir} uv run alembic upgrade head && ` +
        `COCKPIT_DATA_DIR=${e2eDataDir} COCKPIT_PORT=8788 uv run uvicorn cockpit.main:app --port 8788"`,
      url: "http://localhost:8788/api/v1/health",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "pnpm exec next dev --port 3100",
      url: "http://localhost:3100",
      reuseExistingServer: false,
      timeout: 90_000,
      env: { NEXT_PUBLIC_API_URL: "http://localhost:8788" },
    },
  ],
});

import { defineConfig, devices } from "@playwright/test";

const backendPort = 18080;
const frontendPort = 3100;
const smokeDbPath = "/tmp/sql-agent-frontend-smoke/smoke.db";

export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.smoke.spec.ts",
  timeout: 120_000,
  expect: {
    timeout: 20_000,
  },
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: `SMOKE_BACKEND_PORT=${backendPort} SMOKE_DB_PATH=${smokeDbPath} bash ./scripts/start-smoke-backend.sh`,
      port: backendPort,
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: `SQL_AGENT_RUN_URL=http://127.0.0.1:${backendPort}/run SQL_AGENT_DB_PATH=${smokeDbPath} pnpm dev --hostname 127.0.0.1 --port ${frontendPort}`,
      port: frontendPort,
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});

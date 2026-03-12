import { defineConfig, devices } from "@playwright/test";

const backendPort = 18080;
const frontendPort = 3100;
const smokeDbPath = "/tmp/sql-agent-frontend-smoke/smoke.db";
const smokeDbBackend = process.env.SMOKE_DB_BACKEND ?? "sqlite";
const smokeBackendCommand =
  smokeDbBackend === "postgres"
    ? `SMOKE_DB_BACKEND=postgres SMOKE_BACKEND_PORT=${backendPort} bash ./scripts/start-smoke-backend.sh`
    : `SMOKE_BACKEND_PORT=${backendPort} SMOKE_DB_PATH=${smokeDbPath} bash ./scripts/start-smoke-backend.sh`;

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
      command: smokeBackendCommand,
      port: backendPort,
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: `SQL_AGENT_RUN_URL=http://127.0.0.1:${backendPort}/run pnpm dev --hostname 127.0.0.1 --port ${frontendPort}`,
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

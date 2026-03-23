import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

function loadSample(name: string) {
  const filePath = path.join(process.cwd(), "samples", "adapter_contract", name, "response.json");
  return JSON.parse(fs.readFileSync(filePath, "utf8")) as Record<string, unknown>;
}

async function mockApiChat(page: Page, sampleName: string) {
  const payload = loadSample(sampleName);
  const httpStatus = typeof payload.http_status === "number" ? payload.http_status : 200;
  await page.route("**/api/chat", async (route) => {
    await route.fulfill({
      status: httpStatus,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
}

async function submitQuestion(page: Page, question: string, options: { allowWrite?: boolean; dryRun?: boolean } = {}) {
  await page.goto("/");
  await page.getByLabel("Question").fill(question);

  if (options.allowWrite) {
    await page.getByTestId("allow-write-toggle").check();
  }
  if (options.allowWrite && options.dryRun === false) {
    await page.getByTestId("dry-run-toggle").uncheck();
  }

  await page.getByTestId("submit-request").click();
}

async function openEvidencePanel(page: Page, label: "Raw JSON" | "Trace") {
  await page.locator("summary").filter({ hasText: label }).click();
}

test("READ success renders result card, SQL panel, result preview, raw JSON, and trace", async ({ page }) => {
  await mockApiChat(page, "read_success");
  await submitQuestion(page, "List the ids and names of all students.");

  await expect(page.getByTestId("status-badge")).toHaveText("SUCCESS");
  await expect(page.getByTestId("mode-badge")).toHaveText("READ");
  await expect(page.getByTestId("message-text")).toContainText("Alice Johnson");
  await expect(page.getByTestId("sql-panel")).toContainText("SELECT id, name FROM students LIMIT 50");
  await expect(page.getByTestId("result-preview")).toContainText("Alice Johnson");
  await expect(page.getByTestId("result-row-count")).toHaveText("6 rows");

  await openEvidencePanel(page, "Raw JSON");
  await expect(page.getByTestId("raw-json")).toContainText("\"status\": \"SUCCESS\"");

  await openEvidencePanel(page, "Trace");
  await expect(page.getByTestId("trace-json")).toContainText("\"name\": \"intent_detection\"");
});

test("WRITE dry-run success renders stable write evidence surfaces", async ({ page }) => {
  await mockApiChat(page, "write_dry_run_success");
  await submitQuestion(page, "Update the student named Alice Johnson to have GPA 3.9.", {
    allowWrite: true,
    dryRun: true,
  });

  await expect(page.getByTestId("status-badge")).toHaveText("SUCCESS");
  await expect(page.getByTestId("mode-badge")).toHaveText("WRITE");
  await expect(page.getByTestId("message-text")).toHaveText("Dry-run: would update 1 row(s)");
  await expect(page.getByTestId("sql-panel")).toContainText("UPDATE students SET gpa = 3.9");
  await expect(page.getByTestId("write-evidence")).toBeVisible();
  await expect(page.getByTestId("write-dry-run")).toHaveText("true");
  await expect(page.getByTestId("write-db-executed")).toHaveText("false");
  await expect(page.getByTestId("write-committed")).toHaveText("false");

  await openEvidencePanel(page, "Raw JSON");
  await expect(page.getByTestId("raw-json")).toContainText("\"dry_run\": true");

  await openEvidencePanel(page, "Trace");
  await expect(page.getByTestId("trace-json")).toContainText("\"name\": \"generate_write_sql\"");
});

test("WRITE commit success renders committed evidence surfaces", async ({ page }) => {
  await mockApiChat(page, "write_commit_success");
  await submitQuestion(page, "Update the student named Alice Johnson to have GPA 3.9.", {
    allowWrite: true,
    dryRun: false,
  });

  await expect(page.getByTestId("status-badge")).toHaveText("SUCCESS");
  await expect(page.getByTestId("mode-badge")).toHaveText("WRITE");
  await expect(page.getByTestId("message-text")).toHaveText("Updated 1 row(s)");
  await expect(page.getByTestId("sql-panel")).toContainText("UPDATE students SET gpa = 3.9");
  await expect(page.getByTestId("write-evidence")).toBeVisible();
  await expect(page.getByTestId("write-dry-run")).toHaveText("false");
  await expect(page.getByTestId("write-db-executed")).toHaveText("true");
  await expect(page.getByTestId("write-committed")).toHaveText("true");

  await openEvidencePanel(page, "Raw JSON");
  await expect(page.getByTestId("raw-json")).toContainText("\"dry_run\": false");

  await openEvidencePanel(page, "Trace");
  await expect(page.getByTestId("trace-json")).toContainText("\"preview\": \"affected_rows=1, dry_run=False\"");
});

test("previous response is cleared when a new question is submitted", async ({ page }) => {
  // First request: READ success
  const readPayload = loadSample("read_success");
  await page.route("**/api/chat", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(readPayload),
    });
  });
  await page.goto("/");
  await page.getByLabel("Question").fill("List all students.");
  await page.getByTestId("submit-request").click();
  await expect(page.getByTestId("status-badge")).toHaveText("SUCCESS");
  await expect(page.getByTestId("sql-panel")).toBeVisible();

  // Second request: intercept and delay so we can verify cleared state
  let resolveSecond!: () => void;
  const secondResponseReady = new Promise<void>((res) => { resolveSecond = res; });
  await page.unrouteAll();
  await page.route("**/api/chat", async (route) => {
    await secondResponseReady;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(loadSample("write_dry_run_success")),
    });
  });

  await page.getByTestId("allow-write-toggle").check();
  await page.getByLabel("Question").fill("Update Alice GPA to 3.9.");
  await page.getByTestId("submit-request").click();

  // While loading, the old sql-panel and result-preview should be gone
  await expect(page.getByTestId("sql-panel")).not.toBeVisible();
  await expect(page.getByTestId("status-badge")).toHaveText("IDLE");

  // Unblock second request and verify new response
  resolveSecond();
  await expect(page.getByTestId("status-badge")).toHaveText("SUCCESS");
  await expect(page.getByTestId("mode-badge")).toHaveText("WRITE");
});

test("unchecking allow_write resets dry_run to true in the request body", async ({ page }) => {
  let capturedBody: Record<string, unknown> = {};
  await page.route("**/api/chat", async (route) => {
    capturedBody = JSON.parse(route.request().postData() ?? "{}") as Record<string, unknown>;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(loadSample("read_success")),
    });
  });

  await page.goto("/");
  await page.getByLabel("Question").fill("List all students.");

  // Enable write and uncheck dry_run, then disable write again
  await page.getByTestId("allow-write-toggle").check();
  await page.getByTestId("dry-run-toggle").uncheck();
  await page.getByTestId("allow-write-toggle").uncheck();

  await page.getByTestId("submit-request").click();
  await expect(page.getByTestId("status-badge")).toHaveText("SUCCESS");

  // dry_run must be true even though it was previously unchecked
  expect(capturedBody.allow_write).toBe(false);
  expect(capturedBody.dry_run).toBe(true);
});

test("idle state does not show HTTP status badge", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("status-badge")).toHaveText("IDLE");
  // HTTP badge must not be present before any request is made
  await expect(page.locator("text=HTTP 0")).not.toBeVisible();
  await expect(page.locator("text=HTTP")).not.toBeVisible();
});

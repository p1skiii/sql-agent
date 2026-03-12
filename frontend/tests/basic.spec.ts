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

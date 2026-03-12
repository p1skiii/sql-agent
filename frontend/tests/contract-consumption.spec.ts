import { expect, test, type Page } from "@playwright/test";

function normalizedReadResponse() {
  return {
    ok: true,
    http_status: 200,
    status: "SUCCESS",
    message: "Primary message comes from response.message",
    data: {
      question: "List the ids and names of all students.",
      mode: "READ",
      summary: "Legacy summary field stays secondary.",
      sql: "SELECT id, name FROM students LIMIT 1",
      raw_sql: "SELECT id, name FROM students",
      repaired_sql: "SELECT id, name FROM students LIMIT 1",
      dry_run: null,
      db_executed: true,
      committed: null,
      result: {
        columns: ["id", "name"],
        rows: [{ id: 1, name: "Normalized Row" }],
        row_count: 1,
      },
      trace: [{ name: "execute_sql", preview: "row_count=1" }],
    },
    error: null,
    raw: {
      status: "SUCCESS",
      summary: "Raw summary should not be the primary message.",
      result: {
        columns: ["id", "name"],
        rows: [{ id: 99, name: "Raw Only Row" }],
        row_count: 1,
      },
      trace: [{ name: "execute_sql", preview: "row_count=99" }],
    },
  };
}

function normalizedWriteResponse(dryRun: boolean) {
  return {
    ok: true,
    http_status: 200,
    status: "SUCCESS",
    message: dryRun ? "Dry-run contract evidence" : "Commit contract evidence",
    data: {
      question: "Update the student named Alice Johnson to have GPA 3.9.",
      mode: "WRITE",
      summary: dryRun ? "Legacy dry-run summary" : "Legacy commit summary",
      sql: "UPDATE students SET gpa = 3.9 WHERE name = 'Alice Johnson'",
      raw_sql: null,
      repaired_sql: null,
      dry_run: dryRun,
      db_executed: !dryRun,
      committed: !dryRun,
      result: {
        columns: [],
        rows: [],
        row_count: 0,
      },
      trace: [{ name: "execute_write", preview: `affected_rows=1, dry_run=${dryRun}` }],
    },
    error: null,
    raw: {
      dry_run: !dryRun,
      affected_rows: 999,
    },
  };
}

async function mockApiChat(page: Page, payload: Record<string, unknown>) {
  await page.route("**/api/chat", async (route) => {
    await route.fulfill({
      status: 200,
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

test("READ UI consumes response.message and data.result instead of raw fallbacks", async ({ page }) => {
  await mockApiChat(page, normalizedReadResponse());
  await submitQuestion(page, "List the ids and names of all students.");

  await expect(page.getByTestId("message-text")).toHaveText("Primary message comes from response.message");
  await expect(page.getByTestId("summary-text")).toHaveText("Legacy summary field stays secondary.");
  await expect(page.getByTestId("result-preview")).toContainText("Normalized Row");
  await expect(page.getByTestId("result-preview")).not.toContainText("Raw Only Row");

  await openEvidencePanel(page, "Raw JSON");
  await expect(page.getByTestId("raw-json")).toContainText("Raw Only Row");
});

test("WRITE dry-run UI consumes db_executed and committed from normalized data", async ({ page }) => {
  await mockApiChat(page, normalizedWriteResponse(true));
  await submitQuestion(page, "Update the student named Alice Johnson to have GPA 3.9.", {
    allowWrite: true,
    dryRun: true,
  });

  await expect(page.getByTestId("message-text")).toHaveText("Dry-run contract evidence");
  await expect(page.getByTestId("write-dry-run")).toHaveText("true");
  await expect(page.getByTestId("write-db-executed")).toHaveText("false");
  await expect(page.getByTestId("write-committed")).toHaveText("false");

  await openEvidencePanel(page, "Raw JSON");
  await expect(page.getByTestId("raw-json")).toContainText("\"dry_run\": false");
});

test("WRITE commit UI consumes committed evidence from normalized data", async ({ page }) => {
  await mockApiChat(page, normalizedWriteResponse(false));
  await submitQuestion(page, "Update the student named Alice Johnson to have GPA 3.9.", {
    allowWrite: true,
    dryRun: false,
  });

  await expect(page.getByTestId("message-text")).toHaveText("Commit contract evidence");
  await expect(page.getByTestId("write-dry-run")).toHaveText("false");
  await expect(page.getByTestId("write-db-executed")).toHaveText("true");
  await expect(page.getByTestId("write-committed")).toHaveText("true");

  await openEvidencePanel(page, "Raw JSON");
  await expect(page.getByTestId("raw-json")).toContainText("\"dry_run\": true");
});

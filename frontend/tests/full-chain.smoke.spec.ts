import { expect, test, type Page } from "@playwright/test";

async function setCheckbox(page: Page, testId: string, checked: boolean) {
  const checkbox = page.getByTestId(testId);
  if ((await checkbox.isChecked()) !== checked) {
    if (checked) {
      await checkbox.check();
    } else {
      await checkbox.uncheck();
    }
  }
}

async function submitQuestion(page: Page, question: string, options: { allowWrite: boolean; dryRun: boolean }) {
  await page.getByLabel("Question").fill(question);
  await setCheckbox(page, "allow-write-toggle", options.allowWrite);
  if (options.allowWrite) {
    await setCheckbox(page, "dry-run-toggle", options.dryRun);
  }
  await page.getByTestId("submit-request").click();
}

async function openEvidencePanel(page: Page, label: "Raw JSON" | "Trace") {
  await page.locator("summary").filter({ hasText: label }).click();
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("READ success smoke proves the page can render live evidence from the full chain", async ({ page }) => {
  await submitQuestion(page, "List the ids and names of all students.", { allowWrite: false, dryRun: true });

  await expect(page.getByTestId("status-badge")).toHaveText("SUCCESS");
  await expect(page.getByTestId("mode-badge")).toHaveText("READ");
  await expect(page.getByTestId("message-text")).toContainText("Alice Johnson");
  await expect(page.getByTestId("sql-panel")).toContainText("SELECT");
  await expect(page.getByTestId("sql-panel")).toContainText("students");
  await expect(page.getByTestId("result-preview")).toContainText("Alice Johnson");
  await expect(page.getByTestId("result-row-count")).toHaveText(/rows?/);

  await openEvidencePanel(page, "Raw JSON");
  await expect(page.getByTestId("raw-json")).toContainText("\"status\": \"SUCCESS\"");

  await openEvidencePanel(page, "Trace");
  await expect(page.getByTestId("trace-json")).toContainText("\"name\": \"intent_detection\"");
});

test("WRITE dry-run smoke proves dry_run flags and leaves the database unchanged", async ({ page }) => {
  await submitQuestion(page, "Update the student named Alice Johnson to have GPA 3.9.", {
    allowWrite: true,
    dryRun: true,
  });

  await expect(page.getByTestId("status-badge")).toHaveText("SUCCESS");
  await expect(page.getByTestId("mode-badge")).toHaveText("WRITE");
  await expect(page.getByTestId("write-evidence")).toBeVisible();
  await expect(page.getByTestId("write-dry-run")).toHaveText("true");
  await expect(page.getByTestId("write-db-executed")).toHaveText("false");
  await expect(page.getByTestId("write-committed")).toHaveText("false");
  await expect(page.getByTestId("sql-panel")).toContainText("UPDATE");
  await expect(page.getByTestId("sql-panel")).toContainText("3.9");

  await openEvidencePanel(page, "Raw JSON");
  await expect(page.getByTestId("raw-json")).toContainText("\"dry_run\": true");

  await openEvidencePanel(page, "Trace");
  await expect(page.getByTestId("trace-json")).toContainText("execute_write_probe");

  await submitQuestion(page, "List the name and GPA for the student named Alice Johnson.", {
    allowWrite: false,
    dryRun: true,
  });

  await expect(page.getByTestId("status-badge")).toHaveText("SUCCESS");
  await expect(page.getByTestId("mode-badge")).toHaveText("READ");
  await expect(page.getByTestId("result-preview")).toContainText("Alice Johnson");
  await expect(page.getByTestId("result-preview")).toContainText("3.8");
});

test("WRITE commit smoke proves committed flags and a follow-up read sees the database change", async ({ page }) => {
  await submitQuestion(page, "Update the student named Alice Johnson to have GPA 3.9.", {
    allowWrite: true,
    dryRun: false,
  });

  await expect(page.getByTestId("status-badge")).toHaveText("SUCCESS");
  await expect(page.getByTestId("mode-badge")).toHaveText("WRITE");
  await expect(page.getByTestId("write-evidence")).toBeVisible();
  await expect(page.getByTestId("write-dry-run")).toHaveText("false");
  await expect(page.getByTestId("write-db-executed")).toHaveText("true");
  await expect(page.getByTestId("write-committed")).toHaveText("true");
  await expect(page.getByTestId("sql-panel")).toContainText("UPDATE");
  await expect(page.getByTestId("sql-panel")).toContainText("3.9");

  await openEvidencePanel(page, "Raw JSON");
  await expect(page.getByTestId("raw-json")).toContainText("\"dry_run\": false");

  await openEvidencePanel(page, "Trace");
  await expect(page.getByTestId("trace-json")).toContainText("execute_write");

  await submitQuestion(page, "List the name and GPA for the student named Alice Johnson.", {
    allowWrite: false,
    dryRun: true,
  });

  await expect(page.getByTestId("status-badge")).toHaveText("SUCCESS");
  await expect(page.getByTestId("mode-badge")).toHaveText("READ");
  await expect(page.getByTestId("result-preview")).toContainText("Alice Johnson");
  await expect(page.getByTestId("result-preview")).toContainText("3.9");
});

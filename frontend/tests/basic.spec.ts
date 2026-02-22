import { test, expect } from '@playwright/test';

// Simple smoke test: page loads, send text, gets any response.
test('chat responds with summary', async ({ page }) => {
  await page.goto('/');
  await page.getByPlaceholder('Type your question and press Enter').fill('List the names of all students');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByText('Thinking…')).toBeVisible({ timeout: 5000 });
  await expect(page.getByText(/names/)).toBeVisible({ timeout: 15000 });
});

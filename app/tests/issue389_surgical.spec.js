const { test, expect } = require('@playwright/test');

test('issue389 surgical', async ({ page }) => {
  await page.goto('/studio.html');

  // Assert the panel heading is visible on the rendered page.
  await expect(page.getByText('Load sequences')).toBeVisible();

  // Assert that window.Sequences was defined by the loaded script.
  await page.waitForFunction(() => typeof window.Sequences === 'object' || typeof window.Sequences === 'function');

  // Assert the error div is attached inside the container (state: 'attached', not 'visible').
  const container = page.locator('[data-panel="sequences"]');
  const errorDiv = container.locator('[data-testid="sequences-error"]');
  await expect(errorDiv).toBeAttached();
});

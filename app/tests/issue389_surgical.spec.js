const { test, expect } = require('@playwright/test');

test('issue389 surgical', async ({ page }) => {
    await page.goto('/studio.html');

    // Assert the text 'Load sequences' is visible
    await expect(page.getByRole('heading', {name: 'Load sequences'})).toBeVisible();

    // Assert via waitForFunction that window.Sequences is defined
    await page.waitForFunction(() => typeof window.Sequences !== 'undefined');

    // Wait for error div inside container with state: 'attached' (empty element has no bounding box)
    const container = page.locator('[data-panel="sequences"]');
    await container.locator('[data-testid="sequences-error"]').waitFor({ state: 'attached' });
});

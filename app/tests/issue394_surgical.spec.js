const { test, expect } = require('@playwright/test');

test('issue394 surgical', async ({ page }) => {
    await page.goto('/studio.html');

    // Assert the new panel heading is visible on screen
    await expect(page.getByText('Run history')).toBeVisible();

    // Assert the module global was wired in by DOMContentLoaded init
    await page.waitForFunction(() => typeof window.SequenceRuns !== 'undefined');

    // Append a probe row element and click it to exercise the delegated handler.
    // With no backend, GET /sequence-runs fails and the handler renders an error div.
    const errorSelector = '[data-panel="sequence-runs"] [data-testid="runs-error"]';
    await page.evaluate(() => {
        const probe = document.createElement('div');
        probe.setAttribute('data-testid', 'sequence-row');
        probe.setAttribute('data-id', 'seq-probe');
        probe.textContent = 'probe';
        document.body.appendChild(probe);
        probe.click();
    });

    // The error div must appear inside the sequence-runs panel container
    const errorEl = await page.waitForSelector(errorSelector);
    expect(await errorEl.isVisible()).toBe(true);
    expect(await errorEl.textContent()).toContain('Could not load runs.');
});

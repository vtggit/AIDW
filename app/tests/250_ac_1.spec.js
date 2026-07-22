const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:8080';

function marker() {
    return `wz-${Date.now()}-${Math.floor(Math.random() * 9999)}`;
}

test('250_ac_1_data_source', async ({ page }) => {
    // Bootstrap development auth
    await page.goto(`${BASE}/auth/dev-token`);
    const token = await page.locator('#dev-token').textContent();
    expect(token).toBeTruthy();
    await page.evaluate((t) => localStorage.setItem('token', t), token);

    const m = marker();

    // Navigate to the app root
    await page.goto(BASE);

    // Assert wizard containers are visible via their data-testids
    await expect(page.locator('[data-testid="wizard-definitions"]')).toBeVisible();
    await expect(page.locator('[data-testid="wizard-steps"]')).toBeVisible();
    await expect(page.locator('[data-testid="wizard-flows"]')).toBeVisible();
    await expect(page.locator('[data-testid="wizard-svg"]')).toBeVisible();

    // Create a definition through the wizard form with marker in its name
    await page.fill('#wizard-def-name', `Def ${m}`);
    await page.fill('#wizard-def-key', m.toLowerCase());
    await page.click('#wizard-create-def-btn');

    // Click its card in wizard-definitions
    const defCard = page.locator('#wizard-definitions').locator(`text=${m}`);
    await expect(defCard).toBeVisible();
    await defCard.click();

    // Add three steps: start, user, end with distinct step keys
    // Step 1: start
    await page.fill('#wizard-step-name', 'Start');
    await page.fill('#wizard-step-key', `${m}-start`);
    await page.fill('#wizard-step-ordinal', '1');
    await page.selectOption('#wizard-step-type', 'start');
    await page.click('#wizard-create-step-btn');

    // Step 2: user
    await page.fill('#wizard-step-name', 'User Task');
    await page.fill('#wizard-step-key', `${m}-user`);
    await page.fill('#wizard-step-ordinal', '2');
    await page.selectOption('#wizard-step-type', 'user');
    await page.click('#wizard-create-step-btn');

    // Step 3: end
    await page.fill('#wizard-step-name', 'End');
    await page.fill('#wizard-step-key', `${m}-end`);
    await page.fill('#wizard-step-ordinal', '3');
    await page.selectOption('#wizard-step-type', 'end');
    await page.click('#wizard-create-step-btn');

    // Add two flows: start -> user, user -> end via wizard-flow-source and wizard-flow-target selects
    // Flow 1: start to user
    await page.fill('#wizard-flow-name', `${m}-flow-1`);
    await page.fill('#wizard-flow-key', `${m}-f1`);
    await page.selectOption('#wizard-flow-source', `${m}-start`);
    await page.selectOption('#wizard-flow-target', `${m}-user`);
    await page.click('#wizard-create-flow-btn');

    // Flow 2: user to end
    await page.fill('#wizard-flow-name', `${m}-flow-2`);
    await page.fill('#wizard-flow-key', `${m}-f2`);
    await page.selectOption('#wizard-flow-source', `${m}-user`);
    await page.selectOption('#wizard-flow-target', `${m}-end`);
    await page.click('#wizard-create-flow-btn');

    // Click wizard-generate
    await page.click('#wizard-generate');

    // Assert an <svg> element becomes visible inside wizard-svg containing at least three shape elements
    const svgContainer = page.locator('[data-testid="wizard-svg"] svg');
    await expect(svgContainer).toBeVisible({ timeout: 10000 });

    const shapes = svgContainer.locator('rect, circle, polygon');
    await expect(shapes).toHaveCount({ greaterThanOrEqual: 3 }, { timeout: 10000 });

    // Assert wizard-download-xml and wizard-download-svg are no longer disabled
    await expect(page.locator('#wizard-download-xml')).not.toBeDisabled();
    await expect(page.locator('#wizard-download-svg')).not.toBeDisabled();
});

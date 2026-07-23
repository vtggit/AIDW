// End-to-end: the Process wizard (Path B) authoring flow in a real browser.
// Drives the REAL UI against a running stack at BASE_URL (nginx proxying /api -> backend):
// create a definition, select it, add start/user/end steps, connect them with two flows,
// click Generate, and assert the server-generated SVG diagram renders with its shapes and
// the download buttons arm. Auth is the page's own development bootstrap (the app
// auto-logs-in with the dev admin token — see warehouse.js _ensureAuth), so no token
// plumbing is needed here. Mirrors the conventions of suggestions.spec.js.
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:8080';
const MARK = `wz${Date.now()}`; // unique per run so assertions never collide with existing rows

test('250_ac_1_data_source', async ({ page }) => {
    await page.goto(BASE + '/studio.html');  // wizard moved to the Studio (AIDW#264/#269)

    // The wizard section rendered and the module bound (containers exist; empties are
    // zero-height, so presence is asserted via attachment and the controls via visibility).
    await expect(page.locator('[data-testid="wizard-definitions"]')).toBeAttached();
    await expect(page.locator('[data-testid="wizard-steps"]')).toBeAttached();
    await expect(page.locator('[data-testid="wizard-flows"]')).toBeAttached();
    await expect(page.locator('[data-testid="wizard-svg"]')).toBeAttached();
    await expect(page.locator('#wizard-create-def-btn')).toBeVisible();
    await expect(page.locator('[data-testid="wizard-generate"]')).toBeVisible();

    // Create a definition and select its card.
    await page.fill('#wizard-def-name', `Demo process ${MARK}`);
    await page.fill('#wizard-def-key', `${MARK}_proc`);
    await page.click('#wizard-create-def-btn');
    const card = page.locator('#wizard-definitions .wizard-card', { hasText: MARK });
    await expect(card).toBeVisible();
    await card.click();

    // Three steps: start, user, end — distinct step keys.
    const steps = [
        { name: 'Start', key: `${MARK}_start`, ordinal: '1', type: 'start' },
        { name: 'Review', key: `${MARK}_review`, ordinal: '2', type: 'user' },
        { name: 'Done', key: `${MARK}_end`, ordinal: '3', type: 'end' },
    ];
    for (const s of steps) {
        await page.fill('#wizard-step-name', s.name);
        await page.fill('#wizard-step-key', s.key);
        await page.fill('#wizard-step-ordinal', s.ordinal);
        await page.selectOption('#wizard-step-type', s.type);
        await page.click('#wizard-create-step-btn');
        // the steps list refresh also rebuilds the flow selects — wait for the option
        await expect(page.locator(`#wizard-flow-source option[value="${s.key}"]`)).toBeAttached();
    }

    // Two flows: start -> user, user -> end.
    const flows = [
        { name: 'to review', key: `${MARK}_f1`, from: `${MARK}_start`, to: `${MARK}_review` },
        { name: 'to done', key: `${MARK}_f2`, from: `${MARK}_review`, to: `${MARK}_end` },
    ];
    for (const f of flows) {
        await page.fill('#wizard-flow-name', f.name);
        await page.fill('#wizard-flow-key', f.key);
        await page.selectOption('#wizard-flow-source', f.from);
        await page.selectOption('#wizard-flow-target', f.to);
        await page.click('#wizard-create-flow-btn');
        await expect(page.locator('#wizard-flows .wizard-row', { hasText: f.key })).toBeVisible();
    }

    // Generate: the server returns {process_key, bpmn_xml, svg}; the SVG lands inline.
    await page.click('[data-testid="wizard-generate"]');
    const svg = page.locator('[data-testid="wizard-svg"] svg');
    await expect(svg).toBeVisible({ timeout: 15000 });

    // One shape per step (rect/circle/polygon) — at least the three we authored.
    const shapeCount = await svg.locator('rect, circle, polygon').count();
    expect(shapeCount).toBeGreaterThanOrEqual(3);

    // The staged artifacts armed the download buttons.
    await expect(page.locator('#wizard-download-xml')).toBeEnabled();
    await expect(page.locator('#wizard-download-svg')).toBeEnabled();
});

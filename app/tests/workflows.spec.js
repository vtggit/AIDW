// End-to-end: the BPMN authoring editor renders in the browser (bpmn.io / bpmn-js, vendored).
// Loads the app, asserts the modeler mounts an SVG canvas with the palette, the bpmn.io
// watermark is present and visible (VTG-ADOPT-001 attribution), and Download BPMN emits a
// .bpmn file. Authoring is client-side, so no API/auth seeding is needed. Requires a running
// frontend at BASE_URL.
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:8080';

test('bpmn-js authoring editor renders with palette + visible watermark', async ({ page }) => {
    await page.goto(BASE + '/');
    // the modeler mounts inside our canvas container
    const canvas = page.locator('[data-testid="bpmn-canvas"]');
    await expect(canvas).toBeVisible();
    // bpmn-js renders an SVG diagram + a palette of tools
    await expect(canvas.locator('svg').first()).toBeVisible({ timeout: 10000 });
    await expect(canvas.locator('.djs-palette')).toBeVisible();
    // the starter diagram's start event is on the canvas
    await expect(canvas.locator('.djs-element').first()).toBeVisible();

    // VTG-ADOPT-001: the bpmn.io watermark must be present and visible, not hidden/overlapped
    const mark = canvas.locator('.bjs-powered-by');
    await expect(mark).toBeVisible();
    const box = await mark.boundingBox();
    expect(box && box.width > 0 && box.height > 0).toBeTruthy();
});

test('Download BPMN exports a .bpmn file', async ({ page }) => {
    await page.goto(BASE + '/');
    await expect(page.locator('[data-testid="bpmn-canvas"] svg').first()).toBeVisible({ timeout: 10000 });
    const [download] = await Promise.all([
        page.waitForEvent('download'),
        page.locator('[data-testid="bpmn-download"]').click(),
    ]);
    expect(download.suggestedFilename()).toBe('process.bpmn');
});

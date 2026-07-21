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

    // VTG-ADOPT-001: the bpmn.io watermark must be present, visible, still linked to bpmn.io,
    // and rendered UNALTERED at its intrinsic size (currently 53x21, from the logo's own
    // width/height attributes in the vendored bundle).
    //
    // A non-zero box is NOT sufficient: a stretched or clipped mark also has a non-zero box, so
    // the previous assertion could not catch the regression we actually care about. The canvas
    // fill rule (.bpmn-canvas svg { 100% !important }) matches the mark's own <svg>, and
    // workflows.css restores it explicitly — this pins that guarantee.
    const mark = canvas.locator('.bjs-powered-by');
    await expect(mark).toBeVisible();
    await expect(mark).toHaveAttribute('href', /bpmn\.io/);

    const logo = mark.locator('svg');
    // Compare against the element's OWN declared size, so a future bpmn-js logo change does not
    // false-fail — what must never change is that we render it unaltered.
    const intrinsic = await logo.evaluate((el) => ({
        w: parseFloat(el.getAttribute('width')),
        h: parseFloat(el.getAttribute('height')),
    }));
    expect(Number.isFinite(intrinsic.w) && Number.isFinite(intrinsic.h)).toBeTruthy();

    const box = await logo.boundingBox();
    expect(box).not.toBeNull();
    expect(Math.round(box.width)).toBe(Math.round(intrinsic.w));
    expect(Math.round(box.height)).toBe(Math.round(intrinsic.h));
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

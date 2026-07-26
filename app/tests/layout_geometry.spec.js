// Rendered-geometry gate (AIDW#306 AC-3): the merge gate measures REAL layout, not source
// text. Charts.renderBar's width parameter is the operator-visible half of the
// grid_col_span sizing chain (#337/#339/#342: span*160 clamped to [640, 1280] in
// drilldown.js) — this spec renders the SVG in a real browser and asserts the LAYOUT
// ENGINE resolved the intended box, so a regression in renderBar's width handling, or CSS
// that constrains chart SVGs, fails here where a source-text match would stay green.
// Data-free by design: only static assets are needed (there is no backend at BASE_URL),
// so it runs identically under the builder's container server and CI's.
const { test, expect } = require('@playwright/test');

test('renderBar width resolves to the rendered SVG box (span sizing chain)', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => typeof Charts !== 'undefined');
    const measure = (w) => page.evaluate((width) => {
        const host = document.createElement('div');
        host.style.cssText = 'position:absolute;left:0;top:0;width:1400px;';
        document.body.appendChild(host);
        host.innerHTML = Charts.renderBar([['a', 3], ['b', 1]], { title: 'g' }, width);
        const box = host.querySelector('svg').getBoundingClientRect();
        host.remove();
        return box.width;
    }, w);

    expect(await measure(undefined)).toBe(640);  // the shipped default
    expect(await measure(960)).toBe(960);        // an explicit width is honoured
    expect(await measure(1280)).toBe(1280);      // the span-12 clamp ceiling renders in full
});

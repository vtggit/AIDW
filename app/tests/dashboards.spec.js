// End-to-end: accepted dashboard items get a chart fill in the browser.
// Seeds a suggestion via the API, accepts it through the real UI, and asserts the item's chart
// container resolves to a terminal state: an SVG/KPI when the stack can serve live data, or the
// explanatory note when it can't (egress off / item not chartable). Requires a running stack
// (backend + nginx) reachable at BASE_URL. Auth is the development admin token.
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:8080';
const TOKEN = 'dev-secret-token:admin';
const MARK = `FE-CHART-${Date.now()}`; // unique per run so assertions never collide

async function createSuggestion(request, title, itemType, aggregation, score = 0.55) {
    const res = await request.post(`${BASE}/api/suggestions`, {
        headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
        data: {
            name: title,
            title,
            item_type: itemType,
            aggregation,
            status: 'suggested',
            strategy: 'schema-only',
            score,
        },
    });
    expect(res.ok(), `create suggestion failed: ${res.status()}`).toBeTruthy();
    return (await res.json()).id;
}

test('accepting a suggestion renders a chart container that reaches a terminal state', async ({ page, request }) => {
    const title = `${MARK} Orders by Region`;
    const sugId = await createSuggestion(request, title, 'bar', 'count');

    await page.addInitScript((t) => { window.sessionStorage.setItem('aicrm_token', t); }, TOKEN);
    await page.goto('/');

    // Accept through the UI -> the item lands on a dashboard with a chart container
    await page.locator(`[data-testid="suggestion"][data-id="${sugId}"] [data-action="accept"]`).click();
    const item = page.locator('[data-testid="dashboard-item"]', { hasText: title });
    await expect(item).toBeVisible();
    const chart = item.getByTestId('chart');
    await expect(chart).toBeVisible();

    // The fill must terminate: either a rendered chart (svg / kpi / value list) or an
    // explanatory note — never left on the transient "Loading data…" placeholder.
    await expect
        .poll(async () => {
            if (await chart.locator('[data-testid="chart-svg"], [data-testid="chart-kpi"]').count()) {
                return 'rendered';
            }
            const notes = await chart.locator('[data-testid="chart-note"]').allTextContents();
            if (notes.length && !notes[0].startsWith('Loading')) return 'note';
            return 'pending';
        }, { timeout: 10000 })
        .not.toBe('pending');
});

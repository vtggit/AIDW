// End-to-end: the schema-tier suggestion loop in the browser.
// Seeds suggestions via the API, then drives the real UI: the inbox renders them, Accept moves one
// onto a dashboard, Dismiss removes one. Requires a running stack (backend + nginx) reachable at
// BASE_URL (nginx proxies /api -> backend). Auth is the development admin token.
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:8080';
const TOKEN = 'dev-secret-token:admin';
const MARK = `FE-${Date.now()}`; // unique per run so assertions never collide with existing rows

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

test('inbox renders suggestions; accept lands one on a dashboard; dismiss removes one', async ({ page, request }) => {
    const barTitle = `${MARK} Orders by ShipCountry`;
    const kpiTitle = `${MARK} Total Freight`;
    const acceptId = await createSuggestion(request, barTitle, 'bar', 'count');
    const dismissId = await createSuggestion(request, kpiTitle, 'kpi', 'sum');

    // seed the dev token before the app's scripts run
    await page.addInitScript((t) => { window.sessionStorage.setItem('aicrm_token', t); }, TOKEN);
    await page.goto('/');

    const inbox = page.getByTestId('inbox');
    await expect(inbox.getByText(barTitle)).toBeVisible();
    await expect(inbox.getByText(kpiTitle)).toBeVisible();

    // Accept -> the card leaves the inbox and appears under Dashboards
    await page.locator(`[data-testid="suggestion"][data-id="${acceptId}"] [data-action="accept"]`).click();
    await expect(inbox.getByText(barTitle)).toHaveCount(0);
    await expect(page.getByTestId('dashboards').getByText(barTitle)).toBeVisible();

    // Dismiss -> the card leaves the inbox
    await page.locator(`[data-testid="suggestion"][data-id="${dismissId}"] [data-action="dismiss"]`).click();
    await expect(inbox.getByText(kpiTitle)).toHaveCount(0);
});

test('inbox ranks suggestions by score — profile-tier confirmation rises to the top', async ({ page, request }) => {
    // seed out of order; the inbox must render them high -> low so profile-tier ranking is visible
    const low = await createSuggestion(request, `${MARK} low`, 'bar', 'count', 0.20);
    const high = await createSuggestion(request, `${MARK} high`, 'bar', 'count', 0.90);
    const mid = await createSuggestion(request, `${MARK} mid`, 'bar', 'count', 0.55);

    await page.addInitScript((t) => { window.sessionStorage.setItem('aicrm_token', t); }, TOKEN);
    await page.goto('/');
    await page.waitForSelector('[data-testid="suggestion"]');

    const ids = await page
        .locator('[data-testid="suggestion"]')
        .evaluateAll((els) => els.map((e) => e.getAttribute('data-id')));
    // among just the three we seeded, DOM order must be descending by score
    const seen = ids.filter((id) => [low, high, mid].includes(id));
    expect(seen).toEqual([high, mid, low]);

    // the top (0.90) reads High, the bottom (0.20) reads Low
    const topConf = page.locator(`[data-testid="suggestion"][data-id="${high}"] [data-testid="confidence"]`);
    const lowConf = page.locator(`[data-testid="suggestion"][data-id="${low}"] [data-testid="confidence"]`);
    await expect(topConf).toHaveText('High');
    await expect(lowConf).toHaveText('Low');
});

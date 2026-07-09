// End-to-end: the PII flags review loop in the browser.
// Seeds a dataset, a discovered field, and pii_flags via the API, then drives the real UI: the
// PII panel renders pending flags grouped by dataset, Confirm removes one (status -> confirmed),
// Dismiss removes one (status -> dismissed). Requires a running stack (backend + nginx) at
// BASE_URL (nginx proxies /api -> backend). Auth is the development admin token.
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:8080';
const TOKEN = 'dev-secret-token:admin';
const MARK = `PII-${Date.now()}`; // unique per run so assertions never collide with existing rows

async function api(request, method, path, data) {
    const res = await request[method](`${BASE}/api${path}`, {
        headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
        ...(data ? { data } : {}),
    });
    expect(res.ok(), `${method} ${path} failed: ${res.status()}`).toBeTruthy();
    return res.status() === 204 ? null : res.json();
}

async function seedFlag(request, datasetId, fieldId, category, name) {
    const flag = await api(request, 'post', '/pii-flags', {
        name,
        dataset_id: datasetId,
        discovered_field_id: fieldId,
        category,
        detection_tier: 'schema',
        status: 'flagged',
        confidence: 0.8,
        rationale: `name token '${category}'`,
        fingerprint: `${MARK}-${category}-${fieldId}`,
    });
    return flag.id;
}

test('PII panel renders pending flags grouped by dataset; confirm and dismiss clear them', async ({ page, request }) => {
    const ds = await api(request, 'post', '/datasets', { name: `${MARK} Customers` });
    const emailField = await api(request, 'post', '/discovered-fields', {
        name: 'EmailAddress', dataset_id: ds.id,
    });
    const keyField = await api(request, 'post', '/discovered-fields', {
        name: 'CustomerID', dataset_id: ds.id,
    });
    const confirmId = await seedFlag(request, ds.id, emailField.id, 'contact', `${MARK} email`);
    const dismissId = await seedFlag(request, ds.id, keyField.id, 'direct_identifier', `${MARK} key`);

    await page.addInitScript((t) => { window.sessionStorage.setItem('aicrm_token', t); }, TOKEN);
    await page.goto('/');

    const pii = page.getByTestId('pii-inbox');
    // the flags render, grouped under their dataset, showing the field name + category
    const group = pii.locator(`[data-testid="pii-group"][data-id="${ds.id}"]`);
    await expect(group.getByText(`${MARK} Customers`)).toBeVisible();
    await expect(group.getByText('EmailAddress')).toBeVisible();
    await expect(group.locator(`[data-testid="pii-flag"][data-id="${confirmId}"]`)).toContainText('contact');

    // Confirm -> the flag leaves the pending panel (status becomes 'confirmed')
    await page.locator(`[data-testid="pii-flag"][data-id="${confirmId}"] [data-action="pii-confirm"]`).click();
    await expect(pii.locator(`[data-testid="pii-flag"][data-id="${confirmId}"]`)).toHaveCount(0);

    // Dismiss -> the flag leaves the pending panel (status becomes 'dismissed')
    await page.locator(`[data-testid="pii-flag"][data-id="${dismissId}"] [data-action="pii-dismiss"]`).click();
    await expect(pii.locator(`[data-testid="pii-flag"][data-id="${dismissId}"]`)).toHaveCount(0);

    // the decisions persisted to the backend with the right statuses
    const flags = await api(request, 'get', '/pii-flags');
    const byId = Object.fromEntries(flags.map((f) => [f.id, f.status]));
    expect(byId[confirmId]).toBe('confirmed');
    expect(byId[dismissId]).toBe('dismissed');
});

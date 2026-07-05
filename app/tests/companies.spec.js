const { test, expect } = require('@playwright/test');
const path = require('path');

test('companies_data_source', async ({ page }) => {
  const calls = [];
  page.on('dialog', (d) => d.accept());
  await page.addInitScript(() => { window.AICRM_CONFIG = { API_BASE_URL: 'http://localhost:9000/api' }; });
  await page.route('**/api/**', (route) => {
    const req = route.request();
    const url = req.url();
    calls.push({ method: req.method(), url, body: req.postData() });
    const json = (o) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(o) });
    if (/\/auth\/me/.test(url)) return json({ authenticated: true, user: { username: 't', sub: 't', roles: ['admin'], display_name: 'T' } });
    if (/\/auth\/config/.test(url)) return json({ auth_enabled: true });
    if (/\/health/.test(url)) return json({ status: 'ok' });
    if (/\/companies(\b|\/|\?|$)/.test(url)) {
      if (req.method() === 'POST') return json({ id: 'r2', name: 'New Company', created_at: '2025-01-02T00:00:00Z' });
      if (req.method() === 'PUT') return json({ id: 'r1', name: 'Edited Company', updated_at: '2025-01-03T00:00:00Z' });
      if (req.method() === 'DELETE') return json({ ok: true });
      return json([{ id: 'r1', name: 'CA_RENDER_Companies', website: 'V_website', industry: 'V_industry', employee_count: 42, created_at: '2025-01-01T00:00:00Z' }]);
    }
    if (/\/settings/.test(url)) return json({ payload: {} });
    return json([]);
  });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('file://' + path.resolve(__dirname, '..', 'index.html'));
  await page.waitForFunction(() => typeof App !== 'undefined'
    && document.getElementById('page-companies')
    && document.querySelector('.nav-item[data-page="companies"]'), { timeout: 20000 });
  await page.evaluate(() => { App.navigate('companies'); });
  await page.waitForFunction((s) => {
    const el = document.getElementById('companies-list');
    return el && el.textContent.includes(s);
  }, 'CA_RENDER_Companies', { timeout: 20000 });
  const meta = await page.evaluate(() => ({
    pageActive: document.getElementById('page-companies').classList.contains('active'),
    navActive: document.querySelector('.nav-item[data-page="companies"]').classList.contains('active'),
    title: (document.getElementById('page-title') || {}).textContent,
  }));
  expect(meta.pageActive).toBe(true);
  expect(meta.navActive).toBe(true);
  expect(meta.title).toBe('Companies');
  // CREATE — click '+ Add' -> modal -> fill EVERY field -> submit -> POST with all fields
  await page.click('#btn-add-company');
  await page.waitForSelector('#company-form', { timeout: 10000 });
  await page.fill('#company-name', 'New Company');
  await page.fill('#company-website', 'Val_website');
  await page.fill('#company-industry', 'Val_industry');
  await page.fill('#company-employee_count', '7');
  await page.click('#company-form button[type="submit"]');
  await expect.poll(() => calls.some((c) => {
    if (c.method !== 'POST' || !/\/companies(\b|\?|$)/.test(c.url) || !c.body) return false;
    let b; try { b = JSON.parse(c.body); } catch (e) { return false; }
    return b.name === 'New Company' && b.website === 'Val_website' && b.industry === 'Val_industry' && b.employee_count === 7;
  }), { timeout: 10000 }).toBe(true);
  await page.waitForSelector('#company-form', { state: 'detached', timeout: 10000 });
  // EDIT — click the card's edit button (delegated handler reads the escaped id) -> PUT
  await page.click('#companies-list .card-action-btn[data-action="edit"]');
  await page.waitForSelector('#company-form', { timeout: 10000 });
  await page.fill('#company-name', 'Edited Company');
  await page.click('#company-form button[type="submit"]');
  await expect.poll(() => calls.some((c) => c.method === 'PUT' && /\/companies\/r1/.test(c.url)), { timeout: 10000 }).toBe(true);
  await page.waitForSelector('#company-form', { state: 'detached', timeout: 10000 });
  // DELETE — click the card's delete button (confirm auto-accepted) -> DELETE
  await page.click('#companies-list .card-action-btn[data-action="delete"]');
  await expect.poll(() => calls.some((c) => c.method === 'DELETE' && /\/companies\/r1/.test(c.url)), { timeout: 10000 }).toBe(true);
  expect(errors).toEqual([]);
});

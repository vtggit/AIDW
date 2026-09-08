const { test, expect } = require('@playwright/test');

test('issue534 surgical', async ({ page }) => {
    await page.goto('/');

    // Ensure #toast element exists in the DOM
    await page.evaluate(() => {
        if (!document.getElementById('toast')) {
            const el = document.createElement('div');
            el.id = 'toast';
            el.hidden = true;
            document.body.appendChild(el);
        }
    });

    // --- AC1: 403 is classified as 'forbidden', toast stays hidden ---
    const result403 = await page.evaluate(async () => {
        const origFetch = window.fetch;
        window.fetch = async () => ({
            ok: false,
            status: 403,
            json: async () => ({ detail: 'Forbidden' }),
        });
        const result = await ApiClient._execute('GET', '/test-forbidden');
        window.fetch = origFetch;
        return result;
    });

    expect(result403.ok).toBe(false);
    expect(result403._errorType).toBe('forbidden');

    const toastAfter403 = await page.evaluate(() => {
        const t = document.getElementById('toast');
        return { hidden: t.hidden, text: t.textContent };
    });
    expect(toastAfter403.hidden).toBe(true);

    // --- AC2: 401 is classified as 'auth', toast becomes visible ---
    const result401 = await page.evaluate(async () => {
        const origFetch = window.fetch;
        window.fetch = async () => ({
            ok: false,
            status: 401,
            json: async () => ({ detail: 'Unauthorized' }),
        });
        const result = await ApiClient._execute('GET', '/test-auth');
        window.fetch = origFetch;
        return result;
    });

    expect(result401.ok).toBe(false);
    expect(result401._errorType).toBe('auth');

    const toastAfter401 = await page.evaluate(() => {
        const t = document.getElementById('toast');
        return { hidden: t.hidden, text: t.textContent };
    });
    expect(toastAfter401.hidden).toBe(false);
    expect(toastAfter401.text).toBe('Your session has expired \u2014 sign in again.');

    // --- AC2: toast auto-hides within 8 seconds when text is unchanged ---
    await page.waitForFunction(
        () => document.getElementById('toast').hidden === true,
        { timeout: 9000 }
    );

    // --- AC2: if text changes before the 8s window, the hide does NOT fire ---
    await page.evaluate(async () => {
        const origFetch = window.fetch;
        window.fetch = async () => ({
            ok: false,
            status: 401,
            json: async () => ({ detail: 'Unauthorized' }),
        });
        await ApiClient._execute('GET', '/test-auth-2');
        window.fetch = origFetch;
    });

    // Simulate another module replacing the toast text immediately
    await page.evaluate(() => {
        const t = document.getElementById('toast');
        t.textContent = 'Another module notification';
    });

    // Wait past the 8-second auto-hide window
    await page.waitForTimeout(9000);

    const toastAfterOverride = await page.evaluate(() => {
        const t = document.getElementById('toast');
        return { hidden: t.hidden, text: t.textContent };
    });
    expect(toastAfterOverride.hidden).toBe(false);
    expect(toastAfterOverride.text).toBe('Another module notification');
});

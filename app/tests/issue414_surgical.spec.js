const { test, expect } = require('@playwright/test');

test('issue414 surgical', async ({ page }) => {
    await page.goto('/');

    const result = await page.evaluate(async () => {
        let toast = document.getElementById('toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'toast';
            toast.hidden = true;
            document.body.appendChild(toast);
        }

        const originalFetch = window.fetch;
        window.fetch = async () => new Response(
            JSON.stringify({ detail: 'Authentication required.' }),
            { status: 401 }
        );

        try {
            const envelope = await ApiClient.get('/anything');
            return {
                toastText: toast.textContent,
                toastHidden: toast.hidden,
                ok: envelope.ok,
                status: envelope.status
            };
        } finally {
            window.fetch = originalFetch;
        }
    });

    expect(result.ok).toBe(false);
    expect(result.status).toBe(401);
    expect(result.toastHidden).toBe(false);
    expect(result.toastText).toContain('session has expired');
});

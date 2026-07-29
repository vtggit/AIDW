const { test, expect } = require('@playwright/test');

test('issue355 surgical', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => document.getElementById('auth-status')?.textContent.includes('Not signed in'));

    const result = await page.evaluate(() => {
        return new Promise((resolve) => {
            const captures = [];
            const origPost = ApiClient.post;
            const origPut = ApiClient.put;
            ApiClient.post = (...a) => { captures.push({ method: 'post', args: a }); return Promise.resolve({ ok: true, data: {} }); };
            ApiClient.put = (...a) => { captures.push({ method: 'put', args: a }); return Promise.resolve({ ok: true, data: {} }); };

            const host = document.createElement('div');
            Object.assign(host.style, { position: 'absolute', width: '1200px', height: '600px', top: '0', left: '0', zIndex: 9999, background: '#fff' });
            document.body.appendChild(host);

            const d1 = { id: 'D1', name: 'Test Dash', grid_columns: 8 };
            const i1 = { id: 'i1', dashboard_id: 'D1', title: 'Item 1', item_type: 'kpi', position: 0 };
            const i2 = { id: 'i2', dashboard_id: 'D1', title: 'Item 2', item_type: 'bar', position: 1 };
            const items = [i1, i2];
            const layouts = [{ id: 'L1', dashboard_item_id: 'i1', grid_col_span: 4 }];

            host.innerHTML = Warehouse.renderDashboards([d1], items, layouts);
            Warehouse.bindLayoutEditor(host, [d1], items, layouts);

            setTimeout(() => {
                const tile1 = host.querySelector('[data-id="i1"]');
                const preWidth = tile1.getBoundingClientRect().width;

                tile1.querySelector('[data-action="edit-layout"]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
                
                const inputsCount = host.querySelectorAll('input[data-testid^="layout-"]').length;
                const colSpanVal = host.querySelector('input[data-testid="layout-col-span"]').value;

                host.querySelector('[data-action="cancel-layout"]').dispatchEvent(new MouseEvent('click', { bubbles: true }));

                const postCancelInputsCount = host.querySelectorAll('input[data-testid^="layout-"]').length;
                const postCancelWidth = host.querySelector('[data-id="i1"]').getBoundingClientRect().width;

                host.querySelector('[data-action="edit-layout"]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
                host.querySelector('[data-action="save-layout"]').dispatchEvent(new MouseEvent('click', { bubbles: true }));

                const postSaveInputsCount = host.querySelectorAll('input[data-testid^="layout-"]').length;
                
                const drilldown = document.getElementById('drilldown');
                const drillVisible = !!(drilldown && !drilldown.hidden);

                resolve({ inputsCount, colSpanVal, postCancelInputsCount, widthDiff: Math.abs(postCancelWidth - preWidth), postSaveInputsCount, capturesLen: captures.length, drillVisible });
                
                ApiClient.post = origPost; ApiClient.put = origPut; document.body.removeChild(host);
            }, 0);
        });
    });

    expect(result.inputsCount).toBe(3);
    expect(result.colSpanVal).toBe('4');
    expect(result.postCancelInputsCount).toBe(0);
    expect(result.widthDiff).toBeLessThanOrEqual(20);
    expect(result.postSaveInputsCount).toBe(3);
    expect(result.capturesLen).toBe(0);
    expect(result.drillVisible).toBe(false);
});

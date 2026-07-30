const { test, expect } = require('@playwright/test');

test('issue357 surgical', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => document.getElementById('auth-status')?.textContent.includes('Not signed in'));

    const result = await page.evaluate(async () => {
        const captures = [];
        const origPost = ApiClient.post;
        const origPut = ApiClient.put;

        ApiClient.put = (path, body) => {
            captures.push({ method: 'put', path, body });
            return Promise.resolve({ ok: true, data: { id: 'L1', dashboard_item_id: 'i1', grid_col_start: body.grid_col_start, grid_col_span: body.grid_col_span, grid_row_span: body.grid_row_span } });
        };
        ApiClient.post = (path, body) => {
            captures.push({ method: 'post', path, body });
            return Promise.resolve({ ok: true, data: Object.assign({ id: 'L-new' }, body) });
        };

        const host = document.createElement('div');
        Object.assign(host.style, { position: 'absolute', width: '1200px', height: '600px', top: '0', left: '0', zIndex: 9999, background: '#fff' });
        document.body.appendChild(host);

        const d1 = { id: 'D1', name: 'Test Dash', grid_columns: 8 };
        const i1 = { id: 'i1', dashboard_id: 'D1', title: 'Tile One', item_type: 'kpi', position: 0 };
        const i2 = { id: 'i2', dashboard_id: 'D1', title: 'Tile Two', item_type: 'bar', position: 1 };
        const items = [i1, i2];
        const layouts = [{ id: 'L1', dashboard_item_id: 'i1', grid_col_span: 4 }];

        host.innerHTML = Warehouse.renderDashboards([d1], items, layouts);
        Warehouse.bindLayoutEditor(host, [d1], items, layouts);

        await new Promise(r => setTimeout(r, 0));

        const tile1 = host.querySelector('[data-id="i1"]');
        tile1.querySelector('[data-action="edit-layout"]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
        await new Promise(r => setTimeout(r, 0));

        const colSpanInput = host.querySelector('input[data-testid="layout-col-span"]');
        colSpanInput.value = '2';
        colSpanInput.dispatchEvent(new Event('input', { bubbles: true }));

        host.querySelector('[data-action="save-layout"]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
        await new Promise(r => setTimeout(r, 0));

        const tile1Rect = host.querySelector('[data-id="i1"]').getBoundingClientRect();
        const hostWidth = host.getBoundingClientRect().width;

        const tile2 = host.querySelector('[data-id="i2"]');
        tile2.querySelector('[data-action="edit-layout"]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
        await new Promise(r => setTimeout(r, 0));

        host.querySelector('[data-action="save-layout"]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
        await new Promise(r => setTimeout(r, 0));

        const drilldown = document.getElementById('drilldown');

        ApiClient.post = origPost;
        ApiClient.put = origPut;
        document.body.removeChild(host);

        return { captures, tile1Width: tile1Rect.width, hostWidth, drillVisible: !!(drilldown && !drilldown.hidden) };
    });

    expect(result.captures.length).toBe(2);

    expect(result.captures[0].method).toBe('put');
    expect(result.captures[0].path).toBe('/dashboard-item-layouts/L1');
    expect(result.captures[0].body.grid_col_span).toBe(2);

    expect(result.captures[1].method).toBe('post');
    expect(result.captures[1].path).toBe('/dashboard-item-layouts');
    expect(result.captures[1].body.dashboard_item_id).toBe('i2');
    expect(typeof result.captures[1].body.name).toBe('string');
    expect(result.captures[1].body.name.length).toBeGreaterThan(0);
    expect(result.captures[1].body.user_id).toBe(undefined);

    const widthDiff = Math.abs(result.tile1Width - (result.hostWidth / 4));
    expect(widthDiff).toBeLessThanOrEqual(20);

    expect(result.drillVisible).toBe(false);
});

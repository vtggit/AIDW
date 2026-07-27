const { test, expect } = require('@playwright/test');

test('issue347 surgical', async ({ page }) => {
    await page.goto('/');
    
    const results = await page.evaluate(() => {
        const host = document.createElement('div');
        host.style.cssText = 'position:absolute;left:0;top:0;width:1200px;';
        document.body.appendChild(host);

        const dashboards = [
            { id: 'd1', name: 'D1', grid_columns: 12 }
        ];
        const items = [
            { id: 'i1', dashboard_id: 'd1', item_type: 'kpi', title: 'I1' },
            { id: 'i2', dashboard_id: 'd1', item_type: 'bar', title: 'I2', grid_col_span: 6 },
            { id: 'i3', dashboard_id: 'd1', item_type: 'line', title: 'I3', grid_col_span: 6 }
        ];
        const layouts = [
            { dashboard_item_id: 'i1', grid_col_span: 6 },
            { dashboard_item_id: 'i2', grid_col_start: 7 },
            { dashboard_item_id: 'ghost', grid_col_span: 1 }
        ];

        host.innerHTML = Warehouse.renderDashboards(dashboards, items, layouts);
        
        const container = host.querySelector('[data-testid="dashboard"][data-id="d1"] .wh-items');
        const i1Tile = host.querySelector('[data-testid="dashboard-item"][data-id="i1"]');
        const i2Tile = host.querySelector('[data-testid="dashboard-item"][data-id="i2"]');
        const i3Tile = host.querySelector('[data-testid="dashboard-item"][data-id="i3"]');
        
        const cRect = container.getBoundingClientRect();
        const r1 = i1Tile.getBoundingClientRect();
        const r2 = i2Tile.getBoundingClientRect();
        const r3 = i3Tile.getBoundingClientRect();

        host.remove();

        return {
            cWidth: cRect.width,
            i1Width: r1.width,
            i2Width: r2.width,
            i2Left: r2.left - cRect.left,
            i3Width: r3.width
        };
    });

    expect(results.cWidth).toBeGreaterThan(600);
    expect(Math.abs(results.i1Width - results.cWidth / 2)).toBeLessThan(20);
    expect(Math.abs(results.i2Width - results.cWidth / 2)).toBeLessThan(20);
    expect(Math.abs(results.i2Left - results.cWidth / 2)).toBeLessThan(20);
    expect(Math.abs(results.i3Width - results.cWidth / 2)).toBeLessThan(20);
});

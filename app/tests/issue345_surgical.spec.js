const { test, expect } = require('@playwright/test');

test('issue345 surgical', async ({ page }) => {
    await page.goto('/');
    
    const results = await page.evaluate(() => {
        const host = document.createElement('div');
        host.style.cssText = 'position:absolute;left:0;top:0;width:1200px;';
        document.body.appendChild(host);

        const dashboards = [
            { id: 'd1', name: 'D1', grid_columns: 12 },
            { id: 'd2', name: 'D2', grid_columns: 4 }
        ];
        const items = [
            { id: 'i1', dashboard_id: 'd1', item_type: 'kpi', title: 'Bare' },
            { id: 'i2', dashboard_id: 'd1', item_type: 'bar', title: 'Span6', grid_col_span: 6 },
            { id: 'i3', dashboard_id: 'd1', item_type: 'line', title: 'Start7', grid_col_start: 7, grid_col_span: 6 },
            { id: 'i4', dashboard_id: 'd2', item_type: 'pie', title: 'D2Span2', grid_col_span: 2 }
        ];

        host.innerHTML = Warehouse.renderDashboards(dashboards, items);
        
        const d1Container = host.querySelector('[data-testid="dashboard"][data-id="d1"] .wh-items');
        const bareTile = host.querySelector('[data-testid="dashboard-item"][data-id="i1"]');
        const span6Tile = host.querySelector('[data-testid="dashboard-item"][data-id="i2"]');
        const start7Tile = host.querySelector('[data-testid="dashboard-item"][data-id="i3"]');
        
        const d2Container = host.querySelector('[data-testid="dashboard"][data-id="d2"] .wh-items');
        const d2Span2Tile = host.querySelector('[data-testid="dashboard-item"][data-id="i4"]');

        const d1Rect = d1Container.getBoundingClientRect();
        const bareRect = bareTile.getBoundingClientRect();
        const span6Rect = span6Tile.getBoundingClientRect();
        const start7Rect = start7Tile.getBoundingClientRect();
        
        const d2Rect = d2Container.getBoundingClientRect();
        const d2Span2Rect = d2Span2Tile.getBoundingClientRect();

        host.remove();

        return {
            d1Width: d1Rect.width,
            bareWidth: bareRect.width,
            span6Width: span6Rect.width,
            start7Left: start7Rect.left - d1Rect.left,
            d2HalfWidth: d2Rect.width / 2,
            d2Span2Width: d2Span2Rect.width
        };
    });

    expect(results.d1Width).toBeGreaterThan(600);
    expect(Math.abs(results.bareWidth - results.d1Width)).toBeLessThan(20);
    expect(Math.abs(results.span6Width - results.d1Width / 2)).toBeLessThan(20);
    expect(Math.abs(results.start7Left - results.d1Width / 2)).toBeLessThan(20);
    expect(Math.abs(results.d2Span2Width - results.d2HalfWidth)).toBeLessThan(20);
});

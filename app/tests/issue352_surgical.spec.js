const { test, expect } = require('@playwright/test');

test('issue352 surgical', async ({ page }) => {
    await page.goto('/');
    const results = await page.evaluate(() => {
        const host1 = document.createElement('div');
        host1.style.cssText = 'position:absolute;left:0;top:0;width:1200px;';
        document.body.appendChild(host1);

        const d1 = { id: 'd1', name: 'D1', grid_columns: 8 };
        const items = [
            { id: 'i1', dashboard_id: 'd1', item_type: 'kpi', title: 'I1' },
            { id: 'i2', dashboard_id: 'd1', item_type: 'bar', title: 'I2' }
        ];
        const layouts = [{ dashboard_item_id: 'i1', grid_col_start: 3, grid_col_span: 4 }];

        host1.innerHTML = Warehouse.renderDashboards([d1], items, layouts, 'i1');

        const i1Tile = host1.querySelector('[data-testid="dashboard-item"][data-id="i1"]');
        const i2Tile = host1.querySelector('[data-testid="dashboard-item"][data-id="i2"]');

        const colStartInp = i1Tile.querySelector('[data-testid="layout-col-start"]');
        const colSpanInp = i1Tile.querySelector('[data-testid="layout-col-span"]');
        const rowSpanInp = i1Tile.querySelector('[data-testid="layout-row-span"]');

        const host2 = document.createElement('div');
        host2.style.cssText = 'position:absolute;left:0;top:0;width:1200px;';
        document.body.appendChild(host2);
        host2.innerHTML = Warehouse.renderDashboards([d1], items, layouts, null);
        const i2TileNoEdit = host2.querySelector('[data-testid="dashboard-item"][data-id="i2"]');

        const r2 = i2Tile.getBoundingClientRect();
        const r2n = i2TileNoEdit.getBoundingClientRect();
        const btns = host1.querySelectorAll('[data-action="edit-layout"]');
        const btnHeights = Array.from(btns).map(b => b.getBoundingClientRect().height);

        host1.remove();
        host2.remove();

        return {
            i1InputCount: i1Tile.querySelectorAll('input[data-testid]').length,
            i2InputCount: i2Tile.querySelectorAll('input[data-testid]').length,
            colStartVal: colStartInp.value,
            colSpanVal: colSpanInp.value,
            rowSpanVal: rowSpanInp.value,
            colStartMax: colStartInp.getAttribute('max'),
            colSpanMax: colSpanInp.getAttribute('max'),
            hasSaveBtn: !!i1Tile.querySelector('[data-action="save-layout"]'),
            hasCancelBtn: !!i1Tile.querySelector('[data-action="cancel-layout"]'),
            i2WidthEdit: r2.width,
            i2WidthNoEdit: r2n.width,
            editLayoutBtnCount: btns.length,
            btnHeights
        };
    });

    expect(results.editLayoutBtnCount).toBe(2);
    expect(results.btnHeights.every(h => h > 0)).toBe(true);
    expect(results.i1InputCount).toBe(3);
    expect(results.i2InputCount).toBe(0);
    expect(results.colStartVal).toBe('3');
    expect(results.colSpanVal).toBe('4');
    expect(results.rowSpanVal).toBe('1');
    expect(results.colStartMax).toBe('8');
    expect(results.colSpanMax).toBe('8');
    expect(results.hasSaveBtn).toBe(true);
    expect(results.hasCancelBtn).toBe(true);
    expect(Math.abs(results.i2WidthEdit - results.i2WidthNoEdit)).toBeLessThan(20);
});

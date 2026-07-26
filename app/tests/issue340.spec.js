const { test, expect } = require('@playwright/test');
const { Drilldown } = require('../js/drilldown');

test('issue340 freeform', () => {
  let capturedWidth;

  global.Charts = {
    renderBar(_series, _meta, chartWidth) {
      capturedWidth = chartWidth;
      return '<svg></svg>';
    },
  };

  const baseDetail = {
    title: 'Test',
    source: 'landed',
    total_rows: 100,
    refreshed_at: '2024-01-01',
    dimension: 'category',
    aggregation: 'sum',
    series: [{ label: 'A', value: 10 }],
  };

  // 4-column tile → 4 * 160 = 640 (within bounds, no clamp)
  Drilldown.renderDetail({ ...baseDetail, grid_col_span: 4 });
  expect(capturedWidth).toBe(640);

  // 1-column tile → 1 * 160 = 160, clamped up to 640 (min)
  Drilldown.renderDetail({ ...baseDetail, grid_col_span: 1 });
  expect(capturedWidth).toBe(640);

  // 8-column tile → 8 * 160 = 1280 (at upper bound)
  Drilldown.renderDetail({ ...baseDetail, grid_col_span: 8 });
  expect(capturedWidth).toBe(1280);

  // 12-column tile → 12 * 160 = 1920, clamped down to 1280 (max)
  Drilldown.renderDetail({ ...baseDetail, grid_col_span: 12 });
  expect(capturedWidth).toBe(1280);

  // No grid_col_span → undefined (Charts defaults to 640)
  Drilldown.renderDetail(baseDetail);
  expect(capturedWidth).toBeUndefined();

  // null grid_col_span → undefined (same as missing)
  Drilldown.renderDetail({ ...baseDetail, grid_col_span: null });
  expect(capturedWidth).toBeUndefined();

  delete global.Charts;
});

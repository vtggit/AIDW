const { test, expect } = require('@playwright/test');
const { Drilldown } = require('../js/drilldown');
const { Charts } = require('../js/charts');

test('issue340 freeform', () => {
  // Expose Charts globally so drilldown.js can resolve the unbound identifier in Node.
  global.Charts = Charts;

  const originalRenderBar = Charts.renderBar;
  let lastCallArgs = null;

  Charts.renderBar = function (...args) {
    lastCallArgs = args;
    return originalRenderBar.apply(this, args);
  };

  // --- Case 1: payload carries grid_col_span => proportionally wider chart ---
  const dataWithSpan = {
    title: 'Revenue by Region',
    source: 'landed',
    total_rows: 4200,
    refreshed_at: '2025-01-01T00:00:00Z',
    dimension: 'region',
    aggregation: 'sum',
    grid_col_span: 2,
    series: [
      { label: 'North', value: 100 },
      { label: 'South', value: 200 },
    ],
    truncated: false,
  };

  Drilldown.renderDetail(dataWithSpan);

  expect(lastCallArgs).not.toBeNull();
  expect(lastCallArgs[2]).toBe(1280);

  // --- Case 2: no grid_col_span => default width (undefined, so Charts uses 640) ---
  const dataWithoutSpan = {
    title: 'Units by Category',
    source: 'live',
    dimension: 'category',
    aggregation: 'count',
    series: [
      { label: 'A', value: 50 },
      { label: 'B', value: 75 },
    ],
    truncated: false,
  };

  lastCallArgs = null;
  Drilldown.renderDetail(dataWithoutSpan);

  expect(lastCallArgs).not.toBeNull();
  // When grid_col_span is absent, chartWidth should be undefined (default path)
  expect(lastCallArgs[2]).toBeUndefined();

  // --- Case 3: grid_col_span of 1 => same as default width (640) ---
  const dataSpanOne = {
    title: 'Count by Status',
    source: 'landed',
    total_rows: 100,
    refreshed_at: '2025-06-01T00:00:00Z',
    dimension: 'status',
    aggregation: 'count',
    grid_col_span: 1,
    series: [
      { label: 'Open', value: 30 },
      { label: 'Closed', value: 70 },
    ],
    truncated: false,
  };

  lastCallArgs = null;
  Drilldown.renderDetail(dataSpanOne);

  expect(lastCallArgs).not.toBeNull();
  expect(lastCallArgs[2]).toBe(640);

  // Restore original
  Charts.renderBar = originalRenderBar;
});

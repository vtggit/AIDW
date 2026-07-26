'use strict';

const { test, expect } = require('@playwright/test');
const { Charts } = require('../js/charts');

test('issue335 freeform', () => {
  const series = [['Alpha', 10], ['Beta', 20]];
  const meta = { title: 'Test Chart', total_rows: 42, refreshed_at: '2025-01-01' };

  // Default dimensions (no width/height supplied) should produce 640x360
  const defaultSvg = Charts.renderBar(series, meta);
  expect(defaultSvg).toContain('viewBox="0 0 640 360"');
  expect(defaultSvg).toContain('width="640"');
  expect(defaultSvg).toContain('height="360"');

  // Title should be centred at W/2 = 320 with defaults
  expect(defaultSvg).toContain('x="320" y="25" text-anchor="middle" font-size="16" font-weight="bold">Test Chart</text>');

  // Footer should sit near the bottom: H - 10 = 350
  expect(defaultSvg).toMatch(/y="350"[^>]*text-anchor="middle"/);

  // Custom dimensions (800x480) should propagate through every derived measurement
  const customSvg = Charts.renderBar(series, meta, 800, 480);
  expect(customSvg).toContain('viewBox="0 0 800 480"');
  expect(customSvg).toContain('width="800"');
  expect(customSvg).toContain('height="480"');

  // Title centred at W/2 = 400 for custom width
  expect(customSvg).toContain('x="400" y="25" text-anchor="middle" font-size="16" font-weight="bold">Test Chart</text>');

  // Footer should sit near the bottom: H - 10 = 470 for custom height
  expect(customSvg).toMatch(/y="470"[^>]*text-anchor="middle"/);

  // Verify that default and custom SVGs are genuinely different (not just a copy)
  expect(defaultSvg).not.toBe(customSvg);

  // Edge case: passing null/undefined should fall back to defaults
  const nullWidthSvg = Charts.renderBar(series, meta, null, undefined);
  expect(nullWidthSvg).toContain('viewBox="0 0 640 360"');

  const zeroHeightSvg = Charts.renderBar(series, meta, 500, 0);
  // Zero is a valid number but produces viewBox with height=0
  expect(zeroHeightSvg).toContain('height="0"');
});

const { test, expect } = require('@playwright/test');

test('issue392 freeform', async ({ page }) => {
  await page.goto('/');
  await page.addScriptTag({ url: '/js/sequence_runs.js' });
  await page.waitForFunction(() => window.SequenceRuns !== undefined);

  // (1) renderRuns with two runs: completed and null-status → pending
  const runRows = await page.evaluate(() => {
    const host = document.createElement('div');
    host.setAttribute('data-panel', 'sequence-runs');
    document.body.appendChild(host);
    const runs = [
      { id: 'r1', name: 'Run A', status: 'completed', started_at: '2024-01-01T00:00:00Z', finished_at: '2024-01-01T00:01:00Z' },
      { id: 'r2', name: 'Run B', status: null, started_at: null, finished_at: null },
    ];
    host.innerHTML = window.SequenceRuns.renderRuns(runs);
    const rows = host.querySelectorAll('[data-testid="run-row"]');
    return {
      count: rows.length,
      statuses: Array.from(rows).map(row => row.querySelector('[data-testid="run-status"]').dataset.status),
    };
  });
  expect(runRows.count).toBe(2);
  expect(runRows.statuses[0]).toBe('completed');
  expect(runRows.statuses[1]).toBe('pending');

  // (2) renderRuns([]) → runs-empty
  const emptyResult = await page.evaluate(() => {
    const host = document.createElement('div');
    host.setAttribute('data-panel', 'sequence-runs');
    document.body.appendChild(host);
    host.innerHTML = window.SequenceRuns.renderRuns([]);
    return host.querySelector('[data-testid="runs-empty"]') !== null;
  });
  expect(emptyResult).toBe(true);

  // (3) renderRunSteps with two steps: failed and skipped
  const stepRows = await page.evaluate(() => {
    const host = document.createElement('div');
    host.setAttribute('data-panel', 'sequence-runs');
    document.body.appendChild(host);
    const steps = [
      { step_id: 's1', status: 'failed', label: 'step 1' },
      { step_id: 's2', status: 'skipped', label: 'step 2' },
    ];
    host.innerHTML = window.SequenceRuns.renderRunSteps(steps);
    const rows = host.querySelectorAll('[data-testid="run-step-row"]');
    return {
      count: rows.length,
      statuses: Array.from(rows).map(row => row.dataset.status),
    };
  });
  expect(stepRows.count).toBe(2);
  expect(stepRows.statuses[0]).toBe('failed');
  expect(stepRows.statuses[1]).toBe('skipped');

  // (4) isTerminal checks
  const terminalResults = await page.evaluate(() => {
    return {
      completed: window.SequenceRuns.isTerminal('completed'),
      failed: window.SequenceRuns.isTerminal('failed'),
      pending: window.SequenceRuns.isTerminal('pending'),
      running: window.SequenceRuns.isTerminal('running'),
      nullVal: window.SequenceRuns.isTerminal(null),
    };
  });
  expect(terminalResults.completed).toBe(true);
  expect(terminalResults.failed).toBe(true);
  expect(terminalResults.pending).toBe(false);
  expect(terminalResults.running).toBe(false);
  expect(terminalResults.nullVal).toBe(false);
});

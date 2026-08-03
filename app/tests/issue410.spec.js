const { test, expect } = require('@playwright/test');

test('issue410 freeform', async ({ page }) => {
  await page.goto('/');
  await page.addScriptTag({ url: '/js/sequences.js' });
  await page.waitForFunction(() => typeof window.Sequences !== 'undefined');

  const results = await page.evaluate(() => {
    const hostList = document.createElement('div');
    hostList.innerHTML = window.Sequences.renderList([]);
    const listText = hostList.textContent;

    const hostFlow = document.createElement('div');
    hostFlow.innerHTML = window.Sequences.renderFlow('not xml at all');
    const flowText = hostFlow.textContent;

    return { listText, flowText };
  });

  expect(results.listText).toContain('No load sequences yet.');
  expect(results.flowText).toContain('Could not render the flow diagram.');
});

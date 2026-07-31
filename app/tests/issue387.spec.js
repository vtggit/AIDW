const { test, expect } = require('@playwright/test');

test('issue387 freeform', async ({ page }) => {
  await page.goto('/');
  await page.addScriptTag({ url: '/js/sequences.js' });

  // Wait for Sequences to be available on window
  await page.waitForFunction(() => typeof window.Sequences !== 'undefined');

  // --- renderList with two sequences ---
  const listResult = await page.evaluate(() => {
    const host = document.createElement('div');
    const sequences = [
      { id: 'seq-001', name: 'First Sequence', description: 'desc1' },
      { id: 'seq-002', name: 'Second Sequence', description: 'desc2' },
    ];
    host.innerHTML = window.Sequences.renderList(sequences);

    const rows = host.querySelectorAll('[data-testid="sequence-row"]');
    return {
      rowCount: rows.length,
      row1Id: rows[0].dataset.id,
      row1Text: rows[0].textContent,
      row2Id: rows[1].dataset.id,
      row2Text: rows[1].textContent,
    };
  });

  expect(listResult.rowCount).toBe(2);
  expect(listResult.row1Id).toBe('seq-001');
  expect(listResult.row1Text).toBe('First Sequence');
  expect(listResult.row2Id).toBe('seq-002');
  expect(listResult.row2Text).toBe('Second Sequence');

  // --- renderList with empty array ---
  const emptyResult = await page.evaluate(() => {
    const host = document.createElement('div');
    host.innerHTML = window.Sequences.renderList([]);
    return host.querySelector('[data-testid="sequences-empty"]') !== null;
  });
  expect(emptyResult).toBe(true);

  // --- renderFlow with BPMN fixture containing two serviceTasks ---
  const bpmnXml = `<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="test-process">
    <bpmn:serviceTask name="step 1"/>
    <bpmn:serviceTask name="step 2"/>
  </bpmn:process>
</definitions>`;

  const flowResult = await page.evaluate((xml) => {
    const host = document.createElement('div');
    host.innerHTML = window.Sequences.renderFlow(xml);

    const steps = host.querySelectorAll('[data-testid="flow-step"]');
    return {
      startCount: host.querySelectorAll('[data-testid="flow-start"]').length,
      stepCount: steps.length,
      endCount: host.querySelectorAll('[data-testid="flow-end"]').length,
      arrowCount: host.querySelectorAll('.wh-flow-arrow').length,
      step1Text: steps[0].textContent,
      step2Text: steps[1].textContent,
    };
  }, bpmnXml);

  expect(flowResult.startCount).toBe(1);
  expect(flowResult.stepCount).toBe(2);
  expect(flowResult.endCount).toBe(1);
  expect(flowResult.arrowCount).toBe(3);
  expect(flowResult.step1Text).toBe('step 1');
  expect(flowResult.step2Text).toBe('step 2');

  // --- renderFlow with invalid XML ---
  const errorResult = await page.evaluate(() => {
    const host = document.createElement('div');
    host.innerHTML = window.Sequences.renderFlow('not xml at all');
    return host.querySelector('[data-testid="flow-error"]') !== null;
  });
  expect(errorResult).toBe(true);

  // --- downloadName ---
  const nameResult = await page.evaluate(() => {
    return window.Sequences.downloadName('load_sequence_abc');
  });
  expect(nameResult).toBe('load_sequence_abc.bpmn');
});

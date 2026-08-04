const { test, expect } = require('@playwright/test');

test('issue412 freeform', async ({ page }) => {
  await page.goto('/');
  await page.addScriptTag({ url: '/js/sequences.js' });
  await page.waitForFunction(() => typeof window.Sequences !== 'undefined');

  const result = await page.evaluate(() => {
    const Sequences = window.Sequences;
    const hostDiv = document.createElement('div');

    // Test empty list rendering
    const emptyHtml = Sequences.renderList([]);
    hostDiv.innerHTML = emptyHtml;

    const createBtnEmpty = hostDiv.querySelector('[data-testid="sequence-create"]');
    const nameInputEmpty = hostDiv.querySelector('[data-testid="sequence-name-input"]');
    const emptyState = hostDiv.querySelector('[data-testid="sequences-empty"]');

    // Test list with two sequences rendering
    const seqs = [
      { id: 'seq-uuid-1', name: 'Sequence One' },
      { id: 'seq-uuid-2', name: 'Sequence Two' }
    ];
    const listHtml = Sequences.renderList(seqs);
    hostDiv.innerHTML = listHtml;

    const rows = hostDiv.querySelectorAll('[data-testid="sequence-row"]');
    const createBtnList = hostDiv.querySelector('[data-testid="sequence-create"]');

    const rowIds = Array.from(rows).map(r => r.getAttribute('data-id'));

    return {
      empty: {
        hasCreateButton: !!createBtnEmpty,
        createButtonText: createBtnEmpty ? createBtnEmpty.textContent : null,
        hasNameInput: !!nameInputEmpty,
        nameInputIsInputTag: nameInputEmpty && nameInputEmpty.tagName.toLowerCase() === 'input',
        hasEmptyState: !!emptyState,
        emptyStateText: emptyState ? emptyState.textContent : null,
      },
      list: {
        rowCount: rows.length,
        rowIds: rowIds,
        hasCreateButtonInList: !!createBtnList,
      }
    };
  });

  // Assertions for empty state
  expect(result.empty.hasCreateButton).toBe(true);
  expect(result.empty.createButtonText).toContain('Create sequence');
  expect(result.empty.hasNameInput).toBe(true);
  expect(result.empty.nameInputIsInputTag).toBe(true);
  expect(result.empty.hasEmptyState).toBe(true);
  expect(result.empty.emptyStateText).toContain('No load sequences yet.');

  // Assertions for list state
  expect(result.list.rowCount).toBe(2);
  expect(result.list.rowIds).toEqual(['seq-uuid-1', 'seq-uuid-2']);
  expect(result.list.hasCreateButtonInList).toBe(true);
});

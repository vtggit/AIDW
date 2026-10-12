'use strict';

const Sequences = {
  _esc(str) {
    const s = String(str);
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  },

  renderList(sequences) {
    const createBtn = Auth.isAdmin() ? '<button data-testid="sequence-create" data-requires-role="admin">Create sequence</button>' : '';
    const input = '<input data-testid="sequence-name-input" placeholder="Sequence name">';
    const emptyNote = '<div data-testid="sequences-empty">No load sequences yet.</div>';
    const items = Array.isArray(sequences) ? sequences : [];
    if (items.length === 0) {
      return input + createBtn + emptyNote;
    }
    let html = '';
    for (let i = 0; i < items.length; i++) {
      const seq = items[i];
      // A null hole in the array is not a sequence: skip it rather than
      // crash reading its id and name.
      if (!seq) continue;
      html += `<div class="wh-seq-row" data-testid="sequence-row" data-id="${this._esc(seq.id)}">${this._esc(seq.name)}</div>`;
    }
    if (html === '') {
      // Every element was null: the terminal state is the empty note.
      return input + createBtn + emptyNote;
    }
    return input + createBtn + html;
  },

  renderFlow(bpmnXml) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(bpmnXml, 'application/xml');

    // Check for parse errors: a failed parse yields an error document
    // whose ROOT element is <parsererror>.  Check the root only, so a
    // <parsererror> element inside the (valid) user content is not
    // mistaken for a parse failure.
    const root = doc.documentElement;
    if (!root || root.localName === 'parsererror') {
      return '<div data-testid="flow-error">Could not render the flow diagram.</div>';
    }

    // Find process elements using namespace-aware lookup
    const bpmnNs = 'http://www.omg.org/spec/BPMN/20100524/MODEL';
    let processes = doc.getElementsByTagNameNS(bpmnNs, 'process');

    // Fallback: try prefixed name or any namespace
    if (processes.length === 0) {
      processes = doc.getElementsByTagName('bpmn:process');
    }
    if (processes.length === 0) {
      processes = doc.getElementsByTagNameNS('*', 'process');
    }

    if (processes.length === 0) {
      return '<div data-testid="flow-error">Could not render the flow diagram.</div>';
    }

    // Find serviceTask elements in document order
    let tasks = doc.getElementsByTagNameNS(bpmnNs, 'serviceTask');
    if (tasks.length === 0) {
      tasks = doc.getElementsByTagName('bpmn:serviceTask');
    }
    if (tasks.length === 0) {
      tasks = doc.getElementsByTagNameNS('*', 'serviceTask');
    }

    // Build vertical flow layout: start → [arrow + step]* → arrow → end
    let html = '<div class="wh-flow">';
    html += '<div class="wh-flow-node" data-testid="flow-start"></div>';

    for (let i = 0; i < tasks.length; i++) {
      const name = tasks[i].getAttribute('name') || '';
      html += '<div class="wh-flow-arrow"></div>';
      html += `<div class="wh-flow-node" data-testid="flow-step">${this._esc(name)}</div>`;
    }

    html += '<div class="wh-flow-arrow"></div>';
    html += '<div class="wh-flow-node" data-testid="flow-end"></div>';
    html += '</div>';

    return html;
  },

  downloadName(processKey) {
    return processKey + '.bpmn';
  },

  /**
   * While the shell shows the tool's section, mark main.wh-main so
   * css/sequences.css can lock the tool to the viewport height
   * (desktop): the document and the main .aidw-scroll region must not
   * scroll — only the list pane's rows and the detail pane do. The
   * shell toggles the section's hidden attribute when switching tools;
   * the observer follows it.
   */
  _bindFit(section) {
    if (!section || !section.closest) return;
    const main = section.closest('main.wh-main');
    if (!main) return;
    const sync = () => main.classList.toggle('sequences-open', !section.hidden);
    sync();
    if (typeof MutationObserver === 'undefined') return;
    const observer = new MutationObserver(sync);
    observer.observe(section, { attributes: true, attributeFilter: ['hidden'] });
  },

  /**
   * Render the list into the pane: the name input and the Create button
   * (renderList emits them first) move into the fixed head, and the
   * rows — or the empty/error note — go into the rows area that scrolls
   * on its own below them.
   */
  _commitList(rowsEl, headEl, data) {
    const tmp = document.createElement('div');
    tmp.innerHTML = this.renderList(data);
    if (headEl) {
      headEl.textContent = '';
      const input = tmp.querySelector('[data-testid="sequence-name-input"]');
      const createBtn = tmp.querySelector('[data-testid="sequence-create"]');
      if (input) headEl.appendChild(input);
      if (createBtn) headEl.appendChild(createBtn);
    }
    rowsEl.innerHTML = '';
    Array.from(tmp.children).forEach((child) => {
      if (child.matches('[data-testid="sequence-name-input"], [data-testid="sequence-create"]')) return;
      rowsEl.appendChild(child);
    });
  },

  /** The chosen row carries aria-current="true"; the others lose it. */
  _markCurrent(rowsEl, row) {
    rowsEl
      .querySelectorAll('[data-testid="sequence-row"][aria-current="true"]')
      .forEach((r) => r.removeAttribute('aria-current'));
    if (row) row.setAttribute('aria-current', 'true');
  },

  async init() {
    const rowsEl = document.querySelector('[data-panel="sequences"]');
    if (!rowsEl) return;

    const listPane = rowsEl.closest('.seq-list-pane') || rowsEl;
    const headEl = listPane.querySelector('[data-testid="seq-list-head"]');
    const section = rowsEl.closest('section.wh-panel');
    const detailPane = section ? section.querySelector('[data-testid="seq-detail-pane"]') : null;

    this._bindFit(section);

    const result = await ApiClient.get('/load-sequences');
    if (!result.ok) {
      rowsEl.innerHTML = '<div data-testid="sequences-error">Could not load sequences.</div>';
      return;
    }

    this._commitList(rowsEl, headEl, result.data);

    // A monotonically increasing token per row selection: an in-flight
    // response from an earlier click must not overwrite the detail of a
    // row chosen afterwards.
    let selectionToken = 0;

    // Bind delegated click handler for sequence rows
    listPane.addEventListener('click', async (e) => {
      const row = e.target.closest('[data-testid="sequence-row"]');
      if (!row) return;

      const id = row.dataset.id;
      const token = ++selectionToken;
      const res = await ApiClient.get(`/load-sequences/${id}/bpmn`);
      // A later row selection superseded this response: drop it.
      if (token !== selectionToken) return;
      if (!res.ok) return;

      const { process_key, bpmn_xml } = res.data;

      this._markCurrent(rowsEl, row);

      // Render the flow into the detail pane (replacing any previous one)
      let detailEl = detailPane ? detailPane.querySelector('[data-testid="sequence-detail"]') : null;
      if (!detailEl) {
        detailEl = document.createElement('div');
        detailEl.setAttribute('data-testid', 'sequence-detail');
        (detailPane || section || listPane).appendChild(detailEl);
      }
      detailEl.innerHTML = this.renderFlow(bpmn_xml);

      // Show the BPMN download control — copy wizard.js downloadXml idiom
      let downloadBtn = detailPane ? detailPane.querySelector('[data-testid="bpmn-download"]') : null;
      if (!downloadBtn) {
        downloadBtn = document.createElement('button');
        downloadBtn.setAttribute('data-testid', 'bpmn-download');
        downloadBtn.textContent = 'Download BPMN';
        (detailPane || section || listPane).appendChild(downloadBtn);
      }
      downloadBtn.hidden = false;

      const blob = new Blob([bpmn_xml], { type: 'application/xml' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = this.downloadName(process_key);

      downloadBtn.onclick = () => {
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      };
    });

    // Bind delegated click handler for create sequence button
    listPane.addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-testid="sequence-create"]');
      if (!btn) return;

      const input = listPane.querySelector('[data-testid="sequence-name-input"]');
      const name = input.value.trim();
      if (!name) return;

      const createResult = await ApiClient.post('/load-sequences', { name });
      if (!createResult.ok) {
        rowsEl.innerHTML = '<div data-testid="sequences-error">Could not load sequences.</div>';
        return;
      }

      const refreshResult = await ApiClient.get('/load-sequences');
      if (!refreshResult.ok) {
        rowsEl.innerHTML = '<div data-testid="sequences-error">Could not load sequences.</div>';
        return;
      }

      this._commitList(rowsEl, headEl, refreshResult.data);
    });
  },
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Sequences };
}
if (typeof window !== 'undefined') {
  window.Sequences = Sequences;
}

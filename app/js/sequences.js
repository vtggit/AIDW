'use strict';

const Sequences = {
  _esc(str) {
    const s = String(str);
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  },

  renderList(sequences) {
    if (!sequences || sequences.length === 0) {
      return '<div data-testid="sequences-empty"></div>';
    }
    let html = '';
    for (let i = 0; i < sequences.length; i++) {
      const seq = sequences[i];
      html += `<div class="wh-seq-row" data-testid="sequence-row" data-id="${this._esc(seq.id)}">${this._esc(seq.name)}</div>`;
    }
    return html;
  },

  renderFlow(bpmnXml) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(bpmnXml, 'application/xml');

    // Check for parse errors
    if (doc.querySelector('parsererror')) {
      return '<div data-testid="flow-error"></div>';
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
      return '<div data-testid="flow-error"></div>';
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

  async init() {
    const container = document.querySelector('[data-panel="sequences"]');
    if (!container) return;

    const result = await ApiClient.get('/load-sequences');
    if (!result.ok) {
      container.innerHTML = '<div data-testid="sequences-error"></div>';
      return;
    }

    container.innerHTML = this.renderList(result.data);

    // Bind delegated click handler for sequence rows
    container.addEventListener('click', async (e) => {
      const row = e.target.closest('[data-testid="sequence-row"]');
      if (!row) return;

      const id = row.dataset.id;
      const res = await ApiClient.get(`/load-sequences/${id}/bpmn`);
      if (!res.ok) return;

      const { process_key, bpmn_xml } = res.data;

      // Render flow into sequence-detail element inside the container
      let detailEl = container.querySelector('[data-testid="sequence-detail"]');
      if (!detailEl) {
        detailEl = document.createElement('div');
        detailEl.setAttribute('data-testid', 'sequence-detail');
        container.appendChild(detailEl);
      }
      detailEl.innerHTML = this.renderFlow(bpmn_xml);

      // Show BPMN download control — copy wizard.js downloadXml idiom
      let downloadBtn = container.querySelector('[data-testid="bpmn-download"]');
      if (!downloadBtn) {
        downloadBtn = document.createElement('button');
        downloadBtn.setAttribute('data-testid', 'bpmn-download');
        downloadBtn.textContent = 'Download BPMN';
        container.appendChild(downloadBtn);
      }

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
  },
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Sequences };
}
if (typeof window !== 'undefined') {
  window.Sequences = Sequences;
}

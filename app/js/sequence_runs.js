'use strict';

const SequenceRuns = {
  _esc(str) {
    const s = String(str);
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  },

  isTerminal(status) {
    return status === 'completed' || status === 'failed';
  },

  _effectiveStatus(status) {
    if (status == null || status === '') {
      return 'pending';
    }
    return status;
  },

  renderRuns(runs) {
    if (!runs || runs.length === 0) {
      return '<div data-testid="runs-empty">No runs yet</div>';
    }
    let html = '';
    for (let i = 0; i < runs.length; i++) {
      const run = runs[i];
      const effectiveStatus = this._effectiveStatus(run.status);
      const startedAt = run.started_at ? ` ${this._esc(run.started_at)}` : '';
      const finishedAt = run.finished_at ? ` ${this._esc(run.finished_at)}` : '';

      html += `<div class="wh-run-row" data-testid="run-row" data-id="${this._esc(run.id)}">`;
      html += `${this._esc(run.name)}`;
      html += `<span data-testid="run-status" data-status="${effectiveStatus}">${this._esc(effectiveStatus)}</span>`;
      if (startedAt || finishedAt) {
        html += `<div>${startedAt}${finishedAt}</div>`;
      }
      html += `</div>`;
    }
    return html;
  },

  renderRunSteps(steps) {
    if (!steps || steps.length === 0) {
      return '<div data-testid="run-steps-empty">No steps recorded</div>';
    }
    let html = '';
    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      const effectiveStatus = this._effectiveStatus(step.status);
      const label = step.label || step.name || '';

      html += `<div data-testid="run-step-row" data-status="${effectiveStatus}">`;
      html += `${this._esc(label)}`;
      html += `</div>`;
    }
    return html;
  },

  _clearPolling() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
  },

  async init() {
    const container = document.querySelector('[data-panel="sequence-runs"]');
    if (!container) return;

    let selectedSequenceId = null;

    // Bind delegated click listener for sequence rows (rendered by sequences.js)
    document.addEventListener('click', async (e) => {
      const row = e.target.closest('[data-testid="sequence-row"]');
      if (!row) return;

      this._clearPolling();
      selectedSequenceId = row.dataset.id;

      // Fetch all runs and client-filter by sequence_id
      const res = await ApiClient.get('/sequence-runs');
      if (!res.ok) {
        container.innerHTML = '<div data-testid="runs-error">Could not load runs.</div>';
        return;
      }

      const allRuns = Array.isArray(res.data) ? res.data : [];
      const filteredRuns = allRuns.filter(r => r.sequence_id === selectedSequenceId);

      // Render history + execute button
      let html = this.renderRuns(filteredRuns);
      html += `<button data-testid="sequence-execute">Execute</button>`;
      container.innerHTML = html;

      // Bind execute click
      const executeBtn = container.querySelector('[data-testid="sequence-execute"]');
      if (!executeBtn) return;

      executeBtn.addEventListener('click', async () => {
        this._clearPolling();

        // Create run
        const createRes = await ApiClient.post('/sequence-runs', {
          name: 'run-' + Date.now(),
          sequence_id: selectedSequenceId,
        });

        if (!createRes.ok) {
          container.innerHTML += '<div data-testid="runs-error">Could not load runs.</div>';
          return;
        }

        const run = createRes.data;
        const runId = run.id;

        // Execute run
        const execRes = await ApiClient.post(`/sequence-runs/${runId}/execute`);

        if (!execRes.ok) {
          container.innerHTML += '<div data-testid="runs-error">Could not load runs.</div>';
          return;
        }

        const finalRun = execRes.data;
        const steps = finalRun.steps || [];

        // Render steps + re-render history
        let html2 = this.renderRunSteps(steps);
        html2 += this.renderRuns(filteredRuns.concat([finalRun]));
        container.innerHTML = html2;

        // Poll until terminal
        const effectiveStatus = this._effectiveStatus(finalRun.status);
        if (this.isTerminal(effectiveStatus)) {
          return;
        }

        this._pollInterval = setInterval(async () => {
          const pollRes = await ApiClient.get(`/sequence-runs/${runId}`);
          if (!pollRes.ok) {
            this._clearPolling();
            container.innerHTML += '<div data-testid="runs-error">Could not load runs.</div>';
            return;
          }

          const polledRun = pollRes.data;
          const polledStatus = this._effectiveStatus(polledRun.status);

          if (this.isTerminal(polledStatus)) {
            this._clearPolling();
            // Re-render history with updated run
            const updatedFiltered = filteredRuns.map(r => r.id === runId ? polledRun : r);
            container.innerHTML = this.renderRunSteps(polledRun.steps || []) + this.renderRuns(updatedFiltered);
          }
        }, 2000);
      });
    });
  },
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { SequenceRuns };
}
if (typeof window !== 'undefined') {
  window.SequenceRuns = SequenceRuns;
}

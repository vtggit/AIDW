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

  _hasValue(value) {
    return value !== null && value !== undefined && value !== '';
  },

  /** "label value" with the label alone when the value is empty. */
  _agePhrase(label, value) {
    return value === '' ? label : label + ' ' + value;
  },

  /**
   * The row's time cells: a readable start stamp (its title keeps the
   * server's original value), "took <span>" for a finished run, the
   * finished run's readable finished stamp, and — for a run that has
   * not finished yet — "running for <age>" once it has started, or
   * "waiting for <age>" from when it was created (the label alone when
   * the run carries no created time).
   */
  _runTimes(run, effectiveStatus, now) {
    if (typeof TimeFormat === 'undefined' || TimeFormat === null) {
      // A page that loads this module without time_format.js keeps the
      // plain raw-timestamp row.
      const startedAt = run.started_at ? ` ${this._esc(run.started_at)}` : '';
      const finishedAt = run.finished_at ? ` ${this._esc(run.finished_at)}` : '';
      if (startedAt || finishedAt) {
        return `<div>${startedAt}${finishedAt}</div>`;
      }
      return '';
    }
    const startedAt = run.started_at;
    const finishedAt = run.finished_at;
    let times = '';
    if (this._hasValue(startedAt)) {
      times += `<span data-testid="run-started" title="${this._esc(startedAt)}">${this._esc(TimeFormat.stamp(startedAt))}</span>`;
    }
    if (effectiveStatus === 'completed' && this._hasValue(finishedAt)) {
      const duration = TimeFormat.span(startedAt, finishedAt);
      if (duration !== '') {
        times += `<span data-testid="run-duration">took ${this._esc(duration)}</span>`;
      }
    }
    if (this._hasValue(finishedAt)) {
      times += `<span title="${this._esc(finishedAt)}">${this._esc(TimeFormat.stamp(finishedAt))}</span>`;
    }
    if (effectiveStatus === 'running' || effectiveStatus === 'pending') {
      const created = run.created_at;
      let ageValue = '';
      let label = 'waiting for';
      if (this._hasValue(startedAt)) {
        label = 'running for';
        ageValue = TimeFormat.age(startedAt, now);
      } else if (this._hasValue(created)) {
        ageValue = TimeFormat.age(created, now);
      }
      times += `<span data-testid="run-age">${this._esc(this._agePhrase(label, ageValue))}</span>`;
    }
    return times;
  },

  renderRuns(runs) {
    if (!runs || runs.length === 0) {
      return '<div data-testid="runs-empty">No runs yet</div>';
    }
    const now = new Date();
    let html = '';
    for (let i = 0; i < runs.length; i++) {
      const run = runs[i] || {};
      const effectiveStatus = this._effectiveStatus(run.status);

      html += `<div class="wh-run-row" data-testid="run-row" data-id="${this._esc(run.id)}">`;
      html += `${this._esc(run.name)}`;
      html += `<span data-testid="run-status" data-status="${this._esc(effectiveStatus)}">${this._esc(effectiveStatus)}</span>`;
      const times = this._runTimes(run, effectiveStatus, now);
      if (times !== '') {
        html += times;
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

      html += `<div data-testid="run-step-row" data-status="${this._esc(effectiveStatus)}">`;
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

    // The runs block starts with this heading while a sequence is
    // chosen — whether it lists runs, the empty note, or a load error.
    // Before a sequence is chosen the block keeps its pre-selection
    // note and no heading.
    const runsHeading = '<div data-testid="runs-heading">Run history</div>';

    let selectedSequenceId = null;
    // A monotonically increasing token per row selection: an in-flight
    // response from an earlier click must not overwrite the runs of a
    // row chosen afterwards.
    let selectionToken = 0;

    // Bind delegated click listener for sequence rows (rendered by sequences.js)
    document.addEventListener('click', async (e) => {
      const row = e.target.closest('[data-testid="sequence-row"]');
      if (!row) return;

      const id = row.dataset.id;
      const token = ++selectionToken;
      this._clearPolling();
      selectedSequenceId = id;

      // Fetch all runs and client-filter by sequence_id
      const res = await ApiClient.get('/sequence-runs');
      // A later row selection superseded this response: drop it.
      if (token !== selectionToken) return;
      if (!res.ok) {
        container.innerHTML = runsHeading + '<div data-testid="runs-error">Could not load runs.</div>';
        return;
      }

      const allRuns = Array.isArray(res.data) ? res.data : [];
      const filteredRuns = allRuns.filter(r => r.sequence_id === id);

      // Render heading + history + execute button (admin-only)
      let html = runsHeading + this.renderRuns(filteredRuns);
      if (Auth.isAdmin()) {
        html += `<button data-testid="sequence-execute" data-requires-role="admin">Execute</button>`;
      }
      container.innerHTML = html;

      // Bind execute click
      const executeBtn = container.querySelector('[data-testid="sequence-execute"]');
      if (!executeBtn) return;

      executeBtn.addEventListener('click', async () => {
        this._clearPolling();

        if (!Auth.isAdmin()) {
          container.innerHTML += '<div data-testid="runs-error">Not authorized to execute runs.</div>';
          return;
        }

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

        // Render heading + steps + re-render history
        let html2 = runsHeading + this.renderRunSteps(steps);
        html2 += this.renderRuns(filteredRuns.concat([finalRun]));
        container.innerHTML = html2;

        // Poll until terminal
        const effectiveStatus = this._effectiveStatus(finalRun.status);
        if (this.isTerminal(effectiveStatus)) {
          return;
        }

        this._pollInterval = setInterval(async () => {
          const pollRes = await ApiClient.get(`/sequence-runs/${runId}`);
          // A later row selection may have superseded this poll while it
          // was in flight: its answer describes the executed run of the
          // earlier selection and must not overwrite the runs of the row
          // chosen afterwards.
          if (token !== selectionToken) {
            return;
          }
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
            container.innerHTML = runsHeading + this.renderRunSteps(polledRun.steps || []) + this.renderRuns(updatedFiltered);
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

const Drilldown = {
  _esc(str) {
    if (str == null) return '';
    const s = String(str);
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  },

  _fmt(n) {
    if (n == null || isNaN(n)) return String(n);
    const num = Number(n);
    const isInt = Number.isInteger(num);
    const opts = isInt ? { maximumFractionDigits: 0 } : { minimumFractionDigits: 0, maximumFractionDigits: 2 };
    return num.toLocaleString(undefined, opts);
  },

  init() {
    const container = document.getElementById('drilldown');
    if (!container) return;

    const dashboardsEl = document.getElementById('dashboards');
    if (dashboardsEl) {
      dashboardsEl.addEventListener('click', (e) => {
        const target = e.target.closest('.wh-item');
        if (target && target.getAttribute('data-id') !== null) {
          this.open(target.getAttribute('data-id'));
        }
      });
    }

    const closeBtn = document.getElementById('drilldown-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.close());
    }
  },

  async open(id) {
    const panel = document.getElementById('drilldown');
    const body = document.getElementById('drilldown-body');
    if (!panel || !body) return;

    panel.style.display = 'block';
    body.innerHTML = '<p>Loading...</p>';

    try {
      const res = await ApiClient.get(`/dashboard-items/${id}/data`);
      if (res.ok) {
        body.innerHTML = this.renderDetail(res.data);
      } else {
        const msg = res.error ? `Error: ${this._esc(res.error)}` : 'Failed to load data.';
        body.innerHTML = `<p class="error">${msg}</p>`;
      }
    } catch (err) {
      // Network errors keep the loading state as specified
    }
  },

  close() {
    const panel = document.getElementById('drilldown');
    const body = document.getElementById('drilldown-body');
    if (panel) panel.style.display = 'none';
    if (body) body.innerHTML = '';
  },

  renderDetail(d) {
    let html = `<h3>${this._esc(d.title)}</h3>`;

    if (d.source === 'landed') {
      const totalRows = this._fmt(d.total_rows);
      html += `<p class="provenance">${totalRows} rows · refreshed ${this._esc(d.refreshed_at)}</p>`;
    } else {
      html += `<p class="provenance">Live sample</p>`;
    }

    if (typeof Charts !== 'undefined' && d.dimension) {
      try {
        const chartData = d.series.map(s => [s.label, s.value]);
        html += `<div id="drilldown-chart">${Charts.renderBar(chartData, { dimension: this._esc(d.dimension) })}</div>`;
      } catch (_) {
        // degrade gracefully to table alone
      }
    }

    html += '<table class="dd-table" data-testid="drilldown-table"><thead><tr><th>Label</th><th>Value</th></tr></thead><tbody>';
    for (const s of d.series) {
      html += `<tr><td>${this._esc(s.label)}</td><td>${this._fmt(s.value)}</td></tr>`;
    }
    html += '</tbody></table>';

    if (d.truncated) {
      html += `<p class="note">${this._fmt(d.buckets_total)} distinct values exist.</p>`;
    }

    return html;
  },
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Drilldown };
}

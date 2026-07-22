const Drilldown = {
  _esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  },

  _fmt(n) {
    if (n == null || Number.isNaN(n)) return '—';
    const num = Number(n);
    if (!Number.isFinite(num)) return '—';
    return num.toLocaleString('en-US', { maximumFractionDigits: 2 });
  },

  _fail(message) {
    return `<div class="dd-error">${this._esc(message)}</div>`;
  },

  renderDetail(d) {
    let html = '';
    html += `<h3>${this._esc(d.title)}</h3>`;

    if (d.source === 'landed') {
      html += `<p class="dd-provenance">${this._fmt(d.total_rows)} rows · refreshed ${this._esc(d.refreshed_at)}</p>`;
    } else {
      html += '<p class="dd-provenance">Live sample</p>';
    }

    if (typeof Charts !== 'undefined' && d.dimension) {
      const seriesPairs = d.series.map((s) => [s.label, s.value]);
      const meta = {
        title: d.title,
        measure_label: `${d.aggregation} by ${d.dimension}`,
        total_rows: d.source === 'landed' ? d.total_rows : null,
        refreshed_at: d.source === 'landed' ? d.refreshed_at : null,
      };
      html += Charts.renderBar(seriesPairs, meta);
    }

    html += '<table class="dd-table" data-testid="drilldown-table">';
    html += '<thead><tr><th>Label</th><th>Value</th></tr></thead>';
    html += '<tbody>';
    for (const s of d.series) {
      html += `<tr><td>${this._esc(s.label)}</td><td>${this._fmt(s.value)}</td></tr>`;
    }
    html += '</tbody></table>';

    if (d.truncated) {
      html += `<p class="dd-note">${this._esc(d.buckets_total)} distinct values exist.</p>`;
    }

    return html;
  },

  init() {
    const panel = document.getElementById('drilldown');
    if (!panel) return;

    document.getElementById('dashboards').addEventListener('click', (e) => {
      const item = e.target.closest('.wh-item');
      if (!item) return;
      const id = item.getAttribute('data-id');
      this.open(id);
    });

    document.getElementById('drilldown-close').addEventListener('click', () => {
      this.close();
    });
  },

  open(id) {
    const panel = document.getElementById('drilldown');
    panel.hidden = false;
    const body = document.getElementById('drilldown-body');
    body.innerHTML = 'Loading...';

    ApiClient.get(`/dashboard-items/${id}/data`)
      .then((res) => {
        if (!res.ok) {
          body.innerHTML = this._fail(res.error || 'Request failed');
          return;
        }
        body.innerHTML = this.renderDetail(res.data);
      })
      .catch((err) => {
        body.innerHTML = this._fail(err.message || 'Unknown error');
      });
  },

  close() {
    const panel = document.getElementById('drilldown');
    panel.hidden = true;
    document.getElementById('drilldown-body').innerHTML = '';
  },
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Drilldown };
}

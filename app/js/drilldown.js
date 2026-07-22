const Drilldown = {
  _esc(s) {
    if (s == null) return '';
    const str = String(s);
    return str.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  },

  _fmt(n) {
    if (n == null || Number.isNaN(n)) return '—';
    const num = Number(n);
    if (!Number.isFinite(num)) return '—';
    const isInt = Number.isInteger(num);
    const opts = { minimumFractionDigits: 0, maximumFractionDigits: isInt ? 0 : 2 };
    try {
      return num.toLocaleString(undefined, opts);
    } catch (_) {
      return String(num);
    }
  },

  _fail(message) {
    const msg = message || 'An unknown error occurred.';
    return `<div class="dd-error">Error: ${this._esc(msg)}</div>`;
  },

  init() {
    const panel = document.getElementById('drilldown');
    if (!panel) return;

    const dashboards = document.getElementById('dashboards');
    if (dashboards) {
      dashboards.addEventListener('click', e => {
        const item = e.target.closest('.wh-item');
        if (item) {
          this.open(item.getAttribute('data-id'));
        }
      });
    }

    const closeBtn = document.getElementById('drilldown-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.close());
    }
  },

  open(id) {
    const panel = document.getElementById('drilldown');
    const body = document.getElementById('drilldown-body');
    if (!panel || !body) return;

    panel.style.display = '';
    body.innerHTML = '<div class="dd-loading">Loading...</div>';

    ApiClient.get(`/dashboard-items/${id}/data`)
      .then(res => {
        if (res.ok) {
          body.innerHTML = this.renderDetail(res.data);
        } else {
          const err = res.error || 'Request failed';
          body.innerHTML = this._fail(err);
        }
      })
      .catch(() => {
        body.innerHTML = this._fail('Network or parsing error');
      });
  },

  close() {
    const panel = document.getElementById('drilldown');
    const body = document.getElementById('drilldown-body');
    if (panel) panel.style.display = 'none';
    if (body) body.innerHTML = '';
  },

  renderDetail(d) {
    let html = `<h3>${this._esc(d.title)}</h3>`;

    const isLanded = d.source === 'landed';
    if (isLanded) {
      html += `<p class="dd-provenance">${this._fmt(d.total_rows)} rows · refreshed ${this._esc(d.refreshed_at)}</p>`;
    } else {
      html += '<p class="dd-provenance">Live sample</p>';
    }

    if (typeof Charts !== 'undefined' && d.dimension) {
      const meta = {
        title: d.title,
        measure_label: `${d.aggregation} by ${d.dimension}`,
        total_rows: isLanded ? d.total_rows : null,
        refreshed_at: isLanded ? d.refreshed_at : null,
      };
      html += Charts.renderBar(d.series.map(s => [s.label, s.value]), meta);
    }

    html += '<table class="dd-table" data-testid="drilldown-table"><thead><tr><th>Label</th><th>Value</th></tr></thead><tbody>';
    for (const s of d.series) {
      html += `<tr><td>${this._esc(s.label)}</td><td>${this._fmt(s.value)}</td></tr>`;
    }
    html += '</tbody></table>';

    if (d.truncated) {
      html += `<p class="dd-note">${this._esc(d.buckets_total)} distinct values exist.</p>`;
    }

    return html;
  },
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Drilldown };
}

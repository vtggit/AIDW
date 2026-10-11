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

  /**
   * Display form of an API value for the table and the provenance line.
   * Numbers and numeric strings — including values that carry thousands
   * separators such as "1,234" — render as grouped digits. Any other value
   * is text and comes back verbatim (the caller inserts it as escaped
   * text), so a value is never silently dropped.
   */
  _fmt(v) {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'number') {
      return Number.isFinite(v)
        ? v.toLocaleString('en-US', { maximumFractionDigits: 2 })
        : '—';
    }
    const s = String(v).trim();
    if (s === '') return '—';
    // Grouped decimal notation: 123,456.78 (optionally signed). Only a
    // shape-valid numeric string is parsed, so text like "1,2,3" or "N/A"
    // is kept as-is rather than mangled or dropped.
    const numeric = /^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$/.test(s);
    if (numeric) {
      const num = Number(s.replace(/,/g, ''));
      return num.toLocaleString('en-US', { maximumFractionDigits: 2 });
    }
    return s;
  },

  _fail(message) {
    return `<div class="dd-error">${this._esc(message)}</div>`;
  },

  renderDetail(d) {
    let html = '';
    html += `<h3>${this._esc(d.title)}</h3>`;

    if (d.source === 'landed') {
      html += `<p class="dd-provenance">${this._esc(this._fmt(d.total_rows))} rows · refreshed ${this._esc(d.refreshed_at)}</p>`;
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

      // 160 pixels per column; clamped to [640, 1280] so a 1-col tile still gets 640
      // and a 12-col tile caps at 1280 rather than overflowing the pane. The pane
      // itself is --detail-width (440 px) and the SVG scales down to it via CSS
      // (viewBox keeps the art); the intrinsic width only sets the aspect ratio.
      let chartWidth;
      if (d.grid_col_span != null) {
        const raw = d.grid_col_span * 160;
        chartWidth = Math.max(640, Math.min(1280, raw));
      }

      html += Charts.renderBar(seriesPairs, meta, chartWidth);
    }

    html += '<div class="dd-card" data-testid="drilldown-table-card">';
    html += '<table class="dd-table" data-testid="drilldown-table">';
    html += '<thead><tr><th>Label</th><th>Value</th></tr></thead>';
    html += '<tbody>';
    for (const s of d.series) {
      html += `<tr><td>${this._esc(s.label)}</td><td>${this._esc(this._fmt(s.value))}</td></tr>`;
    }
    html += '</tbody></table>';
    html += '</div>';

    if (d.truncated) {
      html += `<p class="dd-note">${this._esc(d.buckets_total)} distinct values exist.</p>`;
    }

    return html;
  },

  _currentId: null,

  // Monotonic open/close sequence: a /data response may only touch the
  // pane if the request that produced it is still the newest one. A
  // slower response for an earlier item (or for an item the user has
  // already closed) is stale and is dropped instead of overwriting the
  // pane's content or state.
  _seq: 0,

  /**
   * aria-current bookkeeping for the split pane: the tile whose drill-down is
   * open carries aria-current="true"; closing clears it from every tile.
   */
  _markCurrent(id) {
    const grid = document.getElementById('dashboards');
    if (!grid) return;
    for (const tile of grid.querySelectorAll('.wh-item')) {
      if (tile.getAttribute('data-id') === String(id)) {
        tile.setAttribute('aria-current', 'true');
      } else if (tile.hasAttribute('aria-current')) {
        tile.removeAttribute('aria-current');
      }
    }
  },

  _clearCurrent() {
    const grid = document.getElementById('dashboards');
    if (!grid) return;
    for (const tile of grid.querySelectorAll('.wh-item[aria-current]')) {
      tile.removeAttribute('aria-current');
    }
  },

  init() {
    const panel = document.getElementById('drilldown');
    if (!panel) return;

    const grid = document.getElementById('dashboards');
    grid.addEventListener('click', (e) => {
      const item = e.target.closest('.wh-item');
      if (!item) return;
      const id = item.getAttribute('data-id');
      this.open(id);
    });

    // Layout editing re-renders the grid: close the pane first so the grid keeps
    // the full width while editing. The editor's own handler (warehouse.js) is a
    // capture listener on #dashboards that stops propagation, so this one listens
    // on document capture — the first node in the path, before any grid handler.
    document.addEventListener('click', (e) => {
      if (e.target instanceof Element && e.target.closest('[data-action="edit-layout"]')) {
        this.close();
      }
    }, true);

    // A grid (re)render replaces the tile nodes (deeplink open racing the
    // initial render, layout save, refresh): re-mark the open tile once the
    // fresh DOM is in place. Attribute changes do not retrigger the observer.
    const observer = new MutationObserver(() => {
      if (this._currentId !== null && !panel.hidden) {
        this._markCurrent(this._currentId);
      }
    });
    observer.observe(grid, { childList: true, subtree: true });

    document.getElementById('drilldown-close').addEventListener('click', () => {
      this.close();
    });
  },

  open(id) {
    const panel = document.getElementById('drilldown');
    const body = document.getElementById('drilldown-body');
    panel.hidden = false;
    this._currentId = String(id);
    this._seq += 1;
    const seq = this._seq;
    this._markCurrent(id);
    body.innerHTML = 'Loading...';

    ApiClient.get(`/dashboard-items/${encodeURIComponent(id)}/data`)
      .then((res) => {
        // A later open() or close() superseded this request: its response must
        // neither overwrite the pane's content for another item nor touch the
        // pane's state after it was closed.
        if (seq !== this._seq) return;
        if (!res.ok) {
          body.innerHTML = this._fail(res.error || 'Request failed');
          return;
        }
        body.innerHTML = this.renderDetail(res.data);
      })
      .catch((err) => {
        if (seq !== this._seq) return;
        body.innerHTML = this._fail(err.message || 'Unknown error');
      });
  },

  close() {
    const panel = document.getElementById('drilldown');
    panel.hidden = true;
    this._seq += 1; // drop every in-flight /data response
    this._currentId = null;
    this._clearCurrent();
    document.getElementById('drilldown-body').innerHTML = '';
  },
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Drilldown };
}

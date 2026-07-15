/**
 * Warehouse UI — the schema-tier suggestion inbox + dashboards.
 *
 * Renders the two halves of the differentiator loop and wires the accept/dismiss actions:
 *   • Inbox     — GET /suggestions, show the 'suggested' ones with Accept / Dismiss buttons.
 *   • Dashboards— GET /dashboards + /dashboard-items, show accepted items grouped by dashboard,
 *                 then fill each item's chart from GET /dashboard-items/{id}/data (sampled,
 *                 suppression-filtered series; SVG drawn in-house, no chart library).
 *
 * Talks to the backend only through ApiClient (never fetch() directly). Render helpers are pure
 * (data -> HTML string) so they can be unit-tested; init()/refresh() do the I/O + DOM wiring.
 * All user/text values are escaped before insertion (no innerHTML injection).
 */
const Warehouse = {
    async init() {
        await this._ensureAuth();
        this._renderAuth();
        const inbox = document.getElementById('inbox');
        if (inbox) inbox.addEventListener('click', (e) => this._onCardClick(e));
        const pii = document.getElementById('pii-inbox');
        if (pii) pii.addEventListener('click', (e) => this._onPiiClick(e));
        await this.refresh();
    },

    /**
     * Dev convenience: if auth is on and no token is present, sign in with the development admin
     * token so the demo works out of the box. In any non-dev environment we only adopt an
     * already-present token (set by a real login / OIDC redirect).
     */
    async _ensureAuth() {
        if (typeof Auth === 'undefined') return;
        if (!Auth.getAuthorizationHeader() && Config.ENVIRONMENT === 'development') {
            await Auth.loginWithToken('dev-secret-token:admin');
        } else {
            await Auth.init();
        }
    },

    _renderAuth() {
        const el = document.getElementById('auth-status');
        if (!el) return;
        const user = Auth.getCurrentUser && Auth.getCurrentUser();
        el.textContent = user ? `Signed in · ${user.username || user.sub || 'admin'}` : 'Not signed in';
    },

    async refresh() {
        await Promise.all([this.loadInbox(), this.loadDashboards(), this.loadPiiFlags()]);
    },

    async loadInbox() {
        const el = document.getElementById('inbox');
        if (!el) return;
        const res = await ApiClient.get('/suggestions');
        if (!res.ok) {
            el.innerHTML = this._notice('Could not load suggestions.', true);
            return;
        }
        const suggested = (res.data || [])
            .filter((s) => s.status === 'suggested')
            .sort((a, b) => (b.score || 0) - (a.score || 0));
        const count = document.getElementById('inbox-count');
        if (count) count.textContent = String(suggested.length);
        el.innerHTML = suggested.length
            ? suggested.map(this.renderSuggestionCard).join('')
            : this._notice('No pending suggestions. Discover a source to generate some.');
    },

    async loadDashboards() {
        const el = document.getElementById('dashboards');
        if (!el) return;
        const [dRes, iRes] = await Promise.all([
            ApiClient.get('/dashboards'),
            ApiClient.get('/dashboard-items'),
        ]);
        if (!dRes.ok || !iRes.ok) {
            el.innerHTML = this._notice('Could not load dashboards.', true);
            return;
        }
        el.innerHTML = this.renderDashboards(dRes.data || [], iRes.data || []);
        await this._fillCharts(el, iRes.data || []);
    },

    /**
     * Fetch each item's chart series and fill its placeholder. Runs after EVERY dashboards
     * render (innerHTML replaces the nodes), so it must tolerate re-entry and nodes that were
     * re-rendered underneath a slow response — a stale fill is simply dropped.
     */
    async _fillCharts(root, items) {
        await Promise.all(items.map(async (i) => {
            const res = await ApiClient.get(`/dashboard-items/${encodeURIComponent(i.id)}/data`);
            const holder = Array.from(root.querySelectorAll('[data-testid="chart"]'))
                .find((n) => n.getAttribute('data-id') === String(i.id));
            if (!holder) return;
            if (res.ok) {
                holder.innerHTML = Warehouse.renderChart(res.data || {});
            } else if (res.status === 503) {
                holder.innerHTML = Warehouse._chartNote('Live data is off for this environment.');
            } else if (res.status === 422) {
                holder.innerHTML = Warehouse._chartNote(Warehouse._errText(res, 'Not chartable.'));
            } else {
                holder.innerHTML = Warehouse._chartNote('Could not load data.', true);
            }
        }));
    },

    /** Best-effort human text out of an ApiClient failure without assuming its error shape. */
    _errText(res, fallback) {
        const e = res && res.error;
        if (typeof e === 'string' && e) return e;
        if (e && typeof e.detail === 'string') return e.detail;
        if (e && typeof e.message === 'string') return e.message;
        return fallback;
    },

    // ---- pure render helpers (data -> HTML) ---------------------------------

    renderSuggestionCard(s) {
        const conf = Warehouse._confidence(s.score);
        return `<div class="wh-card" data-testid="suggestion" data-id="${Warehouse._attr(s.id)}">
      <div class="wh-card-main">
        <span class="badge wh-chart">${Warehouse._chartLabel(s.item_type)}</span>
        <span class="wh-title">${Warehouse._esc(s.title || s.name || '')}</span>
        <span class="wh-agg">${Warehouse._esc(s.aggregation || '')}</span>
      </div>
      <div class="wh-card-actions">
        <span class="wh-conf ${conf.cls}" data-testid="confidence" title="score ${conf.value}">${conf.label}</span>
        <button class="btn btn-primary btn-sm" data-action="accept" data-id="${Warehouse._attr(s.id)}">Accept</button>
        <button class="btn btn-secondary btn-sm" data-action="dismiss" data-id="${Warehouse._attr(s.id)}">Dismiss</button>
      </div>
    </div>`;
    },

    /** Map a suggestion score to a confidence chip. Profile-tier's re-scoring surfaces here: a
     * data-confirmed low-arity dimension reads High; a demoted near-unique field reads Low. */
    _confidence(score) {
        const v = typeof score === 'number' ? score : 0;
        const value = v.toFixed(2);
        if (v >= 0.7) return { label: 'High', cls: 'wh-conf-high', value };
        if (v >= 0.4) return { label: 'Medium', cls: 'wh-conf-med', value };
        return { label: 'Low', cls: 'wh-conf-low', value };
    },

    renderDashboards(dashboards, items) {
        if (!dashboards.length) {
            return Warehouse._notice('No dashboards yet. Accept a suggestion to start one.');
        }
        const byDash = {};
        for (const it of items) {
            (byDash[it.dashboard_id] = byDash[it.dashboard_id] || []).push(it);
        }
        return dashboards.map((d) => {
            const its = (byDash[d.id] || []).slice().sort(
                (a, b) => (a.position || 0) - (b.position || 0)
            );
            const body = its.length
                ? its.map(Warehouse.renderDashboardItem).join('')
                : '<div class="wh-empty">Empty</div>';
            return `<div class="dashboard-card" data-testid="dashboard" data-id="${Warehouse._attr(d.id)}">
        <h3>${Warehouse._esc(d.name || '')}</h3>
        <div class="wh-items">${body}</div>
      </div>`;
        }).join('');
    },

    renderDashboardItem(i) {
        return `<div class="wh-item" data-testid="dashboard-item" data-id="${Warehouse._attr(i.id)}">
      <span class="badge wh-chart">${Warehouse._chartLabel(i.item_type)}</span>
      <span class="wh-title">${Warehouse._esc(i.title || i.name || '')}</span>
      <div class="wh-item-chart" data-testid="chart" data-id="${Warehouse._attr(i.id)}">${Warehouse._chartNote('Loading data…')}</div>
    </div>`;
    },

    // ---- chart rendering (pure; SVG built in-house, values escaped/coerced) --

    /** Dispatch a /data payload to the item_type's renderer. */
    renderChart(d) {
        const series = Array.isArray(d.series) ? d.series : [];
        if (!series.length) return Warehouse._chartNote('No data in the sample.');
        const meta = Warehouse._chartMeta(d, series);
        if (d.item_type === 'kpi' || !d.dimension) return Warehouse.renderKpi(series[0], meta);
        if (d.item_type === 'line') return Warehouse.renderLineChart(series, meta);
        if (d.item_type === 'bar' || d.item_type === 'pie') return Warehouse.renderBarChart(series, meta);
        return Warehouse.renderValueList(series, meta);
    },

    renderBarChart(series, meta) {
        const W = 320; const H = 140; const top = 14; const bottom = 24; const side = 4;
        const plotW = W - side * 2;
        const plotH = H - top - bottom;
        const max = Math.max(0, ...series.map((p) => Number(p.value) || 0));
        const n = series.length;
        const slot = plotW / n;
        const barW = Math.max(2, slot * 0.72);
        const bars = series.map((p, idx) => {
            const v = Math.max(0, Number(p.value) || 0);
            const h = max > 0 ? (v / max) * plotH : 0;
            const x = side + idx * slot + (slot - barW) / 2;
            const y = top + plotH - h;
            const cx = (x + barW / 2).toFixed(1);
            const valText = n <= 12
                ? `<text x="${cx}" y="${(y - 3).toFixed(1)}" text-anchor="middle" class="wh-svg-val">${Warehouse._esc(Warehouse._fmtNum(v))}</text>`
                : '';
            const axText = n <= 8
                ? `<text x="${cx}" y="${H - 8}" text-anchor="middle" class="wh-svg-label">${Warehouse._esc(Warehouse._trim(p.label, 10))}</text>`
                : '';
            return `<g><title>${Warehouse._esc(p.label)}: ${Warehouse._esc(Warehouse._fmtNum(v))}</title>`
                + `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" rx="2" class="wh-svg-bar" data-testid="chart-bar"></rect>`
                + valText + axText + '</g>';
        }).join('');
        return `<svg viewBox="0 0 ${W} ${H}" role="img" data-testid="chart-svg">${bars}</svg>${meta}`;
    },

    renderLineChart(series, meta) {
        const W = 320; const H = 140; const top = 14; const bottom = 24; const side = 8;
        const plotW = W - side * 2;
        const plotH = H - top - bottom;
        const vals = series.map((p) => Number(p.value) || 0);
        const max = Math.max(0, ...vals);
        const step = series.length > 1 ? plotW / (series.length - 1) : 0;
        const pt = (v, idx) => {
            const x = series.length > 1 ? side + idx * step : W / 2;
            const y = top + plotH - (max > 0 ? (Math.max(0, v) / max) * plotH : 0);
            return [x, y];
        };
        const points = vals.map((v, idx) => pt(v, idx).map((c) => c.toFixed(1)).join(',')).join(' ');
        const dots = vals.map((v, idx) => {
            const [x, y] = pt(v, idx);
            return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5" class="wh-svg-dot"><title>${Warehouse._esc(series[idx].label)}: ${Warehouse._esc(Warehouse._fmtNum(v))}</title></circle>`;
        }).join('');
        const first = series[0]; const last = series[series.length - 1];
        const labels = `<text x="${side}" y="${H - 8}" text-anchor="start" class="wh-svg-label">${Warehouse._esc(Warehouse._trim(first.label, 14))}</text>`
            + (series.length > 1 ? `<text x="${W - side}" y="${H - 8}" text-anchor="end" class="wh-svg-label">${Warehouse._esc(Warehouse._trim(last.label, 14))}</text>` : '');
        return `<svg viewBox="0 0 ${W} ${H}" role="img" data-testid="chart-svg"><polyline points="${points}" class="wh-svg-line"></polyline>${dots}${labels}</svg>${meta}`;
    },

    renderKpi(point, meta) {
        const v = Number(point.value);
        return `<div class="wh-kpi" data-testid="chart-kpi">${Warehouse._esc(Warehouse._fmtNum(Number.isFinite(v) ? v : 0))}</div>${meta}`;
    },

    /** Fallback for table/unknown item types: a compact label -> value list. */
    renderValueList(series, meta) {
        const rows = series.map((p) => `<div class="wh-chart-row"><span>${Warehouse._esc(Warehouse._trim(p.label, 32))}</span><span>${Warehouse._esc(Warehouse._fmtNum(Number(p.value) || 0))}</span></div>`).join('');
        return `${rows}${meta}`;
    },

    /** Provenance footer: what was aggregated and over how many sampled rows. */
    _chartMeta(d, series) {
        const what = `${d.aggregation || ''}(${d.measure || 'rows'})${d.dimension ? ` by ${d.dimension}` : ''}`;
        const sampled = `${Number(d.sample_size) || 0} sampled rows`;
        const cap = d.truncated ? ` · top ${series.length} of ${Number(d.buckets_total) || 0}` : '';
        return `<div class="wh-chart-meta" data-testid="chart-meta">${Warehouse._esc(`${what} · ${sampled}${cap}`)}</div>`;
    },

    _chartNote(msg, isError) {
        return `<span class="wh-chart-note${isError ? ' wh-err' : ''}" data-testid="chart-note">${Warehouse._esc(msg)}</span>`;
    },

    _fmtNum(v) {
        const n = Number(v);
        if (!Number.isFinite(n)) return '0';
        return Number.isInteger(n) ? String(n) : n.toFixed(2);
    },

    _trim(s, n) {
        const str = String(s == null ? '' : s);
        return str.length > n ? `${str.slice(0, n - 1)}…` : str;
    },

    // ---- actions ------------------------------------------------------------

    _onCardClick(e) {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;
        const id = btn.getAttribute('data-id');
        const action = btn.getAttribute('data-action');
        if (action === 'accept') this.accept(id);
        else if (action === 'dismiss') this.dismiss(id);
    },

    async accept(id) {
        const res = await ApiClient.post(`/suggestions/${encodeURIComponent(id)}/accept`);
        if (res.ok) {
            this._toast('Accepted — added to a dashboard.');
            await this.refresh();
        } else {
            this._toast('Accept failed.', true);
        }
    },

    async dismiss(id) {
        const res = await ApiClient.post(`/suggestions/${encodeURIComponent(id)}/dismiss`);
        if (res.ok) {
            this._toast('Dismissed.');
            await this.refresh();
        } else {
            this._toast('Dismiss failed.', true);
        }
    },

    // ---- PII flags review ---------------------------------------------------

    async loadPiiFlags() {
        const el = document.getElementById('pii-inbox');
        if (!el) return;
        const [fRes, dRes, dfRes] = await Promise.all([
            ApiClient.get('/pii-flags'),
            ApiClient.get('/datasets'),
            ApiClient.get('/discovered-fields'),
        ]);
        if (!fRes.ok || !dRes.ok || !dfRes.ok) {
            el.innerHTML = this._notice('Could not load PII flags.', true);
            return;
        }
        // only 'flagged' rows are pending review — confirmed/dismissed/stale are decided
        const pending = (fRes.data || []).filter((f) => f.status === 'flagged');
        const count = document.getElementById('pii-count');
        if (count) count.textContent = String(pending.length);
        const dsById = {};
        for (const d of dRes.data || []) dsById[d.id] = d.name;
        const fieldById = {};
        for (const f of dfRes.data || []) fieldById[f.id] = f.name;
        el.innerHTML = pending.length
            ? this.renderPiiGroups(pending, dsById, fieldById)
            : this._notice('No PII flags awaiting review. Discover or profile a source to scan.');
    },

    /** Group pending flags by dataset and render each group as a card of flag rows. */
    renderPiiGroups(flags, dsById, fieldById) {
        const byDs = {};
        for (const f of flags) {
            const key = f.dataset_id || '';
            (byDs[key] = byDs[key] || []).push(f);
        }
        return Object.keys(byDs).map((dsId) => {
            const name = dsById[dsId] || 'Unknown dataset';
            const rows = byDs[dsId].map((f) => Warehouse.renderPiiCard(f, fieldById[f.discovered_field_id])).join('');
            return `<div class="dashboard-card" data-testid="pii-group" data-id="${Warehouse._attr(dsId)}">
        <h3>${Warehouse._esc(name)}</h3>
        <div class="wh-cards">${rows}</div>
      </div>`;
        }).join('');
    },

    renderPiiCard(f, fieldName) {
        const conf = Warehouse._confidence(f.confidence);
        const field = fieldName || f.discovered_field_id || '(unbound field)';
        return `<div class="wh-card" data-testid="pii-flag" data-id="${Warehouse._attr(f.id)}">
      <div class="wh-card-main">
        <span class="badge wh-chart">${Warehouse._esc(Warehouse._piiCategory(f.category))}</span>
        <span class="wh-title">${Warehouse._esc(field)}</span>
        <span class="wh-agg" data-testid="pii-tier">${Warehouse._esc(f.detection_tier || '')}</span>
        <span class="wh-sub">${Warehouse._esc(f.rationale || '')}</span>
      </div>
      <div class="wh-card-actions">
        <span class="wh-conf ${conf.cls}" data-testid="pii-confidence" title="confidence ${conf.value}">${conf.label}</span>
        <button class="btn btn-primary btn-sm" data-action="pii-confirm" data-id="${Warehouse._attr(f.id)}">Confirm</button>
        <button class="btn btn-secondary btn-sm" data-action="pii-dismiss" data-id="${Warehouse._attr(f.id)}">Dismiss</button>
      </div>
    </div>`;
    },

    _piiCategory(c) {
        return String(c || '').replace(/_/g, ' ') || 'other';
    },

    _onPiiClick(e) {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;
        const id = btn.getAttribute('data-id');
        const action = btn.getAttribute('data-action');
        if (action === 'pii-confirm') this.confirmPii(id);
        else if (action === 'pii-dismiss') this.dismissPii(id);
    },

    async confirmPii(id) {
        const res = await ApiClient.post(`/pii-flags/${encodeURIComponent(id)}/confirm`);
        if (res.ok) {
            this._toast('Confirmed — this field is personal data.');
            await this.loadPiiFlags();
        } else {
            this._toast('Confirm failed.', true);
        }
    },

    async dismissPii(id) {
        const res = await ApiClient.post(`/pii-flags/${encodeURIComponent(id)}/dismiss`);
        if (res.ok) {
            this._toast('Dismissed — not personal data.');
            await this.loadPiiFlags();
        } else {
            this._toast('Dismiss failed.', true);
        }
    },

    // ---- small utilities ----------------------------------------------------

    _chartLabel(t) {
        return { kpi: 'KPI', bar: 'Bar', line: 'Line', pie: 'Pie', table: 'Table' }[t]
            || String(t || '').toUpperCase();
    },

    /** HTML-escape text for safe insertion into element content. */
    _esc(s) {
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    },

    /** Escape a value destined for a double-quoted HTML attribute. */
    _attr(s) {
        return this._esc(s);
    },

    _notice(msg, isError) {
        return `<div class="wh-empty${isError ? ' wh-err' : ''}" data-testid="notice">${Warehouse._esc(msg)}</div>`;
    },

    _toast(msg, isError) {
        const el = document.getElementById('toast');
        if (!el) return;
        el.textContent = msg;
        el.hidden = false;
        el.classList.toggle('wh-err', !!isError);
        clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => { el.hidden = true; }, 2500);
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Warehouse };
}

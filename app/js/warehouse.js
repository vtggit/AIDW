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
        this._suggestions = [];
        this._confidenceFilter = 'all';
        const inbox = document.getElementById('inbox');
        if (inbox) inbox.addEventListener('click', (e) => this._onCardClick(e));
        const filters = document.querySelector('[data-testid="suggestions-filters"]');
        if (filters) filters.addEventListener('click', (e) => this._onFilterClick(e));
        this._bindSuggestionsFit();
        this._piiFlags = [];
        this._piiFilter = 'all';
        const pii = document.getElementById('pii-inbox');
        if (pii) pii.addEventListener('click', (e) => this._onPiiClick(e));
        const piiFilters = document.querySelector('[data-testid="pii-filters"]');
        if (piiFilters) piiFilters.addEventListener('click', (e) => this._onPiiFilterClick(e));
        this._bindPiiFit();
        await this.refresh();
    },

    /**
     * Resolve auth. init() first (adopts a #access_token from an OIDC redirect and reads the
     * backend's auth mode). If still unauthenticated: dev-token in development mode; in production
     * (Keycloak) leave it to _renderAuth to show a Log in button that redirects to the IdP.
     */
    async _ensureAuth() {
        if (typeof Auth === 'undefined') return;
        await Auth.init();
        if (!Auth.isAuthenticated() && !Auth.isProductionAuth()) {
            await Auth.loginWithToken('dev-secret-token:admin');
        }
    },

    _renderAuth() {
        const el = document.getElementById('auth-status');
        if (!el) return;
        const user = Auth.getCurrentUser && Auth.getCurrentUser();
        if (user) {
            el.textContent = `Signed in · ${user.username || user.sub || 'user'}`;
        } else if (Auth.isProductionAuth && Auth.isProductionAuth()) {
            el.innerHTML = '<button class="btn btn-primary" id="wh-login">Log in</button>';
            const b = document.getElementById('wh-login');
            if (b) b.addEventListener('click', () => Auth.login());
        } else {
            el.textContent = 'Not signed in';
        }
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
        // Cache the pending suggestions (highest confidence first) so the
        // confidence chips and accept/dismiss re-render from state — no new
        // request — and _renderInbox() does the DOM update.
        const data = Array.isArray(res.data) ? res.data : [];
        this._suggestions = data
            .filter((s) => s && s.status === 'suggested')
            .sort((a, b) => Warehouse._scoreNumber(b.score) - Warehouse._scoreNumber(a.score));
        this._renderInbox();
    },

    async loadDashboards() {
        const el = document.getElementById('dashboards');
        if (!el) return;
        const [dRes, iRes, lRes] = await Promise.all([
            ApiClient.get('/dashboards'),
            ApiClient.get('/dashboard-items'),
            ApiClient.get('/dashboard-item-layouts'),
        ]);
        if (!dRes.ok || !iRes.ok) {
            el.innerHTML = this._notice('Could not load dashboards.', true);
            return;
        }
        const dashboards = dRes.data || [];
        const items = iRes.data || [];
        const layouts = (lRes && lRes.ok ? (lRes.data || []) : []);
        el.innerHTML = this.renderDashboards(dashboards, items, layouts);
        Warehouse.bindLayoutEditor(el, dashboards, items, layouts);
        await this._fillCharts(el, items);
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

    /**
     * One compact inbox row: type, suggested item, aggregation, the
     * confidence chip and the Accept / Dismiss actions, on the same grid
     * columns as the sticky header. Every API value goes through
     * _esc/_attr — the row is never built from raw HTML.
     */
    renderSuggestionRow(s) {
        const conf = Warehouse._confidence(s.score);
        return `<div class="wh-sug-row" data-testid="suggestion" data-id="${Warehouse._attr(s.id)}">
      <span class="wh-sug-type">${Warehouse._esc(Warehouse._chartLabel(s.item_type))}</span>
      <span class="wh-sug-title">${Warehouse._esc(s.title || s.name || '')}</span>
      <span class="wh-sug-agg">${Warehouse._esc(s.aggregation || '')}</span>
      <span class="wh-conf ${conf.cls}" data-testid="confidence" title="score ${conf.value}">${conf.label}</span>
      <span class="wh-sug-actions">
        <button type="button" class="btn btn-primary btn-sm" data-action="accept" data-id="${Warehouse._attr(s.id)}">Accept</button>
        <button type="button" class="btn btn-secondary btn-sm" data-action="dismiss" data-id="${Warehouse._attr(s.id)}">Dismiss</button>
      </span>
    </div>`;
    },

    /** The sticky column header: ONE element holding the five labels, in column order. */
    _inboxHead() {
        return '<div class="wh-inbox-head" data-testid="inbox-header">'
            + '<span class="wh-inbox-col">Type</span>'
            + '<span class="wh-inbox-col">Suggested item</span>'
            + '<span class="wh-inbox-col">Aggregation</span>'
            + '<span class="wh-inbox-col">Confidence</span>'
            + '<span class="wh-inbox-col">Actions</span>'
            + '</div>';
    },

    /** The nothing-to-review empty state: centred heading, sentence and a
     * link into the Data sources tool. */
    _inboxEmpty() {
        return '<div class="wh-sug-empty" data-testid="inbox-empty">'
            + '<span class="wh-sug-empty-eyebrow">No pending suggestions</span>'
            + '<h3 class="wh-sug-empty-title">No suggestions to review</h3>'
            + '<p class="wh-sug-empty-copy">Discover a data source to get suggested dashboard items.</p>'
            + '<a class="btn btn-primary" data-testid="open-sources" href="studio.html?panel=sources">Open Data sources</a>'
            + '</div>';
    },

    /**
     * Render #inbox from the cached suggestions: the sticky column header,
     * then the rows for the active confidence filter (highest confidence
     * first), or the matching empty state. Also updates the #inbox-count
     * badge, every chip's own count and its aria-pressed state.
     */
    _renderInbox() {
        const el = document.getElementById('inbox');
        if (!el) return;
        const all = Array.isArray(this._suggestions) ? this._suggestions : [];
        const filter = this._confidenceFilter || 'all';
        const tierOf = (s) => Warehouse._confidence(s.score).tier;
        const counts = { all: all.length, high: 0, medium: 0, low: 0 };
        for (const s of all) counts[tierOf(s)] += 1;
        const visible = filter === 'all' ? all : all.filter((s) => tierOf(s) === filter);
        const badge = document.getElementById('inbox-count');
        if (badge) badge.textContent = String(counts.all);
        for (const key of ['all', 'high', 'medium', 'low']) {
            const countEl = document.getElementById('filter-' + key + '-count');
            if (countEl) countEl.textContent = String(counts[key]);
            const chip = document.querySelector('[data-testid="filter-' + key + '"]');
            if (chip) chip.setAttribute('aria-pressed', String(chip.getAttribute('data-filter') === filter));
        }
        const body = visible.length
            ? visible.map((s) => Warehouse.renderSuggestionRow(s)).join('')
            : (counts.all
                ? '<div class="wh-sug-empty" data-testid="inbox-empty-filter"><p class="wh-sug-empty-copy">No suggestions at this confidence.</p></div>'
                : Warehouse._inboxEmpty());
        el.innerHTML = Warehouse._inboxHead() + body;
    },

    /** A confidence chip narrows the list client-side: no request is sent. */
    _onFilterClick(e) {
        const chip = e.target.closest('.wh-filter-chip');
        if (!chip) return;
        const filter = chip.getAttribute('data-filter');
        if (!filter || filter === this._confidenceFilter) return;
        this._confidenceFilter = filter;
        this._renderInbox();
    },

    /**
     * While the shell shows the suggestions section, mark main.wh-main so
     * css/suggestions.css can lock the panel to the viewport height
     * (desktop): the document and the main .aidw-scroll region must not
     * scroll — only #inbox does. The shell toggles the section's hidden
     * attribute when switching tools; the observer follows it.
     */
    _bindSuggestionsFit() {
        const section = document.querySelector('section.wh-panel[data-panel="suggestions"]');
        if (!section) return;
        const main = section.closest ? section.closest('main.wh-main') : null;
        if (!main) return;
        const sync = () => main.classList.toggle('suggestions-open', !section.hidden);
        sync();
        if (typeof MutationObserver === 'undefined') return;
        this._suggestionsFitObserver = new MutationObserver(sync);
        this._suggestionsFitObserver.observe(section, { attributes: true, attributeFilter: ['hidden'] });
    },

    /**
     * Coerce an API score to a finite number: finite numbers pass through,
     * numeric strings are parsed (a score that arrives as "0.9" sorts AND
     * tiers as 0.9 — the two can never disagree), and anything else —
     * missing, empty, non-numeric, control characters, NUL, Infinity/NaN —
     * reads 0.
     */
    _scoreNumber(score) {
        if (typeof score === 'number' && Number.isFinite(score)) return score;
        if (typeof score === 'string' && score.trim() !== '') {
            const n = Number(score);
            if (Number.isFinite(n)) return n;
        }
        return 0;
    },

    /** Map a suggestion score to a confidence chip. Profile-tier's re-scoring surfaces here: a
     * data-confirmed low-arity dimension reads High; a demoted near-unique field reads Low. */
    _confidence(score) {
        const v = Warehouse._scoreNumber(score);
        const value = v.toFixed(2);
        if (v >= 0.7) return { label: 'High', cls: 'wh-conf-high', tier: 'high', value };
        if (v >= 0.4) return { label: 'Medium', cls: 'wh-conf-med', tier: 'medium', value };
        return { label: 'Low', cls: 'wh-conf-low', tier: 'low', value };
    },

    renderDashboards(dashboards, items, layouts = [], editingId = null) {
        if (!dashboards.length) {
            return Warehouse._notice('No dashboards yet. Accept a suggestion to start one.');
        }
        const overlayIdx = {};
        for (const lo of layouts) {
            if (lo.dashboard_item_id && !overlayIdx[lo.dashboard_item_id]) {
                overlayIdx[lo.dashboard_item_id] = lo;
            }
        }
        const byDash = {};
        for (const it of items) {
            (byDash[it.dashboard_id] = byDash[it.dashboard_id] || []).push(it);
        }
        return dashboards.map((d) => {
            const C = (typeof d.grid_columns === 'number' && Number.isInteger(d.grid_columns) && d.grid_columns >= 1 && d.grid_columns <= 12) ? d.grid_columns : 12;
            const its = (byDash[d.id] || []).slice().sort(
                (a, b) => (a.position || 0) - (b.position || 0)
            );
            const body = its.length
                ? its.map((it) => {
                    const lo = overlayIdx[it.id];
                    let merged = Object.assign({}, it);
                    if (lo) {
                        ['grid_col_start', 'grid_col_span', 'grid_row_span'].forEach(k => {
                            if (typeof lo[k] === 'number' && Number.isInteger(lo[k]) && lo[k] >= 1) {
                                merged[k] = lo[k];
                            }
                        });
                    }
                    return Warehouse.renderDashboardItem(merged, C, editingId);
                }).join('')
                : '<div class="wh-empty" style="grid-column: 1 / -1">Empty</div>';
            return `<div class="dashboard-card" data-testid="dashboard" data-id="${Warehouse._attr(d.id)}">
        <h3>${Warehouse._esc(d.name || '')}</h3>
        <div class="wh-items" style="display:grid; grid-template-columns: repeat(${C}, minmax(0,1fr))">${body}</div>
      </div>`;
        }).join('');
    },

    renderDashboardItem(i, C, editingId = null) {
        const isPosInt = (v) => typeof v === 'number' && Number.isInteger(v) && v >= 1;
        let W = isPosInt(i.grid_col_span) ? Math.min(C, Math.max(1, i.grid_col_span)) : C;
        let S = 'auto';
        if (isPosInt(i.grid_col_start)) {
            const maxStart = C - W + 1;
            S = Math.min(maxStart, Math.max(1, i.grid_col_start));
        }
        let R = isPosInt(i.grid_row_span) ? Math.min(6, Math.max(1, i.grid_row_span)) : 1;
        const style = `grid-column: ${S} / span ${W}; grid-row: span ${R}`;
        const effStart = (S === 'auto') ? 1 : S;
        const isAdmin = typeof Auth !== 'undefined' && Auth.isAdmin();
        const editorHtml = (isAdmin && String(i.id) === String(editingId))
            ? `<div class="wh-layout-editor" data-requires-role="admin">
      <input type="number" data-testid="layout-col-start" min="1" max="${C}" value="${effStart}">
      <input type="number" data-testid="layout-col-span" min="1" max="${C}" value="${W}">
      <input type="number" data-testid="layout-row-span" min="1" max="6" value="${R}">
      <button type="button" class="btn btn-sm" data-action="save-layout">Save</button>
      <button type="button" class="btn btn-sm" data-action="cancel-layout">Cancel</button>
    </div>`
            : '';
        const editBtn = isAdmin ? `<button type="button" class="btn btn-sm" data-action="edit-layout" data-requires-role="admin">Edit layout</button>` : '';
        return `<div class="wh-item" data-testid="dashboard-item" data-id="${Warehouse._attr(i.id)}" style="${style}">
      <span class="badge wh-chart">${Warehouse._chartLabel(i.item_type)}</span>
      <span class="wh-title">${Warehouse._esc(i.title || i.name || '')}</span>
      <div class="wh-item-chart" data-testid="chart" data-id="${Warehouse._attr(i.id)}">${Warehouse._chartNote('Loading data…')}</div>
      ${editorHtml}
      ${editBtn}
    </div>`;
    },

    // ---- chart rendering (pure; SVG built in-house, values escaped/coerced) --

    /** Dispatch a /data payload to the item_type's renderer. */
    renderChart(d) {
        const series = Array.isArray(d.series) ? d.series : [];
        if (!series.length) return Warehouse._chartNote('No data in the sample.');
        const meta = Warehouse._chartMeta(d, series);
        // v2 (#259): bar-shaped items delegate to the labeled full-size renderer when
        // charts.js is loaded. The rows/freshness caption is passed ONLY for the landed
        // path (#258) — a live-sample card must never present its cap as a total.
        if (typeof Charts !== 'undefined' && d.dimension
                && (d.item_type === 'bar' || d.item_type === 'pie')) {
            const landed = d.source === 'landed';
            return Charts.renderBar(series.map((s) => [s.label, s.value]), {
                title: d.title || '',
                measure_label: `${d.aggregation || ''}${d.dimension ? ' by ' + d.dimension : ''}`,
                total_rows: landed ? d.total_rows : null,
                refreshed_at: landed ? d.refreshed_at : null,
            });
        }
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

    bindLayoutEditor(container, dashboards, items, layouts) {
        if (container._boundLayoutEditor) return;
        container._boundLayoutEditor = true;
        const handler = async (e) => {
            const btn = e.target.closest('[data-action]');
            const inEditor = e.target.closest('.wh-layout-editor');
            if (btn) {
                const action = btn.getAttribute('data-action');
                if (['edit-layout', 'save-layout', 'cancel-layout'].includes(action)) {
                    e.stopPropagation();
                    if (action === 'edit-layout') {
                        container.innerHTML = Warehouse.renderDashboards(dashboards, items, layouts, btn.closest('.wh-item').dataset.id);
                    } else if (action === 'cancel-layout') {
                        container.innerHTML = Warehouse.renderDashboards(dashboards, items, layouts, null);
                        await Warehouse._fillCharts(container, items);
                    } else if (action === 'save-layout') {
                        const tileEl = btn.closest('.wh-item');
                        const itemId = tileEl.dataset.id;
                        const colStart = parseInt(tileEl.querySelector('[data-testid="layout-col-start"]').value, 10);
                        const colSpan = parseInt(tileEl.querySelector('[data-testid="layout-col-span"]').value, 10);
                        const rowSpan = parseInt(tileEl.querySelector('[data-testid="layout-row-span"]').value, 10);

                        const existingIdx = layouts.findIndex(l => l.dashboard_item_id === itemId);
                        let res;
                        if (existingIdx !== -1) {
                            const body = { grid_col_start: colStart, grid_col_span: colSpan, grid_row_span: rowSpan };
                            res = await ApiClient.put('/dashboard-item-layouts/' + layouts[existingIdx].id, body);
                            if (res.ok) {
                                layouts[existingIdx].grid_col_start = res.data.grid_col_start;
                                layouts[existingIdx].grid_col_span = res.data.grid_col_span;
                                layouts[existingIdx].grid_row_span = res.data.grid_row_span;
                                container.innerHTML = Warehouse.renderDashboards(dashboards, items, layouts, null);
                                await Warehouse._fillCharts(container, items);
                            } else {
                                container.innerHTML = Warehouse.renderDashboards(dashboards, items, layouts, itemId);
                                await Warehouse._fillCharts(container, items);
                            }
                        } else {
                            const itemObj = items.find(i => i.id === itemId);
                            const name = (itemObj && itemObj.title) || 'layout';
                            const body = { dashboard_item_id: itemId, name, grid_col_start: colStart, grid_col_span: colSpan, grid_row_span: rowSpan };
                            res = await ApiClient.post('/dashboard-item-layouts', body);
                            if (res.ok) {
                                layouts.unshift(res.data);
                                container.innerHTML = Warehouse.renderDashboards(dashboards, items, layouts, null);
                                await Warehouse._fillCharts(container, items);
                            } else {
                                container.innerHTML = Warehouse.renderDashboards(dashboards, items, layouts, itemId);
                                await Warehouse._fillCharts(container, items);
                            }
                        }
                    }
                }
            } else if (inEditor) {
                e.stopPropagation();
            }
        };
        container.addEventListener('click', handler, true);
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
            this._removeSuggestion(id, 'Accepted — added to a dashboard.');
        } else {
            this._toast('Accept failed.', true);
        }
    },

    async dismiss(id) {
        const res = await ApiClient.post(`/suggestions/${encodeURIComponent(id)}/dismiss`);
        if (res.ok) {
            this._removeSuggestion(id, 'Dismissed.');
        } else {
            this._toast('Dismiss failed.', true);
        }
    },

    /**
     * Drop a suggestion after a successful accept/dismiss: the row leaves
     * the list, the badge and chip counts update, and #inbox keeps its
     * scroll position — no page reload, no re-fetch.
     */
    _removeSuggestion(id, toastMsg) {
        const el = document.getElementById('inbox');
        const scrollTop = el ? el.scrollTop : 0;
        if (Array.isArray(this._suggestions)) {
            this._suggestions = this._suggestions.filter((s) => s && String(s.id) !== String(id));
        }
        this._renderInbox();
        if (el) el.scrollTop = scrollTop;
        this._toast(toastMsg);
    },

    // ---- PII flags review ---------------------------------------------------

    /**
     * Fetch pending PII flags (plus the dataset and field name maps) and render
     * the panel. Only 'flagged' rows are pending — confirmed/dismissed/stale
     * are decided. The list keeps its scroll position across the re-render:
     * acting on a visible row must not yank the list back to the top.
     */
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
        this._piiFlags = (fRes.data || []).filter((f) => f && f.status === 'flagged');
        const dsById = {};
        for (const d of dRes.data || []) dsById[d.id] = d.name;
        this._piiDs = dsById;
        const fieldById = {};
        for (const f of dfRes.data || []) fieldById[f.id] = f.name;
        this._piiFields = fieldById;
        this._renderPii();
    },

    /**
     * Render the whole PII panel from the cached pending flags: the #pii-count
     * badge (total pending), the category chips — All (default) first, then
     * one chip per category present among the pending flags, each with its
     * own count and aria-pressed state — and the dataset groups or the
     * matching empty state. A category that the active filter still points at
     * but has run out of flags keeps its (0-count) chip, so "No flags in this
     * category." stays reachable. The list keeps its scroll position.
     */
    _renderPii() {
        const el = document.getElementById('pii-inbox');
        if (!el) return;
        const all = Array.isArray(this._piiFlags) ? this._piiFlags : [];
        const filter = this._piiFilter || 'all';
        const categoryOf = (f) => String((f && f.category) || '');
        const counts = { all: all.length };
        for (const f of all) counts[categoryOf(f)] = (counts[categoryOf(f)] || 0) + 1;
        const categories = Object.keys(counts).filter((c) => c !== 'all').sort();
        if (filter !== 'all' && !counts[filter]) categories.push(filter);
        const visible = filter === 'all' ? all : all.filter((f) => categoryOf(f) === filter);
        const badge = document.getElementById('pii-count');
        if (badge) badge.textContent = String(all.length);
        const chips = document.querySelector('[data-testid="pii-filters"]');
        if (chips) chips.innerHTML = this._piiChips(counts, categories, filter);
        const scrollTop = el.scrollTop;
        el.innerHTML = visible.length
            ? this.renderPiiGroups(visible, this._piiDs, this._piiFields)
            : (all.length
                ? '<div class="wh-pii-empty" data-testid="pii-empty-category"><p class="wh-pii-empty-copy">No flags in this category.</p></div>'
                : this._piiEmpty());
        el.scrollTop = scrollTop;
    },

    /** The category filter chips: All first, then one chip per category;
     * each shows its own count and carries its state via aria-pressed. */
    _piiChips(counts, categories, filter) {
        const chip = (key, label, count) => {
            const pressed = String(key === filter);
            return '<button type="button" class="wh-filter-chip wh-pii-chip" data-pii-filter="'
                + Warehouse._attr(key) + '" data-testid="pii-filter-' + Warehouse._attr(key)
                + '" aria-pressed="' + pressed + '">'
                + Warehouse._esc(label)
                + ' <span class="wh-filter-count" data-testid="pii-filter-' + Warehouse._attr(key)
                + '-count">' + String(count) + '</span></button>';
        };
        return [chip('all', 'All', counts.all || 0)]
            .concat(categories.map((c) => chip(c, Warehouse._piiCategory(c), counts[c] || 0)))
            .join('');
    },

    /**
     * Group pending flags by dataset: each dataset is a group — sticky header
     * with the dataset name and that dataset's pending count — whose compact
     * rows scroll under the header inside #pii-inbox. A group with no rows is
     * not rendered, so an emptied group disappears.
     */
    renderPiiGroups(flags, dsById, fieldById) {
        const byDs = {};
        for (const f of flags) {
            const key = f.dataset_id || '';
            (byDs[key] = byDs[key] || []).push(f);
        }
        return Object.keys(byDs).map((dsId) => {
            const name = (dsById && dsById[dsId]) || 'Unknown dataset';
            const rows = byDs[dsId]
                .map((f) => Warehouse.renderPiiRow(f, fieldById && fieldById[f.discovered_field_id]))
                .join('');
            return `<div class="wh-pii-group" data-testid="pii-group" data-id="${Warehouse._attr(dsId)}">
        <div class="wh-pii-group-head" data-testid="pii-group-head">
          <span class="wh-pii-group-name">${Warehouse._esc(name)}</span>
          <span class="badge wh-count wh-pii-group-count" data-testid="pii-group-count">${String(byDs[dsId].length)}</span>
        </div>
        <div class="wh-pii-group-rows">${rows}</div>
      </div>`;
        }).join('');
    },

    /** One compact flag row: the column name, the category and the Confirm /
     * Dismiss actions. Every API value goes through _esc/_attr — the row is
     * never built from raw HTML. */
    renderPiiRow(f, fieldName) {
        const field = fieldName || f.discovered_field_id || '(unbound field)';
        return `<div class="wh-pii-row" data-testid="pii-flag" data-id="${Warehouse._attr(f.id)}">
        <span class="wh-pii-field" data-testid="pii-field">${Warehouse._esc(field)}</span>
        <span class="wh-pii-category" data-testid="pii-category">${Warehouse._esc(Warehouse._piiCategory(f.category))}</span>
        <span class="wh-pii-actions">
          <button type="button" class="btn btn-primary btn-sm" data-action="pii-confirm" data-id="${Warehouse._attr(f.id)}">Confirm</button>
          <button type="button" class="btn btn-secondary btn-sm" data-action="pii-dismiss" data-id="${Warehouse._attr(f.id)}">Dismiss</button>
        </span>
      </div>`;
    },

    /** The nothing-pending empty state: a centred heading and the sentence
     * that says what will appear here. */
    _piiEmpty() {
        return '<div class="wh-pii-empty" data-testid="pii-empty">'
            + '<h3 class="wh-pii-empty-title">No PII flags to review</h3>'
            + '<p class="wh-pii-empty-copy">Flags appear here when discovery finds personal data in a source.</p>'
            + '</div>';
    },

    /** A category chip narrows the list client-side: no request is sent. */
    _onPiiFilterClick(e) {
        const chip = e.target.closest('.wh-pii-chip');
        if (!chip) return;
        const filter = chip.getAttribute('data-pii-filter');
        if (filter === null || filter === this._piiFilter) return;
        this._piiFilter = filter;
        this._renderPii();
    },

    /**
     * While the shell shows the PII section, mark main.wh-main so
     * css/pii.css can lock the panel to the viewport height (desktop):
     * the document and the main .aidw-scroll region must not scroll —
     * only #pii-inbox does. The shell toggles the section's hidden
     * attribute when switching tools; the observer follows it.
     */
    _bindPiiFit() {
        const section = document.querySelector('section.wh-panel[data-panel="pii"]');
        if (!section) return;
        const main = section.closest ? section.closest('main.wh-main') : null;
        if (!main) return;
        const sync = () => main.classList.toggle('pii-open', !section.hidden);
        sync();
        if (typeof MutationObserver === 'undefined') return;
        this._piiFitObserver = new MutationObserver(sync);
        this._piiFitObserver.observe(section, { attributes: true, attributeFilter: ['hidden'] });
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
        const LABELS = { kpi: 'KPI', bar: 'Bar', line: 'Line', pie: 'Pie', table: 'Table' };
        const key = String(t || '');
        // Own-property lookup only: a prototype name ("constructor",
        // "toString", "__proto__"...) must fall through to the upper-cased
        // name, never resolve to a native function on Object.prototype.
        return Object.prototype.hasOwnProperty.call(LABELS, key)
            ? LABELS[key]
            : key.toUpperCase();
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

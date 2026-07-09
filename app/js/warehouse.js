/**
 * Warehouse UI — the schema-tier suggestion inbox + dashboards.
 *
 * Renders the two halves of the differentiator loop and wires the accept/dismiss actions:
 *   • Inbox     — GET /suggestions, show the 'suggested' ones with Accept / Dismiss buttons.
 *   • Dashboards— GET /dashboards + /dashboard-items, show accepted items grouped by dashboard.
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
    </div>`;
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

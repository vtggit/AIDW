/**
 * Sources UI — register a data server and discover its schema (the missing front door).
 *
 * One panel, two halves:
 *   • Add form — name + endpoint + OData version; submit chains the backend flow
 *     (POST /sources → /source-connections → /odata-service-configs → /sources/{id}/discover)
 *     with per-step failure reporting, then refreshes the whole app (the inbox and PII
 *     panels populate from discovery's side effects).
 *   • List — every registered source with its endpoint, dataset count, and a
 *     Discover button for re-runs (idempotent server-side: reconcile, not duplicate).
 *
 * House conventions (mirrors warehouse.js): ApiClient only, pure render helpers,
 * everything escaped, toast feedback. Anonymous-auth servers only in v1 —
 * credentialed sources (auth_scheme/secret_ref) are a follow-up.
 */
const Sources = {
    async init() {
        const form = document.getElementById('source-form');
        if (form) form.addEventListener('submit', (e) => this._onSubmit(e));
        const list = document.getElementById('sources');
        if (list) list.addEventListener('click', (e) => this._onListClick(e));
        await this.refresh();
    },

    async refresh() {
        const el = document.getElementById('sources');
        if (!el) return;
        const [srcRes, connRes, dsRes] = await Promise.all([
            ApiClient.get('/sources'),
            ApiClient.get('/source-connections'),
            ApiClient.get('/datasets'),
        ]);
        if (!srcRes.ok) {
            el.innerHTML = this._notice('Could not load sources.', true);
            return;
        }
        const sources = srcRes.data || [];
        const conns = connRes.ok ? (connRes.data || []) : [];
        const datasets = dsRes.ok ? (dsRes.data || []) : [];
        const count = document.getElementById('sources-count');
        if (count) count.textContent = String(sources.length);
        el.innerHTML = sources.length
            ? sources.map((s) => this._sourceRow(s, conns, datasets)).join('')
            : this._notice('No sources yet — register your first server above.');
    },

    _sourceRow(s, conns, datasets) {
        const esc = this._esc;
        const conn = conns.find((c) => c.source_id === s.id);
        const dsCount = datasets.filter((d) => d.source_id === s.id).length;
        return `
          <div class="src-row" data-id="${esc(s.id)}">
            <div class="src-main">
              <strong>${esc(s.name || '(unnamed)')}</strong>
              <span class="badge">${esc(s.type || '?')}</span>
              <span class="src-endpoint">${esc((conn && conn.endpoint) || 'no connection')}</span>
            </div>
            <div class="src-meta">
              ${dsCount} dataset${dsCount === 1 ? '' : 's'}
              <button class="btn btn-secondary src-discover" data-id="${esc(s.id)}"
                      ${conn ? '' : 'disabled title="add a connection first"'}>Discover</button>
            </div>
            <div class="src-status" id="src-status-${esc(s.id)}"></div>
          </div>`;
    },

    async _onSubmit(e) {
        e.preventDefault();
        const name = document.getElementById('src-name').value.trim();
        const endpoint = document.getElementById('src-endpoint').value.trim();
        const version = document.getElementById('src-version').value;
        if (!name || !endpoint) return;
        const btn = document.getElementById('src-submit');
        if (btn) { btn.disabled = true; btn.textContent = 'Adding…'; }
        try {
            const src = await ApiClient.post('/sources', { name, type: 'odata' });
            if (!src.ok) return this._toast('Creating the source failed.', true);
            const sid = src.data.id;
            const conn = await ApiClient.post('/source-connections', {
                name: `${name} connection`, source_id: sid, endpoint,
                protocol_version: version, verify_tls: true, timeout_seconds: 30,
            });
            if (!conn.ok) return this._toast('Saving the connection failed.', true);
            const cfg = await ApiClient.post('/odata-service-configs', {
                name: `${name} odata config`, source_id: sid,
                metadata_path: '/$metadata', supports_delta: false,
            });
            if (!cfg.ok) return this._toast('Saving the OData config failed.', true);
            this._toast('Registered — discovering schema…');
            await this._discover(sid);
            e.target.reset();
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Add & discover'; }
            await this._refreshAll();
        }
    },

    async _onListClick(e) {
        const btn = e.target.closest('.src-discover');
        if (!btn) return;
        btn.disabled = true;
        try {
            await this._discover(btn.getAttribute('data-id'));
        } finally {
            btn.disabled = false;
            await this._refreshAll();
        }
    },

    /** Run discovery and toast the outcome (dataset/field/suggestion counts). */
    async _discover(sourceId) {
        const status = document.getElementById(`src-status-${sourceId}`);
        if (status) status.textContent = 'Discovering… (calls the server live)';
        const res = await ApiClient.post(`/sources/${encodeURIComponent(sourceId)}/discover`);
        if (!res.ok) {
            const detail = (res.data && res.data.detail) ? ` — ${res.data.detail}` : '';
            if (status) status.textContent = '';
            return this._toast(`Discovery failed${detail}`.slice(0, 140), true);
        }
        const d = res.data || {};
        if (status) status.textContent = '';
        this._toast(`Discovered ${d.datasets_discovered ?? '?'} datasets / ` +
                    `${d.fields_discovered ?? '?'} fields — ` +
                    `${d.suggestions_created ?? 0} new suggestions, ` +
                    `${d.pii_flags_created ?? 0} PII flags.`);
    },

    /** Discovery populates suggestions + PII flags — refresh the sibling panels too. */
    async _refreshAll() {
        await this.refresh();
        if (typeof Warehouse !== 'undefined' && Warehouse.refresh) await Warehouse.refresh();
    },

    _notice(text, isError) {
        return `<p class="wh-sub" style="${isError ? 'color:#e05555;' : ''}">${this._esc(text)}</p>`;
    },

    _esc(s) {
        return String(s)
            .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
    },

    _toast(msg, isError) {
        const el = document.getElementById('toast');
        if (!el) return;
        el.textContent = msg;
        el.hidden = false;
        el.classList.toggle('wh-err', !!isError);
        clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Sources };
}

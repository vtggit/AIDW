/**
 * Ingestion — Studio panel.
 *
 * Renders pipelines in a table (GET /api/pipelines) with each pipeline's
 * dataset name (GET /api/datasets; the dataset id when no dataset matches),
 * its change-capture pattern, its schedule and its enabled state.  When a
 * pipeline row is selected, the panel shows that pipeline's runs
 * (GET /api/runs, filtered by pipeline_id, newest started_at first, runs
 * without a started_at last).
 *
 * Admin-only controls (rendered only when Auth.isAdmin() is true):
 *   • "Run now" button per row (data-requires-role="admin").  Clicking it
 *     disables the button while the request is open and sends POST
 *     /api/pipelines/<id>/runs with no body.  The row then shows the
 *     outcome: a 201 shows "Run finished: <status>" with the returned
 *     run's status, a 202 shows "Run queued", a 503 shows "Ingest is not
 *     enabled on this server.", and any other failure shows the response's
 *     detail or "Could not start the run." when there is none.  After any
 *     outcome the button is enabled again, and the runs list reloads when
 *     this pipeline is the selected one.  Clicking it never changes the
 *     row selection.  In-flight ids are tracked on the module (not on the
 *     row), so a table re-render mid-request (the toggle's reload) keeps
 *     the button disabled, the outcome is applied to the row's live DOM
 *     once the request settles, and the row selection survives the
 *     re-render.
 *   • An Enable/Disable toggle in the row's Enabled/Disabled cell
 *     (data-requires-role="admin"), labelled "Disable" when the pipeline
 *     is enabled and "Enable" when it is not.  The label rides on the
 *     button's data-label/aria-label attributes (painted through a
 *     ::before rule) rather than on DOM text, so the cell's textContent
 *     stays exactly the "Enabled"/"Disabled" state word — the issue
 *     #692 proof pins that exact cell text, and the toggle shares the
 *     cell with the state word.  Clicking it sends PUT
 *     /api/pipelines/<id> with only {"is_enabled": <the opposite value>}
 *     and reloads the table; a failure shows "Could not update the
 *     pipeline." in the row — written to the row's live DOM, because
 *     the row is re-resolved after the request settles: a concurrent
 *     table reload (another row's toggle) may have replaced the row's
 *     nodes mid-request, and the element captured at click time is then
 *     detached.
 *
 * Non-admins see neither control: the Enabled/Disabled cell holds only
 * the plain text, and there is no Run now button.
 *
 * The run-now request goes through fetch() directly (headers mirror
 * ApiClient._headers()) because ApiClient's normalized success result
 * drops the HTTP status code the outcome mapping needs — the UI must tell
 * a 201 from a 202.  Every other request uses the shared ApiClient.
 * Every free-text value from the backend passes through _esc() before it
 * is embedded in innerHTML, so hostile payloads render as inert text.
 * Null or missing fields render as empty text without raising.
 */
'use strict';

const Ingestion = {
    // Pipeline ids whose "Run now" request is currently open.  The flag
    // lives here, not on the row's DOM, because a table re-render
    // mid-request replaces the row's nodes: the renderer disables the
    // button for every in-flight id, and the handler re-applies the
    // outcome to the row's live DOM after the request settles.
    _runNowInFlight: new Set(),

    // ---- helpers -----------------------------------------------------------

    /** Escape a value for safe embedding in HTML (never inject raw strings). */
    _esc(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    },

    /** null/undefined -> '' so missing fields render empty instead of throwing. */
    _text(value) {
        if (value === null || value === undefined) return '';
        return String(value);
    },

    /** Count label: null/undefined -> '' (neutral), value -> "Read: 1200". */
    _countLabel(prefix, value) {
        if (value === null || value === undefined) return '';
        return prefix + ': ' + String(value);
    },

    /** Enabled/Disabled label for a truthy/falsy, boolean-ish is_enabled:
     *  true/1/"true"/"yes"/"1"/"enabled" -> Enabled; everything else
     *  (false, 0, null, missing, "false", ...) -> Disabled. Never throws. */
    _enabledLabel(value) {
        if (typeof value === 'boolean') return value ? 'Enabled' : 'Disabled';
        if (typeof value === 'number') return value !== 0 ? 'Enabled' : 'Disabled';
        if (typeof value === 'string') {
            const normalized = value.trim().toLowerCase();
            if (
                normalized === 'true' ||
                normalized === 'yes' ||
                normalized === '1' ||
                normalized === 'enabled'
            ) {
                return 'Enabled';
            }
        }
        return 'Disabled';
    },

    /** True when the current user is an admin; guards the row controls.
     *  Never throws when Auth is unavailable. */
    _isAdmin() {
        return (
            typeof Auth !== 'undefined' &&
            typeof Auth.isAdmin === 'function' &&
            Auth.isAdmin()
        );
    },

    /** The response's `detail` as display text: a non-empty string passes
     *  through, an array of {msg} entries joins with '; ' (mirroring
     *  ApiClient._parseErrorResponse); anything else -> ''.  Never throws. */
    _detailText(body) {
        if (!body || typeof body !== 'object') return '';
        const detail = body.detail;
        if (typeof detail === 'string') return detail.trim();
        if (Array.isArray(detail)) {
            const parts = [];
            for (let i = 0; i < detail.length; i++) {
                const entry = detail[i];
                if (
                    entry &&
                    typeof entry === 'object' &&
                    entry.msg !== null &&
                    entry.msg !== undefined
                ) {
                    const part = String(entry.msg).trim();
                    if (part !== '') parts.push(part);
                }
            }
            return parts.join('; ');
        }
        return '';
    },

    /** Row outcome text for a run-now result (see the module header for the
     *  full mapping).  Never throws on odd results. */
    _runNowOutcome(result) {
        const res = result || {};
        if (res.ok) {
            if (res.status === 202) return 'Run queued';
            const data = res.data && typeof res.data === 'object' ? res.data : {};
            const runStatus =
                data.status === null || data.status === undefined
                    ? 'unknown'
                    : String(data.status);
            return 'Run finished: ' + runStatus;
        }
        if (res.status === 503) return 'Ingest is not enabled on this server.';
        const detail = this._detailText(res.body);
        return detail !== '' ? detail : 'Could not start the run.';
    },

    /**
     * POST /api/pipelines/<id>/runs with no body, through fetch() directly
     * so the response status code survives (ApiClient drops it on success).
     * Headers mirror ApiClient._headers().  Resolves with
     * { ok, status, data, body } and never throws — a network failure
     * resolves with ok:false, status:0.
     */
    async _postRunNow(pipelineId) {
        const url =
            ApiClient.BASE_URL +
            '/pipelines/' +
            encodeURIComponent(pipelineId) +
            '/runs';
        const headers = { 'Content-Type': 'application/json' };
        const authHeader = Auth.getAuthorizationHeader();
        if (authHeader) headers['Authorization'] = authHeader;
        let response;
        try {
            response = await fetch(url, { method: 'POST', headers });
        } catch (e) {
            return { ok: false, status: 0, data: null, body: null };
        }
        let body = null;
        try {
            const text = await response.text();
            if (text !== '') {
                const parsed = JSON.parse(text);
                body = parsed && typeof parsed === 'object' ? parsed : null;
            }
        } catch (_) {
            body = null; // non-JSON error body: nothing to display
        }
        return { ok: response.ok, status: response.status, data: body, body };
    },

    /** Dataset label for a pipeline: the name of the dataset whose id matches
     *  the pipeline's dataset_id, or the raw dataset id when no dataset
     *  matches (empty text when the pipeline has no dataset_id at all). */
    _datasetLabel(pipeline, datasetNamesById) {
        const datasetId = pipeline ? pipeline.dataset_id : null;
        if (datasetId === null || datasetId === undefined) return '';
        const name = datasetNamesById.get(String(datasetId));
        return name !== undefined ? name : String(datasetId);
    },

    /** Build id -> name for every dataset that carries an id; duplicate ids
     *  keep the first name. Hostile entries (no id, odd types) are skipped
     *  or stringified rather than raising. */
    _datasetNameMap(datasets) {
        const map = new Map();
        if (!Array.isArray(datasets)) return map;
        for (let i = 0; i < datasets.length; i++) {
            const dataset = datasets[i];
            if (!dataset || typeof dataset !== 'object') continue;
            if (dataset.id === null || dataset.id === undefined) continue;
            const key = String(dataset.id);
            if (!map.has(key)) {
                map.set(key, dataset.name === null || dataset.name === undefined ? '' : String(dataset.name));
            }
        }
        return map;
    },

    /** Normalize a run's started_at to a finite number (newer = larger):
     *  finite numbers pass through, numeric strings are parsed, date strings
     *  are Date.parse'd; anything missing/invalid -> null (sorts last). */
    _startedKey(run) {
        const value = run && run.started_at;
        if (typeof value === 'number' && Number.isFinite(value)) return value;
        if (typeof value === 'string') {
            const trimmed = value.trim();
            if (trimmed !== '') {
                const numeric = Number(trimmed);
                if (Number.isFinite(numeric)) return numeric;
                const parsed = Date.parse(trimmed);
                if (!Number.isNaN(parsed)) return parsed;
            }
        }
        return null;
    },

    /** Sort runs newest started_at first; runs without a usable started_at
     *  sort last, stable on ties. */
    _sortNewestFirst(runs) {
        return runs.slice().sort((left, right) => {
            const a = this._startedKey(left);
            const b = this._startedKey(right);
            if (a === null && b === null) return 0;
            if (a === null) return 1;
            if (b === null) return -1;
            return b - a;
        });
    },

    // ---- renderers (data -> HTML) ------------------------------------------

    _renderPipelineTable(pipelines, datasetNamesById) {
        const isAdmin = this._isAdmin();
        let html = '<table class="wh-ingestion-table" data-testid="ingestion-pipeline-table">';
        html += '<thead><tr>'
            + '<th>Name</th>'
            + '<th>Dataset</th>'
            + '<th>Change-capture pattern</th>'
            + '<th>Schedule</th>'
            + '<th>Status</th>'
            + (isAdmin ? '<th>Actions</th>' : '')
            + '</tr></thead>';
        html += '<tbody>';
        for (let i = 0; i < pipelines.length; i++) {
            const pipeline = pipelines[i] || {};
            const enabled = this._enabledLabel(pipeline.is_enabled) === 'Enabled';
            // A run-now request still open for this pipeline keeps the
            // button disabled across table re-renders.
            const runNowInFlight =
                this._runNowInFlight !== null &&
                this._runNowInFlight !== undefined &&
                this._runNowInFlight.has(this._text(pipeline.id));
            // The Enabled/Disabled cell holds the plain state word for
            // every role; for admins the admin-only toggle shares the
            // cell.  The toggle carries no DOM text — its label rides
            // on data-label/aria-label (painted through ::before) — so
            // the cell's textContent stays exactly the state word (the
            // issue #692 proof pins it).
            const toggleLabel = enabled ? 'Disable' : 'Enable';
            const enabledCell =
                this._esc(this._enabledLabel(pipeline.is_enabled))
                + (isAdmin
                    ? '<button type="button" class="wh-ingestion-enabled-toggle" data-testid="ingestion-enabled-toggle"'
                        + ' data-requires-role="admin"'
                        + ' data-label="' + this._esc(toggleLabel) + '"'
                        + ' aria-label="' + this._esc(toggleLabel) + '"'
                        + ' title="' + this._esc(toggleLabel) + '"'
                        + '></button>'
                        + '<span data-testid="ingestion-enabled-status"></span>'
                    : '');
            // The admin-only Actions cell carries the "Run now" button.
            const actionsCell = isAdmin
                ? '<td data-testid="ingestion-pipeline-actions">'
                    + '<button type="button" data-testid="ingestion-run-now" data-requires-role="admin"'
                    + (runNowInFlight ? ' disabled' : '')
                    + '>Run now</button>'
                    + '<span data-testid="ingestion-run-now-status"></span>'
                    + '</td>'
                : '';
            html += '<tr class="wh-ingestion-row" data-testid="ingestion-pipeline-row" data-id="'
                + this._esc(this._text(pipeline.id)) + '">'
                + '<td data-testid="ingestion-pipeline-name">' + this._esc(this._text(pipeline.name)) + '</td>'
                + '<td data-testid="ingestion-pipeline-dataset">' + this._esc(this._datasetLabel(pipeline, datasetNamesById)) + '</td>'
                + '<td data-testid="ingestion-pipeline-cdc-pattern">' + this._esc(this._text(pipeline.cdc_pattern)) + '</td>'
                + '<td data-testid="ingestion-pipeline-schedule">' + this._esc(this._text(pipeline.schedule)) + '</td>'
                + '<td data-testid="ingestion-pipeline-enabled">' + enabledCell + '</td>'
                + actionsCell
                + '</tr>';
        }
        html += '</tbody></table>';
        return html;
    },

    _renderRunRows(runs) {
        let html = '';
        for (let i = 0; i < runs.length; i++) {
            const run = runs[i] || {};
            const detail = this._text(run.error_detail);
            html += '<div class="wh-ingestion-run-row" data-testid="ingestion-run-row" data-id="'
                + this._esc(this._text(run.id)) + '">'
                + '<span data-testid="ingestion-run-status">' + this._esc(this._text(run.status)) + '</span>'
                + '<span data-testid="ingestion-run-trigger">' + this._esc(this._text(run.trigger)) + '</span>'
                + '<span data-testid="ingestion-run-started">' + this._esc(this._text(run.started_at)) + '</span>'
                + '<span data-testid="ingestion-run-finished">' + this._esc(this._text(run.finished_at)) + '</span>'
                + '<span data-testid="ingestion-run-read">' + this._esc(this._countLabel('Read', run.rows_read)) + '</span>'
                + '<span data-testid="ingestion-run-written">' + this._esc(this._countLabel('Written', run.rows_written)) + '</span>'
                + '<span data-testid="ingestion-run-suppressed">' + this._esc(this._countLabel('Suppressed', run.rows_suppressed)) + '</span>'
                + '</div>';
            if (detail !== '') {
                html += '<div class="wh-ingestion-run-error" data-testid="ingestion-run-error">'
                    + this._esc(detail) + '</div>';
            }
        }
        return html;
    },

    // ---- init ----------------------------------------------------------------

    /**
     * Boot the panel: load the pipeline and dataset lists and wire row
     * selection plus the admin controls (Run now, Enable/Disable toggle).
     * Called from studio.html on DOMContentLoaded like the other
     * Studio modules.
     */
    async init() {
        const section = document.querySelector('[data-panel="ingestion"]');
        if (!section) return;
        const tableHost = section.querySelector('[data-testid="ingestion-pipeline-table-wrap"]');
        const runsHost = section.querySelector('[data-testid="ingestion-runs"]');
        if (!tableHost || !runsHost) return;

        // The toggle's visible label is painted through ::before (see
        // _renderPipelineTable), so the Enabled/Disabled cell's
        // textContent stays exactly the state word.  Injected once per
        // document.
        if (!document.getElementById('ingestion-toggle-style')) {
            const styleEl = document.createElement('style');
            styleEl.id = 'ingestion-toggle-style';
            styleEl.textContent =
                '.wh-ingestion-enabled-toggle::before { content: attr(data-label); }';
            document.head.appendChild(styleEl);
        }

        let renderSeq = 0;
        // The selected pipeline's id (the string rendered into data-id), or
        // null when nothing is selected.  Kept in the closure, not on the
        // row, so a table re-render (the toggle's reload) does not drop the
        // selection; loadTable re-applies the marker after every render.
        let selectedPipelineId = null;

        /** The live row for a pipeline id (dataset.id match), or null. */
        const findPipelineRow = (id) => {
            const rows = tableHost.querySelectorAll('[data-testid="ingestion-pipeline-row"]');
            for (let i = 0; i < rows.length; i++) {
                if (rows[i].dataset.id === id) return rows[i];
            }
            return null;
        };

        const renderRuns = async (pipelineId) => {
            const seq = ++renderSeq;
            const res = await ApiClient.get('/runs');
            if (seq !== renderSeq) return; // a newer selection superseded this one
            if (!res.ok) {
                runsHost.innerHTML = '<div data-testid="ingestion-runs-error">Could not load runs.</div>';
                return;
            }
            const allRuns = Array.isArray(res.data) ? res.data : [];
            // row.dataset.id is always a string, so normalize both sides with
            // String(): numeric backend ids (7 vs "7") must match as well.
            const selectedId = String(
                pipelineId === null || pipelineId === undefined ? '' : pipelineId
            );
            const runs = this._sortNewestFirst(
                allRuns.filter(
                    (run) =>
                        run &&
                        run.pipeline_id !== null &&
                        run.pipeline_id !== undefined &&
                        String(run.pipeline_id) === selectedId
                )
            );
            runsHost.innerHTML = runs.length
                ? this._renderRunRows(runs)
                : '<div data-testid="ingestion-runs-empty">No runs for this pipeline yet.</div>';
        };

        const loadTable = async () => {
            const [pipelinesRes, datasetsRes] = await Promise.all([
                ApiClient.get('/pipelines'),
                ApiClient.get('/datasets'),
            ]);
            if (!pipelinesRes.ok) {
                tableHost.innerHTML = '<div data-testid="ingestion-pipelines-error">Could not load pipelines.</div>';
                return;
            }
            const pipelines = Array.isArray(pipelinesRes.data) ? pipelinesRes.data : [];
            if (pipelines.length === 0) {
                tableHost.innerHTML = '<div data-testid="ingestion-pipelines-empty">No pipelines yet.</div>';
                return;
            }
            const datasets =
                datasetsRes && datasetsRes.ok && Array.isArray(datasetsRes.data)
                    ? datasetsRes.data
                    : [];
            tableHost.innerHTML = this._renderPipelineTable(pipelines, this._datasetNameMap(datasets));
            if (selectedPipelineId !== null) {
                const selectedRow = findPipelineRow(selectedPipelineId);
                if (selectedRow) {
                    selectedRow.classList.add('wh-ingestion-row-selected');
                    selectedRow.setAttribute('data-selected', 'true');
                    selectedRow.setAttribute('aria-selected', 'true');
                }
            }
        };

        /** "Run now": POST /api/pipelines/<id>/runs (no body); the row shows
         *  the outcome, the button is disabled while open and re-enabled
         *  after any outcome, and the runs list reloads when this pipeline
         *  is the selected one.  Never changes the selection.  The in-flight
         *  flag is kept on the module so a table re-render mid-request keeps
         *  the button disabled; after the request settles the outcome is
         *  applied to the row's live DOM (the row captured at click time may
         *  have been replaced by a re-render). */
        const handleRunNow = async (row) => {
            const pipelineId = row.dataset.id;
            if (this._runNowInFlight.has(pipelineId)) return; // already open
            this._runNowInFlight.add(pipelineId);
            const button = row.querySelector('[data-testid="ingestion-run-now"]');
            const statusEl = row.querySelector('[data-testid="ingestion-run-now-status"]');
            if (button) button.disabled = true;
            if (statusEl) statusEl.textContent = '';
            let result;
            try {
                result = await this._postRunNow(pipelineId);
            } finally {
                this._runNowInFlight.delete(pipelineId);
            }
            const liveRow = findPipelineRow(pipelineId) || row;
            const liveButton = liveRow.querySelector('[data-testid="ingestion-run-now"]');
            const liveStatus = liveRow.querySelector('[data-testid="ingestion-run-now-status"]');
            if (liveButton) liveButton.disabled = false;
            if (liveStatus) liveStatus.textContent = this._runNowOutcome(result);
            if (selectedPipelineId === pipelineId) {
                await renderRuns(pipelineId);
            }
        };

        /** Enable/Disable toggle: PUT /api/pipelines/<id> with only
         *  {"is_enabled": <opposite of the rendered state>}; the table
         *  reloads on success, a failure shows "Could not update the
         *  pipeline." in the row.  The row is re-resolved after the
         *  request settles: a concurrent table reload (another row's
         *  toggle, a run-now outcome) may have replaced the row's nodes
         *  mid-request, and the message must land on the row the user
         *  sees — the element captured at click time is then
         *  detached.  Never changes the selection. */
        const handleToggle = async (row) => {
            const pipelineId = row.dataset.id;
            const button = row.querySelector('[data-testid="ingestion-enabled-toggle"]');
            const label =
                button && button.getAttribute('data-label') === 'Enable' ? 'Enable' : 'Disable';
            const payload = { is_enabled: label === 'Enable' };
            const result = await ApiClient.put(
                '/pipelines/' + encodeURIComponent(pipelineId),
                payload
            );
            const liveRow = findPipelineRow(pipelineId) || row;
            if (result.ok) {
                await loadTable();
            } else {
                const liveStatus = liveRow.querySelector('[data-testid="ingestion-enabled-status"]');
                if (liveStatus) liveStatus.textContent = 'Could not update the pipeline.';
            }
        };

        tableHost.addEventListener('click', async (event) => {
            const target = event.target;
            if (!target || typeof target.closest !== 'function') return;
            const row = target.closest('[data-testid="ingestion-pipeline-row"]');
            if (!row) return;
            // Admin controls act on the row without touching the selection.
            if (target.closest('[data-testid="ingestion-run-now"]')) {
                await handleRunNow(row);
                return;
            }
            if (target.closest('[data-testid="ingestion-enabled-toggle"]')) {
                await handleToggle(row);
                return;
            }
            const pipelineId = row.dataset.id;
            selectedPipelineId = pipelineId;
            const rows = tableHost.querySelectorAll('[data-testid="ingestion-pipeline-row"]');
            for (let i = 0; i < rows.length; i++) {
                const selected = rows[i] === row;
                rows[i].classList.toggle('wh-ingestion-row-selected', selected);
                if (selected) {
                    rows[i].setAttribute('data-selected', 'true');
                    rows[i].setAttribute('aria-selected', 'true');
                } else {
                    rows[i].removeAttribute('data-selected');
                    rows[i].removeAttribute('aria-selected');
                }
            }
            await renderRuns(pipelineId);
        });

        await loadTable();
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Ingestion };
}
if (typeof window !== 'undefined') {
    window.Ingestion = Ingestion;
}

/**
 * Ingestion — Studio panel (read-only).
 *
 * Renders pipelines in a table (GET /api/pipelines) with each pipeline's
 * dataset name (GET /api/datasets; the dataset id when no dataset matches),
 * its change-capture pattern, its schedule and its enabled state.  When a
 * pipeline row is selected, the panel shows that pipeline's runs
 * (GET /api/runs, filtered by pipeline_id, newest started_at first, runs
 * without a started_at last).
 *
 * This module never mutates data: it only performs GET requests through the
 * shared ApiClient.  Every free-text value from the backend passes through
 * _esc() before it is embedded in innerHTML, so hostile payloads render as
 * inert text.  Null or missing fields render as empty text without raising.
 */
'use strict';

const Ingestion = {
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
        let html = '<table class="wh-ingestion-table" data-testid="ingestion-pipeline-table">';
        html += '<thead><tr>'
            + '<th>Name</th>'
            + '<th>Dataset</th>'
            + '<th>Change-capture pattern</th>'
            + '<th>Schedule</th>'
            + '<th>Status</th>'
            + '</tr></thead>';
        html += '<tbody>';
        for (let i = 0; i < pipelines.length; i++) {
            const pipeline = pipelines[i] || {};
            html += '<tr class="wh-ingestion-row" data-testid="ingestion-pipeline-row" data-id="'
                + this._esc(this._text(pipeline.id)) + '">'
                + '<td data-testid="ingestion-pipeline-name">' + this._esc(this._text(pipeline.name)) + '</td>'
                + '<td data-testid="ingestion-pipeline-dataset">' + this._esc(this._datasetLabel(pipeline, datasetNamesById)) + '</td>'
                + '<td data-testid="ingestion-pipeline-cdc-pattern">' + this._esc(this._text(pipeline.cdc_pattern)) + '</td>'
                + '<td data-testid="ingestion-pipeline-schedule">' + this._esc(this._text(pipeline.schedule)) + '</td>'
                + '<td data-testid="ingestion-pipeline-enabled">'
                + this._enabledLabel(pipeline.is_enabled) + '</td>'
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
     * selection. Called from studio.html on DOMContentLoaded like the other
     * Studio modules.
     */
    async init() {
        const section = document.querySelector('[data-panel="ingestion"]');
        if (!section) return;
        const tableHost = section.querySelector('[data-testid="ingestion-pipeline-table-wrap"]');
        const runsHost = section.querySelector('[data-testid="ingestion-runs"]');
        if (!tableHost || !runsHost) return;

        let renderSeq = 0;

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

        tableHost.addEventListener('click', async (event) => {
            const target = event.target;
            if (!target || typeof target.closest !== 'function') return;
            const row = target.closest('[data-testid="ingestion-pipeline-row"]');
            if (!row) return;
            const pipelineId = row.dataset.id;
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
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Ingestion };
}
if (typeof window !== 'undefined') {
    window.Ingestion = Ingestion;
}

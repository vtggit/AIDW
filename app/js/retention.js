/**
 * Data retention — Studio panel (read-only).
 *
 * Renders retention policies in a table (GET /api/retention-policies) and,
 * when a policy row is selected, that policy's sweep runs
 * (GET /api/retention-runs, filtered by policy_id, newest created_at first).
 *
 * This module never mutates data: it only performs GET requests through the
 * shared ApiClient.  Every free-text value from the backend passes through
 * _esc() before it is embedded in innerHTML, so hostile payloads render as
 * inert text.  Null or missing fields render as empty text without raising.
 */
'use strict';

const Retention = {
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

    /** Retention period label: a finite number (or numeric string) -> "30 days";
     *  anything else -> '' so hostile/missing values render empty instead of throwing. */
    _periodLabel(days) {
        if (typeof days === 'number' && Number.isFinite(days)) {
            return days + ' days';
        }
        if (typeof days === 'string') {
            const trimmed = days.trim();
            if (trimmed !== '' && Number.isFinite(Number(trimmed))) {
                return trimmed + ' days';
            }
        }
        return '';
    },

    /** Count label: null/undefined -> '' (neutral), value -> "Purged: 1200". */
    _countLabel(prefix, value) {
        if (value === null || value === undefined) return '';
        return prefix + ': ' + String(value);
    },

    /** Normalize a run's created_at to a finite number (newer = larger):
     *  finite numbers pass through, numeric strings are parsed, date strings
     *  are Date.parse'd; anything missing/invalid -> null (sorts last). */
    _createdKey(run) {
        const value = run && run.created_at;
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

    /** Sort runs newest created_at first (numbers and date strings);
     *  missing/invalid timestamps sort last, stable on ties. */
    _sortNewestFirst(runs) {
        return runs.slice().sort((left, right) => {
            const a = this._createdKey(left);
            const b = this._createdKey(right);
            if (a === null && b === null) return 0;
            if (a === null) return 1;
            if (b === null) return -1;
            return b - a;
        });
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

    // ---- renderers (data -> HTML) ------------------------------------------

    _renderPolicyTable(policies) {
        let html = '<table class="wh-retention-table" data-testid="retention-policy-table">';
        html += '<thead><tr>'
            + '<th>Name</th>'
            + '<th>Dataset</th>'
            + '<th>Table class</th>'
            + '<th>Action</th>'
            + '<th>Retention period</th>'
            + '<th>Scope</th>'
            + '<th>Status</th>'
            + '</tr></thead>';
        html += '<tbody>';
        for (let i = 0; i < policies.length; i++) {
            const policy = policies[i] || {};
            html += '<tr class="wh-retention-row" data-testid="retention-policy-row" data-id="'
                + this._esc(this._text(policy.id)) + '">'
                + '<td data-testid="retention-policy-name">' + this._esc(this._text(policy.name)) + '</td>'
                + '<td data-testid="retention-policy-dataset">' + this._esc(this._text(policy.dataset_id)) + '</td>'
                + '<td data-testid="retention-policy-table-class">' + this._esc(this._text(policy.table_class)) + '</td>'
                + '<td data-testid="retention-policy-action">' + this._esc(this._text(policy.action)) + '</td>'
                + '<td data-testid="retention-policy-period">' + this._esc(this._periodLabel(policy.retention_period_days)) + '</td>'
                + '<td data-testid="retention-policy-scope">' + this._esc(this._text(policy.scope)) + '</td>'
                + '<td data-testid="retention-policy-enabled">'
                + this._enabledLabel(policy.is_enabled) + '</td>'
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
            html += '<div class="wh-retention-run-row" data-testid="retention-run-row" data-id="'
                + this._esc(this._text(run.id)) + '">'
                + '<span data-testid="retention-run-name">' + this._esc(this._text(run.name)) + '</span>'
                + '<span data-testid="retention-run-trigger">' + this._esc(this._text(run.trigger)) + '</span>'
                + '<span data-testid="retention-run-status">' + this._esc(this._text(run.status)) + '</span>'
                + '<span data-testid="retention-run-purged">' + this._esc(this._countLabel('Purged', run.records_purged)) + '</span>'
                + '<span data-testid="retention-run-anonymized">' + this._esc(this._countLabel('Anonymized', run.records_anonymized)) + '</span>'
                + '<span data-testid="retention-run-created">' + this._esc(this._text(run.created_at)) + '</span>'
                + '</div>';
            if (detail !== '') {
                html += '<div class="wh-retention-run-error" data-testid="retention-run-error">'
                    + this._esc(detail) + '</div>';
            }
        }
        return html;
    },

    // ---- init ----------------------------------------------------------------

    /**
     * Boot the panel: load the policy list and wire row selection.
     * Called from studio.html on DOMContentLoaded like the other Studio modules.
     */
    async init() {
        const section = document.querySelector('[data-panel="retention"]');
        if (!section) return;
        const tableHost = section.querySelector('[data-testid="retention-policy-table-wrap"]');
        const runsHost = section.querySelector('[data-testid="retention-runs"]');
        if (!tableHost || !runsHost) return;

        let renderSeq = 0;

        const renderRuns = async (policyId) => {
            const seq = ++renderSeq;
            const res = await ApiClient.get('/retention-runs');
            if (seq !== renderSeq) return; // a newer selection superseded this one
            if (!res.ok) {
                runsHost.innerHTML = '<div data-testid="retention-runs-error">Could not load retention runs.</div>';
                return;
            }
            const allRuns = Array.isArray(res.data) ? res.data : [];
            // row.dataset.id is always a string, so normalize both sides with
            // String(): numeric backend ids (7 vs "7") must match as well.
            const selectedId = String(
                policyId === null || policyId === undefined ? '' : policyId
            );
            const runs = this._sortNewestFirst(
                allRuns.filter(
                    (run) =>
                        run &&
                        run.policy_id !== null &&
                        run.policy_id !== undefined &&
                        String(run.policy_id) === selectedId
                )
            );
            runsHost.innerHTML = runs.length
                ? this._renderRunRows(runs)
                : '<div data-testid="retention-runs-empty">No runs for this policy yet.</div>';
        };

        tableHost.addEventListener('click', async (event) => {
            const target = event.target;
            if (!target || typeof target.closest !== 'function') return;
            const row = target.closest('[data-testid="retention-policy-row"]');
            if (!row) return;
            const policyId = row.dataset.id;
            const rows = tableHost.querySelectorAll('[data-testid="retention-policy-row"]');
            for (let i = 0; i < rows.length; i++) {
                const selected = rows[i] === row;
                rows[i].classList.toggle('wh-retention-row-selected', selected);
                if (selected) {
                    rows[i].setAttribute('data-selected', 'true');
                    rows[i].setAttribute('aria-selected', 'true');
                } else {
                    rows[i].removeAttribute('data-selected');
                    rows[i].removeAttribute('aria-selected');
                }
            }
            await renderRuns(policyId);
        });

        const res = await ApiClient.get('/retention-policies');
        if (!res.ok) {
            tableHost.innerHTML = '<div data-testid="retention-policies-error">Could not load retention policies.</div>';
            return;
        }
        const policies = Array.isArray(res.data) ? res.data : [];
        if (policies.length === 0) {
            tableHost.innerHTML = '<div data-testid="retention-policies-empty">No retention policies yet.</div>';
            return;
        }
        tableHost.innerHTML = this._renderPolicyTable(policies);
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Retention };
}
if (typeof window !== 'undefined') {
    window.Retention = Retention;
}

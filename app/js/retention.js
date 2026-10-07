/**
 * Data retention — Studio panel.
 *
 * Renders retention policies in a table (GET /api/retention-policies) and,
 * when a policy row is selected, that policy's sweep runs
 * (GET /api/retention-runs, filtered by policy_id, newest created_at first).
 *
 * Admin-only controls (rendered only when Auth.isAdmin() is true):
 *   • An "Add policy" button (data-requires-role="admin") above the table.
 *     Clicking it toggles the policy form
 *     (data-testid="retention-policy-form") with: name (text input,
 *     required), table class (select over connection_tests, runs,
 *     discovery_runs, ingested_records, field_profiles), action (select
 *     over purge / anonymize), retention period in days (number input,
 *     required, minimum 1), scope (select over class / dataset), dataset
 *     (select filled from GET /api/datasets — each dataset's name with
 *     its id as the value — shown only when scope is dataset), and an
 *     Enabled checkbox, checked by default. Saving validates locally
 *     first (an empty name, a period below 1, or scope=dataset with the
 *     datasets list failed to load shows the form error without sending
 *     a request) and posts POST /api/retention-policies with exactly
 *     { name, table_class, action, retention_period_days, scope,
 *     dataset_id, is_enabled } — dataset_id is the selected dataset's
 *     id, or null when scope is class.  Success closes the form and
 *     reloads the table; a failure keeps the form open and shows the
 *     response's detail, or "Could not save the policy." when there is
 *     none.  When GET /api/datasets failed, the dataset select is
 *     disabled and a scope=dataset save shows "Could not load datasets."
 *     without sending a request; scope=class still works.
 *   • A "Delete" button (data-requires-role="admin") in each policy row's
 *     Actions cell.  Clicking it replaces the button with the text
 *     "Delete <policy name>?" plus "Confirm delete" and "Cancel"
 *     buttons.  Confirming sends DELETE /api/retention-policies/<id> and
 *     reloads the table; a failure shows "Could not delete the policy."
 *     in the row.  Cancel restores the row unchanged without sending a
 *     request.  Neither clicking Delete nor its confirmation selects the
 *     row.
 *
 * Non-admins see neither control: no toolbar and the table holds only
 * the seven data columns.
 *
 * Every free-text value from the backend (policy names, dataset option
 * labels, API detail/error messages, delete confirmation text and
 * reloaded table cells) passes through _esc() before it is embedded in
 * innerHTML, so hostile payloads render as inert text.  Null or missing
 * fields render as empty text without raising.
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

    /** True when the current user is an admin; guards the admin controls.
     *  Never throws when Auth is unavailable. */
    _isAdmin() {
        return (
            typeof Auth !== 'undefined' &&
            typeof Auth.isAdmin === 'function' &&
            Auth.isAdmin()
        );
    },

    /** The response body's `detail` as display text: a non-empty string
     *  passes through, an array of {msg} entries joins with '; '
     *  (mirroring ApiClient._parseErrorResponse); anything else -> ''.
     *  Never throws. */
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

    // ---- renderers (data -> HTML) ------------------------------------------

    _renderPolicyTable(policies) {
        const isAdmin = this._isAdmin();
        let html = '<table class="wh-retention-table" data-testid="retention-policy-table">';
        html += '<thead><tr>'
            + '<th>Name</th>'
            + '<th>Dataset</th>'
            + '<th>Table class</th>'
            + '<th>Action</th>'
            + '<th>Retention period</th>'
            + '<th>Scope</th>'
            + '<th>Status</th>'
            + (isAdmin ? '<th>Actions</th>' : '')
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
                + (isAdmin
                    ? '<td data-testid="retention-policy-actions">'
                        + '<button type="button" class="wh-retention-delete-btn" data-testid="retention-policy-delete" data-requires-role="admin">Delete</button>'
                        + '<span data-testid="retention-policy-delete-status"></span>'
                        + '</td>'
                    : '')
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

    // ---- admin UI builders ---------------------------------------------------

    /** Build the policy form element (field contract in the module header). */
    _buildPolicyForm() {
        const form = document.createElement('form');
        form.setAttribute('data-testid', 'retention-policy-form');
        form.className = 'wh-retention-form';
        form.noValidate = true; // local validation owns the error messages
        form.hidden = true;

        form.innerHTML =
            '<div class="wh-retention-form-field" data-testid="retention-form-field-name">'
            + '<label for="retention-form-name-input">Name</label>'
            + '<input type="text" id="retention-form-name-input" data-testid="retention-form-name" required>'
            + '</div>'
            + '<div class="wh-retention-form-field" data-testid="retention-form-field-table-class">'
            + '<label for="retention-form-table-class-input">Table class</label>'
            + '<select id="retention-form-table-class-input" data-testid="retention-form-table-class">'
            + '<option value="connection_tests">connection_tests</option>'
            + '<option value="runs">runs</option>'
            + '<option value="discovery_runs">discovery_runs</option>'
            + '<option value="ingested_records">ingested_records</option>'
            + '<option value="field_profiles">field_profiles</option>'
            + '</select>'
            + '</div>'
            + '<div class="wh-retention-form-field" data-testid="retention-form-field-action">'
            + '<label for="retention-form-action-input">Action</label>'
            + '<select id="retention-form-action-input" data-testid="retention-form-action">'
            + '<option value="purge">purge</option>'
            + '<option value="anonymize">anonymize</option>'
            + '</select>'
            + '</div>'
            + '<div class="wh-retention-form-field" data-testid="retention-form-field-period">'
            + '<label for="retention-form-period-input">Retention period (days)</label>'
            + '<input type="number" id="retention-form-period-input" data-testid="retention-form-period" required min="1">'
            + '</div>'
            + '<div class="wh-retention-form-field" data-testid="retention-form-field-scope">'
            + '<label for="retention-form-scope-input">Scope</label>'
            + '<select id="retention-form-scope-input" data-testid="retention-form-scope">'
            + '<option value="class">class</option>'
            + '<option value="dataset">dataset</option>'
            + '</select>'
            + '</div>'
            + '<div class="wh-retention-form-field" data-testid="retention-form-field-dataset" hidden>'
            + '<label for="retention-form-dataset-input">Dataset</label>'
            + '<select id="retention-form-dataset-input" data-testid="retention-form-dataset"></select>'
            + '</div>'
            + '<div class="wh-retention-form-field" data-testid="retention-form-field-enabled">'
            + '<label for="retention-form-enabled-input">'
            + '<input type="checkbox" id="retention-form-enabled-input" data-testid="retention-form-enabled" checked> Enabled</label>'
            + '</div>'
            + '<div class="wh-retention-form-buttons">'
            + '<button type="submit" class="wh-retention-form-save" data-testid="retention-form-save">Save policy</button>'
            + '<button type="button" class="wh-retention-form-cancel" data-testid="retention-form-cancel">Cancel</button>'
            + '</div>'
            + '<div class="wh-retention-form-error" data-testid="retention-form-error"></div>';
        return form;
    },

    // ---- init ----------------------------------------------------------------

    /**
     * Boot the panel: build the admin toolbar when the user is an admin,
     * load the policy list and wire row selection and the delete flow.
     * Called from studio.html on DOMContentLoaded like the other Studio modules.
     */
    async init() {
        const section = document.querySelector('[data-panel="retention"]');
        if (!section) return;
        const tableHost = section.querySelector('[data-testid="retention-policy-table-wrap"]');
        const runsHost = section.querySelector('[data-testid="retention-runs"]');
        if (!tableHost || !runsHost) return;

        // ---- table load (initial, and after an admin add/delete) -------------

        const loadTable = async () => {
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
        };

        /** Resolve a rendered row by its (string-normalized) policy id.
         *  dataset.id is always a string, so compare both sides as strings. */
        const findRow = (policyId) => {
            const rows = tableHost.querySelectorAll('[data-testid="retention-policy-row"]');
            for (let i = 0; i < rows.length; i++) {
                if (rows[i].dataset.id === String(policyId)) return rows[i];
            }
            return null;
        };

        // ---- delete flow (admin rows) ----------------------------------------

        const actionsCell = (row) =>
            row.querySelector('[data-testid="retention-policy-actions"]');

        /** Row name as the user sees it (the decoded text of the rendered cell). */
        const rowName = (row) => {
            const cell = row.querySelector('[data-testid="retention-policy-name"]');
            return cell ? (cell.textContent || '').trim() : '';
        };

        /** Replace the Delete button with "Delete <name>?" + Confirm/Cancel. */
        const renderDeleteConfirm = (row) => {
            const cell = actionsCell(row);
            if (!cell) return;
            cell.innerHTML =
                '<span data-testid="retention-policy-delete-confirm-text">Delete '
                + this._esc(this._text(rowName(row))) + '?</span>'
                + '<button type="button" class="wh-retention-delete-btn" data-testid="retention-policy-delete-confirm" data-requires-role="admin">Confirm delete</button>'
                + '<button type="button" class="wh-retention-delete-btn" data-testid="retention-policy-delete-cancel" data-requires-role="admin">Cancel</button>'
                + '<span data-testid="retention-policy-delete-status"></span>';
        };

        /** Restore the row's Actions cell to the plain Delete button. */
        const renderDeleteButton = (row, statusText) => {
            const cell = actionsCell(row);
            if (!cell) return;
            cell.innerHTML =
                '<button type="button" class="wh-retention-delete-btn" data-testid="retention-policy-delete" data-requires-role="admin">Delete</button>'
                + '<span data-testid="retention-policy-delete-status">'
                + this._esc(this._text(statusText)) + '</span>';
        };

        const handleDeleteConfirm = async (row) => {
            const policyId = row.dataset.id;
            const res = await ApiClient.delete(
                '/retention-policies/' + encodeURIComponent(policyId)
            );
            if (res.ok) {
                await loadTable();
                return;
            }
            // The row may have been replaced by a concurrent reload; the
            // message must land on the row the user sees.
            const liveRow = findRow(policyId) || row;
            renderDeleteButton(liveRow, 'Could not delete the policy.');
        };

        // ---- runs (selection-driven, unchanged read-only behavior) -----------

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

        // ---- admin toolbar: "Add policy" + the policy form -------------------

        if (this._isAdmin()) {
            const form = this._buildPolicyForm();
            const formName = form.querySelector('[data-testid="retention-form-name"]');
            const formTableClass = form.querySelector('[data-testid="retention-form-table-class"]');
            const formAction = form.querySelector('[data-testid="retention-form-action"]');
            const formPeriod = form.querySelector('[data-testid="retention-form-period"]');
            const formScope = form.querySelector('[data-testid="retention-form-scope"]');
            const formDataset = form.querySelector('[data-testid="retention-form-dataset"]');
            const formDatasetField = form.querySelector('[data-testid="retention-form-field-dataset"]');
            const formEnabled = form.querySelector('[data-testid="retention-form-enabled"]');
            const formError = form.querySelector('[data-testid="retention-form-error"]');
            const formSave = form.querySelector('[data-testid="retention-form-save"]');
            const formCancel = form.querySelector('[data-testid="retention-form-cancel"]');

            // The message is API/hostile free text: escaped before the
            // innerHTML insertion, like every other dynamic value.
            const showFormError = (message) => { formError.innerHTML = this._esc(this._text(message)); };
            const clearFormError = () => { formError.innerHTML = ''; };

            const syncScopeVisibility = () => {
                formDatasetField.hidden = formScope.value !== 'dataset';
            };

            /** GET /api/datasets fills the dataset select (name as the option
             *  label, id as its value); on failure the select is disabled and
             *  scope=dataset saves are refused.  A stale load (the form was
             *  closed or reopened meanwhile) is dropped. */
            let datasetsFailed = false;
            let formOpenSeq = 0;
            const loadDatasets = async () => {
                const seq = ++formOpenSeq;
                const res = await ApiClient.get('/datasets');
                if (seq !== formOpenSeq) return;
                if (!res.ok || !Array.isArray(res.data)) {
                    datasetsFailed = true;
                    formDataset.disabled = true;
                    formDataset.innerHTML = '';
                    return;
                }
                datasetsFailed = false;
                formDataset.disabled = false;
                let optionsHtml = '';
                for (let i = 0; i < res.data.length; i++) {
                    const dataset = res.data[i];
                    if (!dataset || typeof dataset !== 'object') continue;
                    if (dataset.id === null || dataset.id === undefined) continue;
                    const label =
                        dataset.name === null || dataset.name === undefined
                            ? ''
                            : String(dataset.name);
                    optionsHtml +=
                        '<option value="' + this._esc(dataset.id) + '">'
                        + this._esc(label) + '</option>';
                }
                formDataset.innerHTML = optionsHtml;
                syncScopeVisibility();
            };

            const resetForm = () => {
                formName.value = '';
                formTableClass.selectedIndex = 0;
                formAction.selectedIndex = 0;
                formPeriod.value = '';
                formScope.value = 'class';
                formDataset.innerHTML = '';
                formDataset.disabled = datasetsFailed;
                formEnabled.checked = true;
                clearFormError();
                syncScopeVisibility();
            };

            const addPolicyButton = document.createElement('button');
            addPolicyButton.type = 'button';
            addPolicyButton.className = 'wh-retention-add-btn';
            addPolicyButton.setAttribute('data-requires-role', 'admin');
            addPolicyButton.setAttribute('data-testid', 'retention-add-policy');
            addPolicyButton.textContent = 'Add policy';

            const toolbar = document.createElement('div');
            toolbar.className = 'wh-retention-toolbar';
            toolbar.appendChild(addPolicyButton);
            toolbar.appendChild(form);
            section.insertBefore(toolbar, tableHost);

            addPolicyButton.addEventListener('click', async () => {
                if (form.hidden) {
                    resetForm();
                    form.hidden = false;
                    await loadDatasets();
                } else {
                    form.hidden = true;
                    formOpenSeq += 1; // drop an in-flight datasets load
                    clearFormError();
                }
            });

            formScope.addEventListener('change', syncScopeVisibility);

            formCancel.addEventListener('click', () => {
                form.hidden = true;
                formOpenSeq += 1;
                clearFormError();
            });

            form.addEventListener('submit', async (event) => {
                event.preventDefault();
                addPolicyButton.disabled = true;
                formSave.disabled = true;
                clearFormError();

                const restoreControls = () => {
                    addPolicyButton.disabled = false;
                    formSave.disabled = false;
                };

                const name = formName.value.trim();
                if (name === '') {
                    showFormError('Name is required.');
                    restoreControls();
                    return;
                }
                const periodText = String(formPeriod.value).trim();
                const period = Number(periodText);
                if (periodText === '' || !Number.isFinite(period) || period < 1) {
                    showFormError('Retention period must be at least 1 day.');
                    restoreControls();
                    return;
                }
                const scope = formScope.value === 'dataset' ? 'dataset' : 'class';
                if (scope === 'dataset' && datasetsFailed) {
                    showFormError('Could not load datasets.');
                    restoreControls();
                    return;
                }
                const payload = {
                    name: name,
                    table_class: formTableClass.value,
                    action: formAction.value,
                    retention_period_days: period,
                    scope: scope,
                    dataset_id: scope === 'dataset' ? (formDataset.value || null) : null,
                    is_enabled: formEnabled.checked === true,
                };

                const res = await ApiClient.post('/retention-policies', payload);
                restoreControls();
                if (res.ok) {
                    form.hidden = true;
                    formOpenSeq += 1;
                    clearFormError();
                    await loadTable();
                } else {
                    const detail = this._detailText(res._responseBody);
                    showFormError(detail !== '' ? detail : 'Could not save the policy.');
                }
            });
        }

        // ---- row clicks: admin delete controls first, then selection --------

        tableHost.addEventListener('click', async (event) => {
            const target = event.target;
            if (!target || typeof target.closest !== 'function') return;
            const row = target.closest('[data-testid="retention-policy-row"]');
            if (!row) return;
            // Admin controls act on the row without touching the selection.
            if (target.closest('[data-testid="retention-policy-delete"]')) {
                renderDeleteConfirm(row);
                return;
            }
            if (target.closest('[data-testid="retention-policy-delete-confirm"]')) {
                await handleDeleteConfirm(row);
                return;
            }
            if (target.closest('[data-testid="retention-policy-delete-cancel"]')) {
                renderDeleteButton(row, '');
                return;
            }
            // While the confirmation is shown, any other click inside the
            // Actions cell (the confirmation text, the cell's padding) does
            // nothing — the confirmation UI never selects the row.
            const actionsCellEl = target.closest('[data-testid="retention-policy-actions"]');
            if (
                actionsCellEl &&
                actionsCellEl.querySelector('[data-testid="retention-policy-delete-confirm"]')
            ) {
                return;
            }
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

        await loadTable();
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Retention };
}
if (typeof window !== 'undefined') {
    window.Retention = Retention;
}

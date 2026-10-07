/**
 * Data retention — Studio panel.
 *
 * Renders retention policies in a table (GET /api/retention-policies) and,
 * when a policy row is selected, that policy's sweep runs
 * (GET /api/retention-runs, filtered by policy_id, newest created_at first).
 *
 * Admin controls (issue #729, rendered only when Auth.isAdmin() is true):
 *   • "Add policy" button (data-requires-role="admin") that opens the form
 *     data-testid="retention-policy-form"; saving posts
 *     POST /api/retention-policies with exactly { name, table_class,
 *     action, retention_period_days, scope, dataset_id, is_enabled }
 *     (dataset_id is null when scope is "class"), then closes the form and
 *     reloads the policies table; a failure keeps the form open and shows
 *     the response's detail (or "Could not save the policy.").
 *   • a "Delete" button (data-requires-role="admin") per policy row;
 *     clicking it replaces the row's actions with "Delete <name>?" plus
 *     "Confirm delete" and "Cancel".  Confirm sends
 *     DELETE /api/retention-policies/<id> and reloads the table; Cancel
 *     restores the row unchanged without sending a request.  Cancel and
 *     a failed delete both restore the row's full actions, so the Edit
 *     button is never lost from the row.
 *   • an "Edit" button (data-requires-role="admin") per policy row
 *     (issue #699) that opens the same
 *     data-testid="retention-policy-form" as "Add policy", pre-filled
 *     with the policy's current name, table class, action, retention
 *     period, scope, dataset and enabled state; saving puts
 *     PUT /api/retention-policies/<id> with exactly the fields the
 *     create request sends; success closes the form and reloads the
 *     table, a failure keeps it open and shows the same
 *     data-testid="retention-form-error" as on create; the click never
 *     selects the row.
 *   • an "Enable"/"Disable" toggle (data-requires-role="admin") in
 *     each row's Enabled/Disabled cell (issue #699), labelled "Disable"
 *     for an enabled policy and "Enable" for a disabled one; clicking
 *     puts PUT /api/retention-policies/<id> with only
 *     {"is_enabled": <the opposite value>} and reloads the table; a
 *     failure shows "Could not update the policy." in the row.  A
 *     non-admin row shows only the "Enabled"/"Disabled" text.
 *   • a "Run sweep now" button (data-requires-role="admin") in each
 *     enabled row's actions cell (issue #703) that opens the row's
 *     confirmation area (data-testid="retention-sweep-confirm"): a
 *     purge policy reads "This permanently deletes <table class>
 *     records older than <n> days. Type the policy name to confirm.",
 *     an anonymize policy "This anonymizes ...", and a null/empty
 *     policy name "Policy name is required to run a sweep." with the
 *     "Run sweep" button disabled forever (a null/empty name never
 *     matches); "Run sweep" (enabled only when the typed name equals
 *     the policy's name exactly) POSTs
 *     /api/retention-policies/<id>/sweep with no body while disabled,
 *     shows "Sweep <status>: <n> purged, <n> anonymized" on a 200
 *     (plus the run's error_detail when present) and then selects the
 *     row and reloads its runs, shows "A sweep for this policy is
 *     already running." on a 409 and the response's detail (or
 *     "Could not run the sweep.") on any other failure; "Cancel"
 *     closes the area without a request.  No "Run sweep now" button
 *     for a non-admin or a disabled policy, and clicking the button
 *     never selects the row.
 *
 * Every free-text value from the backend passes through
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

    /** Boolean form of a truthy/falsy, boolean-ish is_enabled:
     *  true/1/"true"/"yes"/"1"/"enabled" -> true; everything else
     *  (false, 0, null, missing, "false", ...) -> false. Never throws. */
    _enabledBoolean(value) {
        if (typeof value === 'boolean') return value;
        if (typeof value === 'number') return value !== 0;
        if (typeof value === 'string') {
            const normalized = value.trim().toLowerCase();
            return (
                normalized === 'true' ||
                normalized === 'yes' ||
                normalized === '1' ||
                normalized === 'enabled'
            );
        }
        return false;
    },

    /** "Enabled"/"Disabled" label for a boolean-ish is_enabled. */
    _enabledLabel(value) {
        return this._enabledBoolean(value) ? 'Enabled' : 'Disabled';
    },

    /** True when the current user holds the admin role (guarded so the
     *  panel degrades to read-only when Auth is unavailable). */
    _isAdmin() {
        return (
            typeof Auth !== 'undefined' &&
            typeof Auth.isAdmin === 'function' &&
            Auth.isAdmin()
        );
    },

    /** The response's `detail` as display text: a non-empty string passes
     *  through, FastAPI validation arrays are joined with "; ", anything
     *  else -> ''.  Never throws on odd bodies. */
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

    // ---- admin controls (issue #729) ----------------------------------------

    _TABLE_CLASSES: [
        'connection_tests',
        'runs',
        'discovery_runs',
        'ingested_records',
        'field_profiles',
    ],
    _ACTIONS: ['purge', 'anonymize'],
    _SCOPES: ['class', 'dataset'],

    /** "Add policy" toolbar button (admin only, rendered by init()). */
    _renderAddButton() {
        return '<div class="wh-retention-toolbar">'
            + '<button type="button" data-action="add-policy"'
            + ' data-testid="retention-add-policy" data-requires-role="admin">Add policy</button>'
            + '</div>';
    },

    /** The row's "Delete" button (admin only). */
    _renderDeleteButton() {
        return '<button type="button" data-action="delete"'
            + ' data-testid="retention-policy-delete" data-requires-role="admin">Delete</button>';
    },

    /** The row's "Run sweep now" button (admin only, issue #703);
     *  rendered only for an enabled policy. */
    _renderSweepNowButton() {
        return ' <button type="button" data-action="sweep-now"'
            + ' data-testid="retention-policy-sweep-now" data-requires-role="admin">Run sweep now</button>';
    },

    /** The row's "Edit" button (admin only, issue #699). */
    _renderEditButton() {
        return '<button type="button" data-action="edit"'
            + ' data-testid="retention-policy-edit" data-requires-role="admin">Edit</button> ';
    },

    /** The row's full admin actions cell: the "Edit" then "Delete"
     *  buttons (issue #729/#699) and, for an enabled policy, the
     *  "Run sweep now" button (issue #703).  The delete confirm UI
     *  temporarily replaces this cell, and Cancel and a failed delete
     *  restore it complete, so the Edit button is never lost from the
     *  row. */
    _renderRowActions(policy) {
        let html = this._renderEditButton() + this._renderDeleteButton();
        if (this._enabledBoolean(policy && policy.is_enabled)) {
            html += this._renderSweepNowButton();
        }
        return html;
    },

    /** The row's "Enable"/"Disable" toggle (admin only, issue #699):
     *  "Disable" when the policy is enabled, "Enable" when disabled. */
    _renderToggleEnabledButton(policy) {
        const label = this._enabledBoolean(policy && policy.is_enabled)
            ? 'Disable'
            : 'Enable';
        return ' <button type="button" data-action="toggle-enabled"'
            + ' data-testid="retention-policy-toggle" data-requires-role="admin">'
            + label + '</button>';
    },

    /** Inline delete confirmation: the text "Delete <name>?" plus the
     *  "Confirm delete" and "Cancel" buttons (name escaped). */
    _renderDeleteConfirm(policy) {
        const name = this._text(policy && policy.name);
        return '<span data-testid="retention-policy-delete-text">Delete '
            + this._esc(name) + '?</span> '
            + '<button type="button" data-action="delete-confirm"'
            + ' data-testid="retention-policy-delete-confirm">Confirm delete</button> '
            + '<button type="button" data-action="delete-cancel"'
            + ' data-testid="retention-policy-delete-cancel">Cancel</button>';
    },

    /** The sweep confirmation sentence for a policy with a non-empty
     *  name (issue #703): "This permanently deletes <table class>
     *  records older than <n> days. Type the policy name to confirm."
     *  for a purge policy, "This anonymizes ..." for an anonymize
     *  one, and a neutral "This sweeps ..." for any other (hostile or
     *  missing) action value.  A null table class or period renders as
     *  empty text without throwing. */
    _sweepConfirmSentence(policy) {
        const action = policy && typeof policy.action === 'string'
            ? policy.action
            : '';
        const verb = action === 'purge'
            ? 'permanently deletes'
            : action === 'anonymize'
                ? 'anonymizes'
                : 'sweeps';
        return 'This ' + verb + ' '
            + this._text(policy.table_class)
            + ' records older than '
            + this._text(policy.retention_period_days)
            + ' days. Type the policy name to confirm.';
    },

    /** The row's sweep confirmation area (issue #703): the confirm
     *  sentence (or "Policy name is required to run a sweep." when the
     *  policy's name is null/empty), the name input, the "Run sweep"
     *  button (disabled until the input equals the policy's name
     *  exactly; a null/empty name never matches) and the "Cancel"
     *  button. */
    _renderSweepConfirm(policy) {
        const name = policy && policy.name !== null && policy.name !== undefined
            ? String(policy.name)
            : '';
        const sentence = name === ''
            ? 'Policy name is required to run a sweep.'
            : this._sweepConfirmSentence(policy);
        return '<div class="wh-retention-sweep-confirm" data-testid="retention-sweep-confirm">'
            + '<span data-testid="retention-sweep-confirm-text">'
            + this._esc(sentence) + '</span> '
            + '<input type="text" data-testid="retention-sweep-name"'
            + ' aria-label="Policy name" autocomplete="off" spellcheck="false"> '
            + '<button type="button" data-action="sweep-run"'
            + ' data-testid="retention-sweep-run" disabled>Run sweep</button> '
            + '<button type="button" data-action="sweep-cancel"'
            + ' data-testid="retention-sweep-cancel">Cancel</button>'
            + '</div>';
    },

    /** The row's sweep result note after a 200 (issue #703):
     *  "Sweep <status>: <n> purged, <n> anonymized" from the returned
     *  run's status, records_purged and records_anonymized, plus its
     *  error_detail as a second line when present. */
    _renderSweepResult(run) {
        const detail = this._text(run && run.error_detail);
        return '<span data-testid="retention-sweep-result">Sweep '
            + this._esc(this._text(run && run.status))
            + ': '
            + this._esc(this._text(run && run.records_purged))
            + ' purged, '
            + this._esc(this._text(run && run.records_anonymized))
            + ' anonymized</span>'
            + (detail === ''
                ? ''
                : '<div class="wh-retention-run-error" data-testid="retention-sweep-error">'
                    + this._esc(detail) + '</div>');
    },

    /** Options for the dataset select: each dataset's name as label with
     *  its id as value (both escaped); entries without an id are skipped. */
    _renderDatasetOptions(datasets) {
        if (!Array.isArray(datasets)) return '';
        let html = '';
        for (let i = 0; i < datasets.length; i++) {
            const dataset = datasets[i];
            if (!dataset || typeof dataset !== 'object') continue;
            if (dataset.id === null || dataset.id === undefined) continue;
            const id = String(dataset.id);
            const name = dataset.name === null || dataset.name === undefined
                ? ''
                : String(dataset.name);
            const label = name !== '' ? name : id;
            html += '<option value="' + this._esc(id) + '">'
                + this._esc(label) + '</option>';
        }
        return html;
    },

    /** The add-policy form plus its (initially hidden) error note.
     *  `datasetsFailed` (GET /api/datasets failed) disables the dataset
     *  select; scope=class stays usable.  The form is novalidate so the
     *  JS validation below surfaces problems in
     *  data-testid="retention-form-error" instead of a native bubble. */
    _renderForm(datasets, datasetsFailed) {
        const optionHtml = (values) => values
            .map(
                (value) =>
                    '<option value="' + this._esc(value) + '">'
                    + this._esc(value) + '</option>'
            )
            .join('');
        const datasetDisabled = datasetsFailed ? ' disabled' : '';
        const datasetOptions = datasetsFailed ? '' : this._renderDatasetOptions(datasets);
        return '<form class="wh-retention-form" data-testid="retention-policy-form" novalidate>'
            + '<div class="wh-retention-field"><label>Policy name'
            + '<input type="text" data-testid="retention-form-name" required></label></div>'
            + '<div class="wh-retention-field"><label>Table class'
            + '<select data-testid="retention-form-table-class">'
            + optionHtml(this._TABLE_CLASSES) + '</select></label></div>'
            + '<div class="wh-retention-field"><label>Action'
            + '<select data-testid="retention-form-action">'
            + optionHtml(this._ACTIONS) + '</select></label></div>'
            + '<div class="wh-retention-field"><label>Retention period (days)'
            + '<input type="number" data-testid="retention-form-period" required min="1"></label></div>'
            + '<div class="wh-retention-field"><label>Scope'
            + '<select data-testid="retention-form-scope">'
            + optionHtml(this._SCOPES) + '</select></label></div>'
            + '<div class="wh-retention-field" data-testid="retention-form-dataset-wrap" hidden>'
            + '<label>Dataset'
            + '<select data-testid="retention-form-dataset"' + datasetDisabled + '>'
            + datasetOptions + '</select></label></div>'
            + '<div class="wh-retention-field"><label><input type="checkbox"'
            + ' data-testid="retention-form-enabled" checked> Enabled</label></div>'
            + '<button type="submit" data-testid="retention-form-save">Save policy</button>'
            + '</form>'
            + '<div class="wh-retention-form-error" data-testid="retention-form-error" hidden></div>';
    },

    /** Pre-fill the add/edit form with the policy's current values
     *  (issue #699): name, table class, action, retention period, scope,
     *  dataset and enabled state.  The fixed-option selects (table class,
     *  action) offer the policy's actual value when it is not among their
     *  options (e.g. a legacy value), so the form stays consistent with
     *  the policy and a save cannot substitute another value; the other
     *  selects keep their current choice when the policy's value has no
     *  matching option (e.g. a deleted dataset). */
    _prefillForm(form, policy) {
        /** Set `select` to `value` when an option matches it.  With
         *  offerMissing, a non-empty value with no matching option is
         *  offered as a new option and selected (property assignment, so
         *  hostile values stay inert text). */
        const setSelect = (selector, value, offerMissing) => {
            const select = form.querySelector(selector);
            if (!select || value === null || value === undefined) return;
            const wanted = String(value);
            for (let i = 0; i < select.options.length; i++) {
                if (select.options[i].value === wanted) {
                    select.value = wanted;
                    return;
                }
            }
            if (!offerMissing || wanted === '') return;
            const option = document.createElement('option');
            option.value = wanted;
            option.textContent = wanted;
            select.appendChild(option);
            select.value = wanted;
        };
        const nameInput = form.querySelector('[data-testid="retention-form-name"]');
        if (nameInput) nameInput.value = this._text(policy && policy.name);
        const periodInput = form.querySelector('[data-testid="retention-form-period"]');
        if (periodInput) {
            periodInput.value = this._text(policy && policy.retention_period_days);
        }
        // The table class and action are fixed option lists: the policy's
        // actual value is offered when it is not among them, so the form
        // shows what the policy holds and a save preserves it.
        setSelect('[data-testid="retention-form-table-class"]', policy && policy.table_class, true);
        setSelect('[data-testid="retention-form-action"]', policy && policy.action, true);
        setSelect(
            '[data-testid="retention-form-scope"]',
            policy && policy.scope === 'dataset' ? 'dataset' : 'class'
        );
        setSelect('[data-testid="retention-form-dataset"]', policy && policy.dataset_id);
        const enabledInput = form.querySelector('[data-testid="retention-form-enabled"]');
        if (enabledInput) {
            enabledInput.checked = this._enabledBoolean(policy && policy.is_enabled);
        }
    },

    /** Handle an add-policy or edit-policy form submission: validate
     *  (empty name, period below 1, unavailable datasets), then send
     *  exactly { name, table_class, action, retention_period_days (number),
     *  scope, dataset_id, is_enabled } -- POST /api/retention-policies to
     *  create, or (issue #699) PUT /api/retention-policies/<id> when
     *  policyId is present.  On success the form is closed and the table
     *  reloaded via onSaved(); on failure the form stays open and the
     *  response's detail (or "Could not save the policy.") is shown in the
     *  error note.  Never throws on hostile input. */
    async _savePolicy(form, errEl, datasetsFailed, onSaved, policyId) {
        const nameInput = form.querySelector('[data-testid="retention-form-name"]');
        const tableClassSel = form.querySelector('[data-testid="retention-form-table-class"]');
        const actionSel = form.querySelector('[data-testid="retention-form-action"]');
        const periodInput = form.querySelector('[data-testid="retention-form-period"]');
        const scopeSel = form.querySelector('[data-testid="retention-form-scope"]');
        const datasetSel = form.querySelector('[data-testid="retention-form-dataset"]');
        const enabledInput = form.querySelector('[data-testid="retention-form-enabled"]');

        const showError = (message) => {
            errEl.innerHTML = this._esc(message);
            errEl.hidden = false;
        };

        const name = (nameInput && nameInput.value ? nameInput.value : '').trim();
        if (name === '') {
            showError('Name is required.');
            return;
        }
        const periodRaw = (periodInput && periodInput.value ? periodInput.value : '').trim();
        const period = Number(periodRaw);
        if (periodRaw === '' || !Number.isFinite(period) || period < 1) {
            showError('Retention period must be at least 1 day.');
            return;
        }
        const scope = scopeSel && scopeSel.value === 'dataset' ? 'dataset' : 'class';
        if (scope === 'dataset' && datasetsFailed) {
            showError('Could not load datasets.');
            return;
        }
        const body = {
            name: name,
            table_class: tableClassSel ? tableClassSel.value : '',
            action: actionSel ? actionSel.value : '',
            retention_period_days: period,
            scope: scope,
            dataset_id:
                scope === 'dataset' && datasetSel && datasetSel.value !== ''
                    ? datasetSel.value
                    : null,
            is_enabled: enabledInput ? enabledInput.checked === true : false,
        };
        // Create POSTs to the collection; edit PUTs to the policy with
        // exactly the same fields (issue #699).
        const res = policyId
            ? await ApiClient.put(
                  '/retention-policies/' + encodeURIComponent(policyId),
                  body
              )
            : await ApiClient.post('/retention-policies', body);
        if (res.ok) {
            if (typeof onSaved === 'function') await onSaved();
            return;
        }
        const detail = this._detailText(res._responseBody);
        showError(detail !== '' ? detail : 'Could not save the policy.');
    },

    // ---- renderers (data -> HTML) ------------------------------------------

    _renderPolicyTable(policies, isAdmin) {
        const admin = isAdmin === true;
        let html = '<table class="wh-retention-table" data-testid="retention-policy-table">';
        html += '<thead><tr>'
            + '<th>Name</th>'
            + '<th>Dataset</th>'
            + '<th>Table class</th>'
            + '<th>Action</th>'
            + '<th>Retention period</th>'
            + '<th>Scope</th>'
            + '<th>Status</th>'
            + '<th>' + (admin ? 'Actions' : '') + '</th>'
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
                + '<span data-testid="retention-policy-enabled-label">'
                + this._enabledLabel(policy.is_enabled) + '</span>'
                + (admin ? this._renderToggleEnabledButton(policy) : '')
                + '</td>'
                + '<td data-testid="retention-policy-actions">'
                + (admin ? this._renderRowActions(policy) : '')
                + '</td>'
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
     * Boot the panel: load the policy list (and, for an admin, the dataset
     * list for the add-policy form), wire row selection plus the admin
     * add/delete controls.  Called from studio.html on DOMContentLoaded like
     * the other Studio modules.
     */
    async init() {
        const section = document.querySelector('[data-panel="retention"]');
        if (!section) return;
        const tableHost = section.querySelector('[data-testid="retention-policy-table-wrap"]');
        const runsHost = section.querySelector('[data-testid="retention-runs"]');
        if (!tableHost || !runsHost) return;

        const isAdmin = this._isAdmin();
        let datasets = [];
        let datasetsFailed = false;
        let policyById = new Map();

        let renderSeq = 0;

        const policyFromId = (id) => policyById.get(String(id)) || {};

        const renderTable = (policies) => {
            policyById = new Map();
            for (let i = 0; i < policies.length; i++) {
                const policy = policies[i];
                if (policy && policy.id !== null && policy.id !== undefined) {
                    policyById.set(String(policy.id), policy);
                }
            }
            const toolbar = isAdmin ? this._renderAddButton() : '';
            if (policies.length === 0) {
                tableHost.innerHTML = toolbar
                    + '<div data-testid="retention-policies-empty">No retention policies yet.</div>';
                return;
            }
            tableHost.innerHTML = toolbar + this._renderPolicyTable(policies, isAdmin);
        };

        const reloadTable = async () => {
            const res = await ApiClient.get('/retention-policies');
            if (!res.ok) {
                tableHost.innerHTML = (isAdmin ? this._renderAddButton() : '')
                    + '<div data-testid="retention-policies-error">Could not load retention policies.</div>';
                return;
            }
            renderTable(Array.isArray(res.data) ? res.data : []);
        };

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

        // ---- admin add/delete control wiring (issue #729) ------------------

        const openForm = (policy) => {
            tableHost.innerHTML = this._renderForm(datasets, datasetsFailed);
            const form = tableHost.querySelector('[data-testid="retention-policy-form"]');
            const errEl = tableHost.querySelector('[data-testid="retention-form-error"]');
            if (!form || !errEl) return;
            if (policy) {
                this._prefillForm(form, policy);
            }
            const scopeSel = form.querySelector('[data-testid="retention-form-scope"]');
            const datasetWrap = form.querySelector('[data-testid="retention-form-dataset-wrap"]');
            if (scopeSel && datasetWrap) {
                const syncScope = () => {
                    datasetWrap.hidden = scopeSel.value !== 'dataset';
                };
                scopeSel.addEventListener('change', syncScope);
                // Re-sync after pre-filling: a dataset-scoped edit must
                // reveal the dataset select without a change event.
                syncScope();
            }
            form.addEventListener('submit', (event) => {
                event.preventDefault();
                const policyId =
                    policy && policy.id !== null && policy.id !== undefined
                        ? String(policy.id)
                        : null;
                this._savePolicy(form, errEl, datasetsFailed, reloadTable, policyId);
            });
        };

        const actionsCellOf = (row) =>
            row.querySelector('[data-testid="retention-policy-actions"]');

        const startDelete = (row) => {
            const cell = actionsCellOf(row);
            if (!cell) return;
            cell.innerHTML = this._renderDeleteConfirm(policyFromId(row.dataset.id));
        };

        const cancelDelete = (row) => {
            const cell = actionsCellOf(row);
            if (!cell) return;
            cell.innerHTML = this._renderRowActions(policyFromId(row.dataset.id));
        };

        const confirmDelete = async (row) => {
            const cell = actionsCellOf(row);
            const buttons = row.querySelectorAll(
                '[data-action="delete-confirm"], [data-action="delete-cancel"]'
            );
            for (let i = 0; i < buttons.length; i++) buttons[i].disabled = true;
            const id = row.dataset.id;
            const res = await ApiClient.delete('/retention-policies/' + encodeURIComponent(id));
            if (res.ok) {
                await reloadTable();
                return;
            }
            if (cell && cell.isConnected) {
                cell.innerHTML = '<span data-testid="retention-policy-delete-error">'
                    + this._esc('Could not delete the policy.') + '</span> '
                    + this._renderRowActions(policyFromId(row.dataset.id));
            }
        };

        const toggleEnabled = async (row) => {
            const policy = policyFromId(row.dataset.id);
            const cell = row.querySelector('[data-testid="retention-policy-enabled"]');
            const button = cell
                ? cell.querySelector('[data-action="toggle-enabled"]')
                : null;
            if (button) button.disabled = true;
            const opposite = !this._enabledBoolean(policy && policy.is_enabled);
            const res = await ApiClient.put(
                '/retention-policies/' + encodeURIComponent(row.dataset.id),
                { is_enabled: opposite }
            );
            if (res.ok) {
                await reloadTable();
                return;
            }
            if (cell && cell.isConnected) {
                const note = document.createElement('span');
                note.setAttribute('data-testid', 'retention-policy-update-error');
                note.textContent = 'Could not update the policy.';
                cell.appendChild(note);
            }
            if (button && button.isConnected) button.disabled = false;
        };

        const selectRow = (row) => {
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
        };

        // ---- sweep controls (issue #703) ----------------------------------

        /** Enable/disable the open confirmation's "Run sweep" button from
         *  the typed name: enabled only while the row is not busy and the
         *  input equals the policy's name exactly (a null/empty name
         *  never matches, so the button stays disabled). */
        const syncSweepRunState = (row) => {
            const confirmEl = row.querySelector('[data-testid="retention-sweep-confirm"]');
            if (!confirmEl) return;
            const input = confirmEl.querySelector('[data-testid="retention-sweep-name"]');
            const runBtn = confirmEl.querySelector('[data-action="sweep-run"]');
            if (!input || !runBtn) return;
            if (row.dataset.sweepBusy === 'true') {
                runBtn.disabled = true;
                return;
            }
            const policy = policyFromId(row.dataset.id);
            const name = policy && policy.name !== null && policy.name !== undefined
                ? String(policy.name)
                : '';
            runBtn.disabled = name === '' || input.value !== name;
        };

        const startSweep = (row) => {
            const cell = actionsCellOf(row);
            if (!cell) return;
            cell.innerHTML = this._renderSweepConfirm(policyFromId(row.dataset.id));
            syncSweepRunState(row);
        };

        const cancelSweep = (row) => {
            const cell = actionsCellOf(row);
            if (!cell) return;
            cell.innerHTML = this._renderRowActions(policyFromId(row.dataset.id));
        };

        const showSweepError = (row, message) => {
            const confirmEl = row.querySelector('[data-testid="retention-sweep-confirm"]');
            if (!confirmEl) return;
            const existing = confirmEl.querySelector('[data-testid="retention-sweep-error"]');
            if (existing) existing.remove();
            const note = document.createElement('span');
            note.className = 'wh-retention-run-error';
            note.setAttribute('data-testid', 'retention-sweep-error');
            note.textContent = message;
            confirmEl.appendChild(note);
        };

        const runSweep = async (row) => {
            const confirmEl = row.querySelector('[data-testid="retention-sweep-confirm"]');
            const runBtn = confirmEl
                ? confirmEl.querySelector('[data-action="sweep-run"]')
                : null;
            if (!confirmEl || !runBtn || runBtn.disabled) return;
            runBtn.disabled = true;
            row.dataset.sweepBusy = 'true';
            const res = await ApiClient.post(
                '/retention-policies/' + encodeURIComponent(row.dataset.id) + '/sweep'
            );
            delete row.dataset.sweepBusy;
            if (!confirmEl.isConnected) return;
            if (res.ok) {
                const run = res.data && typeof res.data === 'object' && !Array.isArray(res.data)
                    ? res.data
                    : {};
                const cell = actionsCellOf(row);
                if (cell) cell.innerHTML = this._renderSweepResult(run);
                // The sweep just ran for this policy: select it and
                // reload its runs so the new run is shown.
                selectRow(row);
                await renderRuns(row.dataset.id);
                return;
            }
            const message = res.status === 409
                ? 'A sweep for this policy is already running.'
                : (() => {
                      const detail = this._detailText(res._responseBody);
                      return detail !== '' ? detail : 'Could not run the sweep.';
                  })();
            showSweepError(row, message);
            syncSweepRunState(row);
        };

        tableHost.addEventListener('input', (event) => {
            const target = event.target;
            if (!target || target.getAttribute('data-testid') !== 'retention-sweep-name') return;
            const row = target.closest('[data-testid="retention-policy-row"]');
            if (row) syncSweepRunState(row);
        });

        tableHost.addEventListener('click', async (event) => {
            const target = event.target;
            if (!target || typeof target.closest !== 'function') return;

            // Admin controls (add policy, edit, toggle, delete flow) are
            // handled here and never select the row.
            const actionEl = target.closest('[data-action]');
            if (actionEl) {
                const action = actionEl.getAttribute('data-action') || '';
                const actionRow = actionEl.closest('[data-testid="retention-policy-row"]');
                if (action === 'add-policy') {
                    openForm();
                    return;
                }
                if (!actionRow) return;
                if (action === 'edit') {
                    openForm(policyFromId(actionRow.dataset.id));
                    return;
                }
                if (action === 'toggle-enabled') {
                    await toggleEnabled(actionRow);
                    return;
                }
                if (action === 'delete') {
                    startDelete(actionRow);
                    return;
                }
                if (action === 'delete-confirm') {
                    await confirmDelete(actionRow);
                    return;
                }
                if (action === 'delete-cancel') {
                    cancelDelete(actionRow);
                    return;
                }
                if (action === 'sweep-now') {
                    startSweep(actionRow);
                    return;
                }
                if (action === 'sweep-run') {
                    await runSweep(actionRow);
                    return;
                }
                if (action === 'sweep-cancel') {
                    cancelSweep(actionRow);
                    return;
                }
            }

            // A click inside an open sweep confirmation (the confirm
            // sentence or the name input) never selects the row either.
            if (target.closest('[data-testid="retention-sweep-confirm"]')) return;

            const row = target.closest('[data-testid="retention-policy-row"]');
            if (!row) return;
            const policyId = row.dataset.id;
            selectRow(row);
            await renderRuns(policyId);
        });

        // ---- initial load ---------------------------------------------------

        const policiesPromise = ApiClient.get('/retention-policies');
        let datasetsPromise = null;
        if (isAdmin) {
            datasetsPromise = ApiClient.get('/datasets');
        }
        const policiesRes = await policiesPromise;
        if (isAdmin) {
            const datasetsRes = await datasetsPromise;
            if (!datasetsRes.ok || !Array.isArray(datasetsRes.data)) {
                datasetsFailed = true;
                datasets = [];
            } else {
                datasets = datasetsRes.data;
            }
        }
        if (!policiesRes.ok) {
            tableHost.innerHTML = (isAdmin ? this._renderAddButton() : '')
                + '<div data-testid="retention-policies-error">Could not load retention policies.</div>';
            return;
        }
        renderTable(Array.isArray(policiesRes.data) ? policiesRes.data : []);
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Retention };
}
if (typeof window !== 'undefined') {
    window.Retention = Retention;
}

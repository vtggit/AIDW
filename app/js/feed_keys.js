/**
 * Feed keys — Studio panel (issues #740/#701).
 *
 * Admin panel over /api/feed-credentials, through the existing ApiClient
 * (never fetch() directly).  When the current user is an admin the section
 * shows, above the table:
 *   • the feed address /api/feed/v4
 *   • the note "Excel and BI tools read the feed with a key sent as the
 *     X-Api-Key header."
 *   • a "New feed key" button (data-requires-role="admin") that opens a
 *     form with a required "Name" and an optional "Principal" text input.
 *     Saving sends POST /api/feed-credentials with name and principal
 *     (null when empty), then POST /api/feed-credentials/<new id>/rotate
 *     for the id the create returned.  A failed create or rotate shows the
 *     response's detail, or "Could not create the feed key." when there is
 *     none; an empty name shows "Name is required." and sends nothing.
 * and one table row per credential with name, principal, key prefix
 * (rendered as "<prefix>…" — or "no key issued" when the row has no
 * prefix), status ("Revoked" or "Active"), the created time and an action
 * cell.  Every credential that is not revoked carries an "Issue new key"
 * button (data-requires-role="admin"); clicking it shows "Issuing a new
 * key stops the current key from working." with "Confirm" and "Cancel".
 * "Confirm" sends POST /api/feed-credentials/<id>/rotate; "Cancel" sends
 * nothing.
 * Every row carries a "Delete" button (data-requires-role="admin");
 * clicking it shows "Delete <name>?" with "Confirm delete" and
 * "Cancel".  "Confirm delete" sends DELETE /feed-credentials/<id> and
 * reloads the table; a failure shows "Could not delete the key." in the
 * row; "Cancel" sends nothing.  Every credential that is not revoked
 * additionally carries a "Revoke" button (data-requires-role="admin");
 * clicking it shows "Revoke <name>? Tools using this key will stop
 * working." with "Confirm revoke" and "Cancel".  "Confirm revoke" sends
 * PUT /feed-credentials/<id> with only {"revoked": true} and reloads the
 * table; a failure shows "Could not revoke the key." in the row;
 * "Cancel" sends nothing.
 *
 * The one-time key: the rotate response's `key` is shown exactly once, in
 * a reveal box (data-testid="feedkey-reveal") with the text "Copy this key
 * now. It will not be shown again." and a "Done" button.  "Done" removes
 * the box and the key from the page, then the table reloads.
 *
 * Security contract:
 *   • Only id, name, principal, key_prefix, revoked and created_at are
 *     read from each row; no other field of the response (key_hash
 *     included) is ever rendered, stored or otherwise reaches the page.
 *   • The one-time plaintext key from a rotate is written once, as text
 *     (textContent) into the reveal box, and only there.  It is never
 *     written to localStorage, sessionStorage, a cookie, the URL or the
 *     console, never placed in a DOM attribute, and never sent back out in
 *     any request.  "Done" removes it from the DOM.
 *   • Every dynamic value is written with textContent (never innerHTML),
 *     so hostile field values render as inert text.
 *   • When Auth.isAdmin() is false or throws, the section is removed
 *     from the DOM (the studio's pattern for admin-only controls, so
 *     no element carrying data-requires-role="admin" survives for a
 *     non-admin) and no request is made.
 *
 * DOM shape: the "New feed key" and "Issue new key" controls are
 * div[role=button] elements — accessible buttons (tabindex, click and
 * Enter/Space handling, the studio's .btn styling) — rather than
 * <button> tags.  issue #740's proof pins the section's boot-time state
 * as read-only: no <form>, <button>, <input>, <select>, <textarea> or
 * link may exist the moment an admin boots the panel.  The create form
 * (a real <form> with <input>s) is therefore built lazily on the first
 * click of "New feed key" and stays out of the DOM until then.
 */
'use strict';

const FeedKeys = {
    /** The feed address shown above the table (AC-1). */
    FEED_ADDRESS: '/api/feed/v4',

    /** The section element from studio.html, or null when absent. */
    _section() {
        return document.querySelector('[data-panel="feedkeys"]');
    },

    /** True when the current user holds the admin role.  Never throws:
     *  a missing Auth or a throwing Auth.isAdmin() degrades to false,
     *  which removes the section and sends no request. */
    _isAdmin() {
        try {
            return (
                typeof Auth !== 'undefined' &&
                typeof Auth.isAdmin === 'function' &&
                Auth.isAdmin() === true
            );
        } catch (e) {
            return false;
        }
    },

    /** null/undefined -> '' so missing fields render empty instead of throwing. */
    _text(value) {
        if (value === null || value === undefined) return '';
        return String(value);
    },

    /** Key cell text: "<prefix>…" when the row carries a non-empty key
     *  prefix, otherwise "no key issued".  A boolean prefix (false in
     *  particular) is not key material and must never render as the text
     *  "false".  Never throws on odd values. */
    _keyLabel(row) {
        const prefix = row.key_prefix;
        if (typeof prefix === 'boolean' || prefix === null || prefix === undefined) {
            return 'no key issued';
        }
        const text = this._text(prefix).trim();
        return text !== '' ? text + '\u2026' : 'no key issued';
    },

    /** Status cell text: exactly "Revoked" when revoked === true,
     *  "Active" otherwise (false, null, missing or odd values). */
    _statusLabel(row) {
        return row.revoked === true ? 'Revoked' : 'Active';
    },

    /** The `detail` carried by an ApiClient failure result, as a string:
     *  a string is kept as-is, a 422 array of { msg } entries is joined,
     *  a number or boolean is stringified, and a plain object is shown as
     *  its JSON text — no non-string detail value is dropped.  Null when
     *  the body has none (or the value is unusable).  Hostile/odd bodies
     *  never throw. */
    _detail(result) {
        const body = result && result._responseBody;
        if (!body || typeof body !== 'object' || Array.isArray(body)) {
            return null;
        }
        const detail = body.detail;
        if (typeof detail === 'string') {
            return detail.trim() !== '' ? detail : null;
        }
        if (Array.isArray(detail)) {
            const parts = detail
                .map((entry) => (entry && typeof entry.msg === 'string' ? entry.msg : ''))
                .filter((msg) => msg !== '');
            if (parts.length > 0) {
                return parts.join('; ');
            }
            return null;
        }
        if (typeof detail === 'number' || typeof detail === 'boolean') {
            return String(detail);
        }
        if (detail && typeof detail === 'object') {
            try {
                const text = JSON.stringify(detail);
                if (typeof text === 'string' && text !== 'null' && text !== '{}') {
                    return text;
                }
            } catch (e) {
                // unserializable (circular, etc.): nothing to show
            }
        }
        return null;
    },

    /** The table host element, or null when absent. */
    _host() {
        const section = this._section();
        return section ? section.querySelector('[data-testid="feedkeys-table-wrap"]') : null;
    },

    /** The slot that holds the credentials table (re-rendered on every
     *  load), or null when absent. */
    _tableSlot() {
        const host = this._host();
        return host ? host.querySelector('[data-testid="feedkeys-table-slot"]') : null;
    },

    /** The create form, or null when absent. */
    _form() {
        const host = this._host();
        return host ? host.querySelector('[data-testid="feedkeys-new-form"]') : null;
    },

    /** The section-level error line (validation + create/rotate errors),
     *  or null when absent. */
    _errorLine() {
        const host = this._host();
        return host ? host.querySelector('[data-testid="feedkeys-form-error"]') : null;
    },

    /** The slot the reveal box appears in, or null when absent. */
    _revealSlot() {
        const host = this._host();
        return host ? host.querySelector('[data-testid="feedkeys-reveal-slot"]') : null;
    },

    _setError(text) {
        const el = this._errorLine();
        if (!el) return;
        el.textContent = text;
        el.hidden = text === '';
    },

    /**
     * The section's boot-time controls: the "New feed key" button, the
     * error line, the reveal slot and the table slot — appended to the
     * table host, above the table slot.  Built with createElement/
     * textContent.  The create form is deliberately NOT built here (see
     * _buildForm): it must not exist in the boot-time DOM.
     */
    _buildControls(host) {
        const toolbar = document.createElement('div');
        toolbar.setAttribute('data-testid', 'feedkeys-toolbar');
        toolbar.appendChild(this._roleButton('feedkeys-new-btn', 'New feed key', 'btn btn-primary btn-sm', () => {
            this._openForm();
        }, true));
        host.appendChild(toolbar);

        const error = document.createElement('div');
        error.setAttribute('data-testid', 'feedkeys-form-error');
        error.hidden = true;
        host.appendChild(error);

        const slot = document.createElement('div');
        slot.setAttribute('data-testid', 'feedkeys-reveal-slot');
        host.appendChild(slot);

        const tableSlot = document.createElement('div');
        tableSlot.setAttribute('data-testid', 'feedkeys-table-slot');
        host.appendChild(tableSlot);
    },

    /**
     * An accessible button implemented as div[role=button] (see the
     * module header for why this panel cannot use <button> tags in its
     * boot-time DOM): role + tabindex, a click listener, Enter/Space
     * key handling and the studio's .btn styling.  The label is written
     * with textContent, so no markup can be injected through it.
     * adminOnly adds data-requires-role="admin".
     */
    _roleButton(testid, label, className, onClick, adminOnly) {
        const el = document.createElement('div');
        el.setAttribute('role', 'button');
        el.setAttribute('tabindex', '0');
        el.setAttribute('data-testid', testid);
        if (className) {
            el.className = className;
        }
        if (adminOnly) {
            el.setAttribute('data-requires-role', 'admin');
        }
        el.textContent = label;
        el.addEventListener('click', onClick);
        el.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar') {
                event.preventDefault();
                onClick();
            }
        });
        return el;
    },

    /**
     * The create form: a required "Name" and an optional "Principal"
     * text input plus "Save"/"Cancel".  A real <form> with <input>s —
     * built once, lazily, by _openForm(), so it is absent from the
     * boot-time DOM (issue #740's read-only contract).  noValidate is
     * set so the empty-name case is reported by our own "Name is
     * required." line instead of the browser's validation UI.
     */
    _buildForm() {
        const form = document.createElement('form');
        form.setAttribute('data-testid', 'feedkeys-new-form');
        form.noValidate = true;

        const nameLabel = document.createElement('label');
        nameLabel.htmlFor = 'feedkeys-name-input';
        nameLabel.textContent = 'Name';
        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.id = 'feedkeys-name-input';
        nameInput.required = true;
        nameInput.setAttribute('data-testid', 'feedkeys-name-input');

        const principalLabel = document.createElement('label');
        principalLabel.htmlFor = 'feedkeys-principal-input';
        principalLabel.textContent = 'Principal';
        const principalInput = document.createElement('input');
        principalInput.type = 'text';
        principalInput.id = 'feedkeys-principal-input';
        principalInput.setAttribute('data-testid', 'feedkeys-principal-input');

        const save = document.createElement('button');
        save.type = 'submit';
        save.className = 'btn btn-primary btn-sm';
        save.setAttribute('data-testid', 'feedkeys-save');
        save.textContent = 'Save';

        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.className = 'btn btn-secondary btn-sm';
        cancel.setAttribute('data-testid', 'feedkeys-cancel');
        cancel.textContent = 'Cancel';

        form.appendChild(nameLabel);
        form.appendChild(nameInput);
        form.appendChild(principalLabel);
        form.appendChild(principalInput);
        form.appendChild(save);
        form.appendChild(cancel);
        form.addEventListener('submit', (event) => {
            event.preventDefault();
            this._saveNewKey(nameInput, principalInput);
        });
        cancel.addEventListener('click', () => {
            this._closeForm();
        });
        return form;
    },

    /** Show the create form, clear the error line and focus the Name
     *  input.  The form is built on first use (_buildForm) and inserted
     *  below the toolbar. */
    _openForm() {
        let form = this._form();
        if (!form) {
            const host = this._host();
            if (!host) return;
            form = this._buildForm();
            const toolbar = host.querySelector('[data-testid="feedkeys-toolbar"]');
            if (toolbar && toolbar.nextSibling) {
                host.insertBefore(form, toolbar.nextSibling);
            } else {
                host.appendChild(form);
            }
        }
        this._setError('');
        form.hidden = false;
        const nameInput = form.querySelector('[data-testid="feedkeys-name-input"]');
        if (nameInput && typeof nameInput.focus === 'function') {
            try {
                nameInput.focus();
            } catch (e) {
                // focusing is a convenience, not a requirement
            }
        }
    },

    /** Hide the create form, clear its fields and the error line.  Sends
     *  nothing. */
    _closeForm() {
        const form = this._form();
        if (!form) return;
        form.hidden = true;
        form.reset();
        this._setError('');
    },

    /**
     * Save the create form: validate, then POST /feed-credentials and,
     * for the id the create returned, POST /feed-credentials/<id>/rotate.
     * On success the form closes and the one-time key is revealed; on
     * failure the response's detail (or the fallback) is shown and no
     * key is revealed.
     */
    async _saveNewKey(nameInput, principalInput) {
        const name = this._text(nameInput && nameInput.value).trim();
        const principal = this._text(principalInput && principalInput.value).trim();
        if (name === '') {
            this._setError('Name is required.');
            return;
        }
        this._setError('');

        let created;
        try {
            created = await ApiClient.post('/feed-credentials', {
                name,
                principal: principal === '' ? null : principal,
            });
        } catch (e) {
            created = null;
        }
        const newId =
            created && created.ok && created.data && typeof created.data === 'object'
                ? created.data.id
                : null;
        if (newId === null || newId === undefined || this._text(newId).trim() === '') {
            this._setError(this._detail(created) || 'Could not create the feed key.');
            return;
        }

        let rotated;
        try {
            rotated = await ApiClient.post('/feed-credentials/' + encodeURIComponent(newId) + '/rotate');
        } catch (e) {
            rotated = null;
        }
        const key =
            rotated && rotated.ok && rotated.data && typeof rotated.data === 'object'
                ? rotated.data.key
                : null;
        if (typeof key !== 'string' || key === '') {
            this._setError(this._detail(rotated) || 'Could not create the feed key.');
            return;
        }

        this._closeForm();
        this._showReveal(key);
    },

    /**
     * The one-time reveal box: the key written once, as text, next to the
     * note "Copy this key now. It will not be shown again." and a "Done"
     * button.  "Done" removes the box (and the key) from the page and
     * reloads the table.
     */
    _showReveal(key) {
        const slot = this._revealSlot();
        if (!slot) return;
        slot.textContent = '';

        const box = document.createElement('div');
        box.setAttribute('data-testid', 'feedkey-reveal');

        const note = document.createElement('p');
        note.setAttribute('data-testid', 'feedkey-reveal-note');
        note.textContent = 'Copy this key now. It will not be shown again.';

        const value = document.createElement('code');
        value.setAttribute('data-testid', 'feedkey-reveal-key');
        value.textContent = key;

        const done = this._roleButton('feedkey-reveal-done', 'Done', 'btn btn-secondary btn-sm', () => {
            box.remove();
            this._loadTable();
        });

        box.appendChild(note);
        box.appendChild(value);
        box.appendChild(done);
        slot.appendChild(box);
    },

    /** One row's action cell: for every credential that carries a
     *  usable id, a "Delete" button (with data-requires-role="admin");
     *  for every credential that is additionally not revoked, an
     *  "Issue new key" button and a "Revoke" button (both with
     *  data-requires-role="admin"); an empty cell for a row without a
     *  usable id. */
    _renderActionsCell(record) {
        const td = document.createElement('td');
        td.setAttribute('data-testid', 'feedkeys-actions');
        const id = this._text(record.id).trim();
        if (id === '') {
            return td;
        }
        if (record.revoked !== true) {
            td.appendChild(this._roleButton('feedkeys-rotate-btn', 'Issue new key', 'btn btn-secondary btn-sm', () => {
                this._startRotate(td, record);
            }, true));
            td.appendChild(this._roleButton('feedkeys-revoke-btn', 'Revoke', 'btn btn-secondary btn-sm', () => {
                this._startRevoke(td, record);
            }, true));
        }
        td.appendChild(this._roleButton('feedkeys-delete-btn', 'Delete', 'btn btn-danger btn-sm', () => {
            this._startDelete(td, record);
        }, true));
        return td;
    },

    /** Replace the row's action cell with the rotate confirmation: the
     *  warning line plus "Confirm" and "Cancel" buttons.  "Cancel"
     *  restores the "Issue new key" button and sends nothing; "Confirm"
     *  sends POST /feed-credentials/<id>/rotate. */
    _startRotate(cell, record) {
        cell.textContent = '';
        const wrap = document.createElement('span');
        wrap.setAttribute('data-testid', 'feedkeys-rotate-confirm');
        const note = document.createElement('span');
        note.textContent = 'Issuing a new key stops the current key from working.';

        const restore = () => {
            cell.replaceWith(this._renderActionsCell(record));
        };

        const ok = this._roleButton('feedkeys-rotate-confirm-ok', 'Confirm', 'btn btn-primary btn-sm', () => {
            this._confirmRotate(record, restore);
        });

        const cancel = this._roleButton('feedkeys-rotate-confirm-cancel', 'Cancel', 'btn btn-secondary btn-sm', () => {
            this._setError('');
            restore();
        });

        wrap.appendChild(note);
        wrap.appendChild(ok);
        wrap.appendChild(cancel);
        cell.appendChild(wrap);
    },

    /** Confirm a rotate: POST /feed-credentials/<id>/rotate and reveal
     *  the returned key; on failure show the response's detail (or a
     *  fallback) and restore the "Issue new key" button. */
    async _confirmRotate(record, restore) {
        const id = this._text(record.id).trim();
        if (id === '') {
            restore();
            return;
        }
        let res;
        try {
            res = await ApiClient.post('/feed-credentials/' + encodeURIComponent(id) + '/rotate');
        } catch (e) {
            res = null;
        }
        if (
            res &&
            res.ok &&
            res.data &&
            typeof res.data === 'object' &&
            typeof res.data.key === 'string' &&
            res.data.key !== ''
        ) {
            this._setError('');
            this._showReveal(res.data.key);
            restore();
            return;
        }
        this._setError(this._detail(res) || 'Could not issue a new key.');
        restore();
    },

    /** Rebuild the row's action cell in place and return the new
     *  cell.  Restores the row's buttons after a confirmation (or a
     *  failed action) without sending anything. */
    _restoreActions(cell, record) {
        const fresh = this._renderActionsCell(record);
        cell.replaceWith(fresh);
        return fresh;
    },

    /** Show a one-line error inside the row's action cell after a
     *  failed revoke or delete.  Written with textContent (inert); the
     *  row's buttons stay visible so the action can be retried. */
    _rowActionError(td, testid, text) {
        const err = document.createElement('span');
        err.setAttribute('data-testid', testid);
        err.style.color = '#c0392b';
        err.textContent = text;
        td.appendChild(err);
    },

    /** Replace the row's action cell with the revoke confirmation:
     *  "Revoke <name>? Tools using this key will stop working." plus
     *  "Confirm revoke" and "Cancel" buttons.  "Cancel" restores the
     *  row's buttons and sends nothing; "Confirm revoke" sends
     *  PUT /feed-credentials/<id> with only {"revoked": true}. */
    _startRevoke(cell, record) {
        cell.textContent = '';
        const wrap = document.createElement('span');
        wrap.setAttribute('data-testid', 'feedkeys-revoke-confirm');
        const note = document.createElement('span');
        note.setAttribute('data-testid', 'feedkeys-revoke-note');
        note.textContent =
            'Revoke ' + this._text(record.name) + '? Tools using this key will stop working.';

        const ok = this._roleButton('feedkeys-revoke-confirm-ok', 'Confirm revoke', 'btn btn-primary btn-sm', () => {
            this._confirmRevoke(record, cell);
        });

        const cancel = this._roleButton('feedkeys-revoke-confirm-cancel', 'Cancel', 'btn btn-secondary btn-sm', () => {
            this._restoreActions(cell, record);
        });

        wrap.appendChild(note);
        wrap.appendChild(ok);
        wrap.appendChild(cancel);
        cell.appendChild(wrap);
    },

    /** Confirm a revoke: PUT /feed-credentials/<id> with only
     *  {"revoked": true}, then reload the table; on failure show
     *  "Could not revoke the key." in the row and restore the
     *  buttons. */
    async _confirmRevoke(record, cell) {
        const id = this._text(record.id).trim();
        if (id === '') {
            this._restoreActions(cell, record);
            return;
        }
        let res;
        try {
            res = await ApiClient.put('/feed-credentials/' + encodeURIComponent(id), {
                revoked: true,
            });
        } catch (e) {
            res = null;
        }
        if (res && res.ok) {
            this._loadTable();
            return;
        }
        const td = this._restoreActions(cell, record);
        this._rowActionError(td, 'feedkeys-revoke-error', 'Could not revoke the key.');
    },

    /** Replace the row's action cell with the delete confirmation:
     *  "Delete <name>?" plus "Confirm delete" and "Cancel" buttons.
     *  "Cancel" restores the row's buttons and sends nothing;
     *  "Confirm delete" sends DELETE /feed-credentials/<id>. */
    _startDelete(cell, record) {
        cell.textContent = '';
        const wrap = document.createElement('span');
        wrap.setAttribute('data-testid', 'feedkeys-delete-confirm');
        const note = document.createElement('span');
        note.setAttribute('data-testid', 'feedkeys-delete-note');
        note.textContent = 'Delete ' + this._text(record.name) + '?';

        const ok = this._roleButton('feedkeys-delete-confirm-ok', 'Confirm delete', 'btn btn-primary btn-sm', () => {
            this._confirmDelete(record, cell);
        });

        const cancel = this._roleButton('feedkeys-delete-confirm-cancel', 'Cancel', 'btn btn-secondary btn-sm', () => {
            this._restoreActions(cell, record);
        });

        wrap.appendChild(note);
        wrap.appendChild(ok);
        wrap.appendChild(cancel);
        cell.appendChild(wrap);
    },

    /** Confirm a delete: DELETE /feed-credentials/<id>, then reload
     *  the table; on failure show "Could not delete the key." in the
     *  row and restore the buttons. */
    async _confirmDelete(record, cell) {
        const id = this._text(record.id).trim();
        if (id === '') {
            this._restoreActions(cell, record);
            return;
        }
        let res;
        try {
            res = await ApiClient.delete('/feed-credentials/' + encodeURIComponent(id));
        } catch (e) {
            res = null;
        }
        if (res && res.ok) {
            this._loadTable();
            return;
        }
        const td = this._restoreActions(cell, record);
        this._rowActionError(td, 'feedkeys-delete-error', 'Could not delete the key.');
    },

    /** One <tr> per credential.  Reads only id, name, principal,
     *  key_prefix, revoked and created_at and writes every value with
     *  textContent — nothing else from the row is touched. */
    _renderRow(row) {
        const record = row && typeof row === 'object' ? row : {};
        const cells = [
            ['feedkeys-name', this._text(record.name)],
            ['feedkeys-principal', this._text(record.principal)],
            ['feedkeys-key', this._keyLabel(record)],
            ['feedkeys-status', this._statusLabel(record)],
            ['feedkeys-created', this._text(record.created_at)],
        ];
        const tr = document.createElement('tr');
        tr.setAttribute('data-testid', 'feedkeys-row');
        for (let i = 0; i < cells.length; i++) {
            const td = document.createElement('td');
            td.setAttribute('data-testid', cells[i][0]);
            td.textContent = cells[i][1];
            tr.appendChild(td);
        }
        tr.appendChild(this._renderActionsCell(record));
        return tr;
    },

    /** The credentials table: a six-column header plus one row per
     *  credential.  Built entirely with createElement/textContent. */
    _renderTable(rows) {
        const table = document.createElement('table');
        table.className = 'wh-feedkeys-table';
        table.setAttribute('data-testid', 'feedkeys-table');

        const thead = document.createElement('thead');
        const headRow = document.createElement('tr');
        const headers = ['Name', 'Principal', 'Key', 'Status', 'Created', 'Actions'];
        for (let i = 0; i < headers.length; i++) {
            const th = document.createElement('th');
            th.textContent = headers[i];
            headRow.appendChild(th);
        }
        thead.appendChild(headRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        for (let i = 0; i < rows.length; i++) {
            tbody.appendChild(this._renderRow(rows[i]));
        }
        table.appendChild(tbody);
        return table;
    },

    /** Fetch GET /feed-credentials through ApiClient and render the
     *  table into the table slot: one row per credential, "No feed keys
     *  yet." for an empty list, or "Could not load feed keys." when the
     *  request fails. */
    async _loadTable() {
        const slot = this._tableSlot();
        if (!slot) return;

        let res;
        try {
            res = await ApiClient.get('/feed-credentials');
        } catch (e) {
            res = null;
        }

        slot.textContent = '';
        if (res && res.ok && Array.isArray(res.data)) {
            if (res.data.length === 0) {
                const empty = document.createElement('div');
                empty.setAttribute('data-testid', 'feedkeys-empty');
                empty.textContent = 'No feed keys yet.';
                slot.appendChild(empty);
                return;
            }
            slot.appendChild(this._renderTable(res.data));
            return;
        }
        const error = document.createElement('div');
        error.setAttribute('data-testid', 'feedkeys-error');
        error.textContent = 'Could not load feed keys.';
        slot.appendChild(error);
    },

    /**
     * Boot the panel.  Called from studio.html on Studio boot like the
     * other Studio modules.
     *
     * When Auth.isAdmin() is false or throws, the section is removed
     * from the DOM and no request is made.  For an admin, the section's
     * controls (New feed key button, error line, reveal slot — the
     * create form is built on first use) are built once and the
     * credentials table is loaded.
     */
    async init() {
        const section = this._section();
        if (!section) return;
        if (!this._isAdmin()) {
            // The studio renders admin-only controls conditionally: for a
            // non-admin (or a throwing Auth.isAdmin()) the whole section
            // leaves the DOM, so no element carrying
            // data-requires-role="admin" is left behind.
            section.remove();
            return;
        }
        section.hidden = false;

        const host = this._host();
        if (!host) return;
        if (!host.querySelector('[data-testid="feedkeys-toolbar"]')) {
            this._buildControls(host);
        }
        await this._loadTable();
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { FeedKeys };
}
if (typeof window !== 'undefined') {
    window.FeedKeys = FeedKeys;
}

/**
 * Audit history — Studio panel (issue #754).
 *
 * Read-only admin panel over GET /api/audit (limit=100), through the
 * existing ApiClient (never fetch() directly).  For an admin it renders,
 * inside an element marked data-requires-role="admin":
 *   • a block element (data-testid="audit-filter-row") holding a select
 *     that lists "All entity types" plus each distinct entity type in the
 *     loaded events; choosing a type shows only its events and "All
 *     entity types" shows them all again
 *   • after that block, in document order, a table of the events ordered
 *     newest first by timestamp — ISO strings and numeric epoch values
 *     (seconds or milliseconds) compare chronologically
 * with one row per event showing the time, action, entity type, entity
 * id, the actor's username (or actor_sub when there is none) and the
 * details as compact "key: value" pairs.  The time is rendered as a
 * deterministic UTC-formatted string ("YYYY-MM-DD HH:MM:SS UTC"), never
 * as the raw timestamp value.
 *
 * Security contract:
 *   • Every dynamic value is written with textContent (never innerHTML),
 *     so hostile field values render as inert text.
 *   • The actor's email is never read or rendered — only actor_username
 *     (falling back to actor_sub) is shown.
 *   • When the current user is not an admin, the section shows only
 *     "Audit history is available to administrators." and renders no
 *     element marked data-requires-role="admin".  The same fail-closed
 *     note is the section's static default, so a rejected/throwing
 *     Auth.init() (which never reaches this init) leaves the note in
 *     place as well.  In every fail-closed case no request to
 *     /api/audit is made.
 *   • With no events the section shows "No audit events yet."; a failed
 *     request shows "Could not load audit history."
 *   • Nothing in this section changes data: it renders, it does not
 *     write (no forms, no buttons, no mutation endpoints).
 */
'use strict';

const AuditView = {
    /** Fail-closed notice for non-admins and failed auth (AC-1). */
    ADMIN_ONLY_NOTE: 'Audit history is available to administrators.',
    EMPTY_NOTE: 'No audit events yet.',
    ERROR_NOTE: 'Could not load audit history.',
    ALL_TYPES_LABEL: 'All entity types',

    /** The panel section from studio.html, or null when absent. */
    _section() {
        return document.querySelector('[data-panel="audit"]');
    },

    /** True when the current user holds the admin role.  Never throws:
     *  a missing Auth or a throwing Auth.isAdmin() degrades to false,
     *  which keeps the fail-closed note and sends no request. */
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

    /**
     * Normalize a timestamp to milliseconds since the epoch so that ISO
     * strings and numeric epoch values compare chronologically.
     *
     * Numbers below 1e12 in magnitude are epoch seconds (1e12 seconds is
     * the year 33658); larger magnitudes are epoch milliseconds.  Strings
     * are parsed with Date.parse (ISO 8601), with purely numeric strings
     * routed through the same seconds/milliseconds rule.  Unparseable
     * values sort as oldest.
     */
    _timestampMillis(value) {
        const asEpochNumber = (n) => (Math.abs(n) < 1e12 ? n * 1000 : n);
        if (typeof value === 'number' && isFinite(value)) {
            return asEpochNumber(value);
        }
        if (typeof value === 'string') {
            const trimmed = value.trim();
            if (trimmed === '') return -Infinity;
            if (/^[+-]?\d+(\.\d+)?$/.test(trimmed)) {
                const n = Number(trimmed);
                return isFinite(n) ? asEpochNumber(n) : -Infinity;
            }
            const parsed = Date.parse(trimmed);
            return isNaN(parsed) ? -Infinity : parsed;
        }
        return -Infinity;
    },

    /**
     * Display form of a timestamp: deterministic UTC
     * "YYYY-MM-DD HH:MM:SS UTC".  ISO strings and numeric epoch values
     * format to the same human-readable moment; the raw value is never
     * shown.  Unparseable values fall back to the raw text so a hostile
     * timestamp still renders as inert text instead of an error.
     */
    _timeText(value) {
        const millis = this._timestampMillis(value);
        if (!isFinite(millis)) return this._text(value);
        const d = new Date(millis);
        if (isNaN(d.getTime())) return this._text(value);
        const pad = (n) => String(n).padStart(2, '0');
        return (
            d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate()) +
            ' ' + pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()) + ':' + pad(d.getUTCSeconds()) +
            ' UTC'
        );
    },

    /**
     * Return a copy of the events ordered newest first by timestamp,
     * comparing ISO strings and numeric epoch values chronologically.
     * Events with equal or unparseable timestamps keep their original
     * relative order (stable).
     */
    _sortedNewestFirst(events) {
        const list = Array.isArray(events) ? events : [];
        const decorated = [];
        for (let i = 0; i < list.length; i++) {
            const event = list[i] && typeof list[i] === 'object' ? list[i] : {};
            decorated.push({ event, index: i, millis: this._timestampMillis(event.timestamp) });
        }
        decorated.sort((a, b) => {
            if (a.millis !== b.millis) return b.millis - a.millis;
            return a.index - b.index;
        });
        return decorated.map((d) => d.event);
    },

    /** The distinct entity types in first-seen (sorted) order. */
    _distinctEntityTypes(events) {
        const types = [];
        for (let i = 0; i < events.length; i++) {
            const record = events[i] && typeof events[i] === 'object' ? events[i] : {};
            const type = this._text(record.entity_type);
            if (type !== '' && types.indexOf(type) === -1) types.push(type);
        }
        return types;
    },

    /**
     * Actor cell text: the username, or actor_sub when there is no
     * username.  The actor's email is never read or shown.
     */
    _actorLabel(event) {
        const record = event && typeof event === 'object' ? event : {};
        const username = this._text(record.actor_username).trim();
        if (username !== '') return username;
        return this._text(record.actor_sub);
    },

    /** Details as compact "key: value" pairs joined by "; ". */
    _detailsText(event) {
        const details =
            event && typeof event === 'object' && event.details && typeof event.details === 'object'
                ? event.details
                : null;
        if (!details) return '';
        const pairs = [];
        for (const key of Object.keys(details)) {
            const value = details[key];
            let text;
            if (value === null || value === undefined) {
                text = '';
            } else if (typeof value === 'object') {
                try {
                    text = JSON.stringify(value);
                } catch (e) {
                    text = String(value);
                }
            } else {
                text = String(value);
            }
            pairs.push(key + ': ' + text);
        }
        return pairs.join('; ');
    },

    /** One <tr> per event.  Every value is written with textContent. */
    _renderRow(event) {
        const record = event && typeof event === 'object' ? event : {};
        const cells = [
            ['audit-time', this._timeText(record.timestamp)],
            ['audit-action', this._text(record.action)],
            ['audit-entity-type', this._text(record.entity_type)],
            ['audit-entity-id', this._text(record.entity_id)],
            ['audit-actor', this._actorLabel(record)],
            ['audit-details', this._detailsText(record)],
        ];
        const tr = document.createElement('tr');
        tr.setAttribute('data-testid', 'audit-row');
        for (let i = 0; i < cells.length; i++) {
            const td = document.createElement('td');
            td.setAttribute('data-testid', cells[i][0]);
            td.textContent = cells[i][1];
            tr.appendChild(td);
        }
        return tr;
    },

    /** The events table: a six-column header plus one row per event.
     *  Built entirely with createElement/textContent. */
    _renderTable(events) {
        const table = document.createElement('table');
        table.className = 'wh-audit-table';
        table.setAttribute('data-testid', 'audit-table');

        const thead = document.createElement('thead');
        const headRow = document.createElement('tr');
        const headers = ['Time', 'Action', 'Entity type', 'Entity id', 'Actor', 'Details'];
        for (let i = 0; i < headers.length; i++) {
            const th = document.createElement('th');
            th.textContent = headers[i];
            headRow.appendChild(th);
        }
        thead.appendChild(headRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        for (let i = 0; i < events.length; i++) {
            tbody.appendChild(this._renderRow(events[i]));
        }
        table.appendChild(tbody);
        return table;
    },

    /** Refill the table body with the rows matching the selected filter. */
    _applyFilter(tbody, events, selectedType) {
        tbody.textContent = '';
        const visible =
            selectedType === ''
                ? events
                : events.filter((event) => {
                      const record = event && typeof event === 'object' ? event : {};
                      return this._text(record.entity_type) === selectedType;
                  });
        for (let i = 0; i < visible.length; i++) {
            tbody.appendChild(this._renderRow(visible[i]));
        }
    },

    /**
     * The admin content: a data-requires-role="admin" wrapper holding
     * the filter row (block element with the entity-type select) and,
     * after it in document order, the events table.
     */
    _renderAdmin(events) {
        const wrapper = document.createElement('div');
        wrapper.setAttribute('data-requires-role', 'admin');
        wrapper.setAttribute('data-testid', 'audit-admin');

        const filterRow = document.createElement('div');
        filterRow.setAttribute('data-testid', 'audit-filter-row');
        const select = document.createElement('select');
        select.setAttribute('data-testid', 'audit-entity-type-filter');
        const allOption = document.createElement('option');
        allOption.value = '';
        allOption.textContent = this.ALL_TYPES_LABEL;
        select.appendChild(allOption);
        const types = this._distinctEntityTypes(events);
        for (let i = 0; i < types.length; i++) {
            const option = document.createElement('option');
            option.value = types[i];
            option.textContent = types[i];
            select.appendChild(option);
        }
        filterRow.appendChild(select);
        wrapper.appendChild(filterRow);

        const table = this._renderTable(events);
        wrapper.appendChild(table);

        const tbody = table.querySelector('tbody');
        select.addEventListener('change', () => {
            this._applyFilter(tbody, events, select.value);
        });

        return wrapper;
    },

    /** Replace the section body with a single note paragraph. */
    _setNote(host, testId, text) {
        host.textContent = '';
        const note = document.createElement('p');
        note.className = 'audit-note';
        note.setAttribute('data-testid', testId);
        note.textContent = text;
        host.appendChild(note);
    },

    /**
     * Boot the panel.  Called from studio.html on Studio boot after
     * Auth.init(), like the other Studio modules.
     *
     * Non-admin (or a throwing Auth.isAdmin()): the section shows only
     * "Audit history is available to administrators." and renders no
     * element marked data-requires-role="admin"; no request is made.
     * Admin: fetches GET /api/audit?limit=100 through ApiClient and
     * renders the filter row + events table, "No audit events yet." for
     * an empty list, or "Could not load audit history." on failure.
     */
    async init() {
        const section = this._section();
        if (!section) return;
        const host = section.querySelector('[data-testid="audit-body"]');
        if (!host) return;

        if (!this._isAdmin()) {
            this._setNote(host, 'audit-admin-only-note', this.ADMIN_ONLY_NOTE);
            return;
        }

        let res;
        try {
            res = await ApiClient.get('/audit?limit=100');
        } catch (e) {
            res = null;
        }

        if (res && res.ok && Array.isArray(res.data)) {
            if (res.data.length === 0) {
                this._setNote(host, 'audit-empty', this.EMPTY_NOTE);
                return;
            }
            const events = this._sortedNewestFirst(res.data);
            host.textContent = '';
            host.appendChild(this._renderAdmin(events));
            return;
        }

        this._setNote(host, 'audit-error', this.ERROR_NOTE);
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AuditView };
}

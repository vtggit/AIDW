/**
 * Audit history — Studio panel (issue #754, refit by issue #816).
 *
 * Read-only admin panel over GET /api/audit (limit=100), through the
 * existing ApiClient (never fetch() directly).  For an admin it renders,
 * inside an element marked data-requires-role="admin":
 *   • a block element (data-testid="audit-filter-row") holding a select
 *     that lists "All entity types" plus the entity types of the first
 *     load; the chosen type stays a choice while it is shown.  Choosing
 *     a type asks the server for GET /api/audit?entity_type=<type>
 *     &limit=100 (the type URL-encoded) and shows the events that
 *     answer returns, newest first; choosing "All entity types" again
 *     asks for GET /api/audit?limit=100.  A count line in the filter
 *     row reads "1 event" for a single event, "N events" for any other
 *     number below 100, and "Latest 100 events" when the server
 *     returned exactly 100, so a capped list says it is capped.  While
 *     a request is out the select stays usable, and only the newest
 *     choice's answer is shown: an answer for an older choice is
 *     dropped (request-sequence guard — the request counter is never
 *     reset when the panel loads again, and the first load uses it
 *     too, so an answer to a request made before a reload is always
 *     dropped).
 *   • after that block, in document order, the events table inside its
 *     own scroll region (css/audit.css): the header row stays in view at
 *     the top of the region while the rows scroll, and every row is one
 *     line — the Time cell does not wrap and the Details cell is cut
 *     with an ellipsis whose title carries the full details text, up to
 *     2,000 characters
 * of the events ordered newest first by timestamp — ISO strings and
 * numeric epoch values (seconds or milliseconds) compare chronologically
 * — with one row per event showing the time, action, entity type,
 * entity id, the actor's username (or actor_sub when there is none) and
 * the details as compact "key: value" pairs.  The time is rendered as a
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
 *     load shows "Could not load audit history." — for a failed FILTER
 *     request the note takes the table's place in the table's region,
 *     the count line is emptied, and the filter row stays, so another
 *     choice can be made; the next answer refills the count line.
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
    /** The page size every audit request asks for. */
    PAGE_SIZE: 100,
    /** "N events" reads "Latest 100 events" when the server returned
     *  exactly one page, so a capped list says it is capped. */
    CAPPED_COUNT: 'Latest 100 events',
    /** The Details cell's title carries the full details text, up to
     *  this many characters. */
    DETAILS_TITLE_LIMIT: 2000,

    // Panel state, set when the admin content renders:
    _knownTypes: [], // the entity types of the first load (the choices)
    _requestSeq: 0,  // the newest audit request's sequence number
    _select: null,
    _countEl: null,
    _tableWrap: null,
    _host: null,

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
     * The count line's text: "1 event" for a single event, "N events"
     * for any other number below the page size, and "Latest 100
     * events" when the server returned exactly one page, so a capped
     * list says it is capped.
     */
    _countText(events) {
        const count = events.length;
        if (count === this.PAGE_SIZE) return this.CAPPED_COUNT;
        return count + (count === 1 ? ' event' : ' events');
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

    /** One <tr> per event.  Every value is written with textContent.
     *  The Details cell carries the full details text in its title
     *  (up to DETAILS_TITLE_LIMIT characters); the CSS cuts the visible
     *  text with an ellipsis so the row stays one line. */
    _renderRow(event) {
        const record = event && typeof event === 'object' ? event : {};
        const cells = [
            ['audit-time', this._timeText(record.timestamp)],
            ['audit-action', this._text(record.action)],
            ['audit-entity-type', this._text(record.entity_type)],
            ['audit-entity-id', this._text(record.entity_id)],
            ['audit-actor', this._actorLabel(record)],
        ];
        const tr = document.createElement('tr');
        tr.setAttribute('data-testid', 'audit-row');
        for (let i = 0; i < cells.length; i++) {
            const td = document.createElement('td');
            td.setAttribute('data-testid', cells[i][0]);
            td.textContent = cells[i][1];
            tr.appendChild(td);
        }
        const detailsText = this._detailsText(record);
        const detailsTd = document.createElement('td');
        detailsTd.setAttribute('data-testid', 'audit-details');
        detailsTd.textContent = detailsText;
        detailsTd.title = detailsText.slice(0, this.DETAILS_TITLE_LIMIT);
        tr.appendChild(detailsTd);
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

    /** Rebuild the select's options: "All entity types" plus the
     *  first load's types; the chosen type stays a choice while it is
     *  shown. */
    _rebuildChoices(types, selected) {
        const select = this._select;
        select.textContent = '';
        const allOption = document.createElement('option');
        allOption.value = '';
        allOption.textContent = this.ALL_TYPES_LABEL;
        select.appendChild(allOption);
        for (let i = 0; i < types.length; i++) {
            const option = document.createElement('option');
            option.value = types[i];
            option.textContent = types[i];
            select.appendChild(option);
        }
        if (selected !== '' && types.indexOf(selected) === -1) {
            const option = document.createElement('option');
            option.value = selected;
            option.textContent = selected;
            select.appendChild(option);
        }
        select.value = selected;
    },

    /** Show one answer: the table (re)renders the events newest first,
     *  the count line reads what is shown, and the select keeps its
     *  choices with the answer's choice selected. */
    _showEvents(selected, events) {
        this._rebuildChoices(this._knownTypes, selected);
        this._countEl.textContent = this._countText(events);
        this._tableWrap.textContent = '';
        this._tableWrap.appendChild(this._renderTable(events));
    },

    /** The load-failure note in place of the table, inside the table's
     *  region — the filter row above it stays (with the count line
     *  emptied, so the count says nothing while no events are shown),
     *  so another choice can be made; the next answer refills the
     *  count line. */
    _showLoadErrorInTableRegion() {
        this._countEl.textContent = '';
        this._tableWrap.textContent = '';
        const note = document.createElement('p');
        note.className = 'audit-note';
        note.setAttribute('data-testid', 'audit-error');
        note.textContent = this.ERROR_NOTE;
        this._tableWrap.appendChild(note);
    },

    /**
     * Ask the server for the audit events of one choice.
     *
     * `selected` is '' for "All entity types" (GET /api/audit?limit=100)
     * or a type, URL-encoded, for GET /api/audit?entity_type=<type>
     * &limit=100.  A request-sequence guard drops an answer that is no
     * longer the newest choice's: while a request is out the select
     * stays usable, and an older choice's late answer never renders.
     */
    async _loadEvents(selected) {
        const seq = ++this._requestSeq;
        const query =
            selected === ''
                ? '/audit?limit=100'
                : '/audit?entity_type=' + encodeURIComponent(selected) + '&limit=100';
        let res;
        try {
            res = await ApiClient.get(query);
        } catch (e) {
            res = null;
        }
        if (seq !== this._requestSeq) return; // an older choice's answer
        if (res && res.ok && Array.isArray(res.data)) {
            this._showEvents(selected, this._sortedNewestFirst(res.data));
            return;
        }
        this._showLoadErrorInTableRegion();
    },

    /**
     * The admin content: a data-requires-role="admin" wrapper holding
     * the filter row (block element with the entity-type select and the
     * count line) and, after it in document order, the events table in
     * its own scroll region.
     */
    _renderAdmin(events, types) {
        const wrapper = document.createElement('div');
        wrapper.className = 'audit-admin';
        wrapper.setAttribute('data-requires-role', 'admin');
        wrapper.setAttribute('data-testid', 'audit-admin');

        const filterRow = document.createElement('div');
        filterRow.className = 'audit-filter-row';
        filterRow.setAttribute('data-testid', 'audit-filter-row');
        const select = document.createElement('select');
        select.className = 'audit-entity-filter';
        select.setAttribute('data-testid', 'audit-entity-type-filter');
        const count = document.createElement('div');
        count.className = 'audit-count';
        count.setAttribute('data-testid', 'audit-count');
        count.textContent = this._countText(events);
        filterRow.appendChild(select);
        filterRow.appendChild(count);
        wrapper.appendChild(filterRow);

        const tableWrap = document.createElement('div');
        tableWrap.className = 'audit-table-wrap';
        tableWrap.setAttribute('data-testid', 'audit-table-wrap');
        tableWrap.appendChild(this._renderTable(events));
        wrapper.appendChild(tableWrap);

        this._select = select;
        this._countEl = count;
        this._tableWrap = tableWrap;
        this._rebuildChoices(types, '');
        select.addEventListener('change', () => this._loadEvents(select.value));

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
        this._host = host;

        if (!this._isAdmin()) {
            this._setNote(host, 'audit-admin-only-note', this.ADMIN_ONLY_NOTE);
            return;
        }

        // The first load goes through the request counter like every
        // other request, and the counter is never reset when the panel
        // loads again: a late answer to an older first load — or to a
        // choice made before the reload — is dropped instead of
        // overwriting a newer choice's.
        const seq = ++this._requestSeq;
        let res;
        try {
            res = await ApiClient.get('/audit?limit=100');
        } catch (e) {
            res = null;
        }
        if (seq !== this._requestSeq) return; // the panel was reloaded

        if (res && res.ok && Array.isArray(res.data)) {
            if (res.data.length === 0) {
                this._setNote(host, 'audit-empty', this.EMPTY_NOTE);
                return;
            }
            const events = this._sortedNewestFirst(res.data);
            this._knownTypes = this._distinctEntityTypes(events);
            host.textContent = '';
            host.appendChild(this._renderAdmin(events, this._knownTypes));
            return;
        }

        this._setNote(host, 'audit-error', this.ERROR_NOTE);
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AuditView };
}

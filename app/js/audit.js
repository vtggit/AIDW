/**
 * Audit history — Studio panel (issue #694).
 *
 * Read-only admin panel over GET /api/audit?limit=100, through the
 * existing ApiClient (never fetch() directly).  For an admin it shows a
 * table of the events, newest timestamp first, with one row per event:
 * the time, the action, the entity type, the entity id, the actor
 * (the actor's username — or the actor's actor_sub when there is no
 * username) and the details as compact "key: value" pairs.  The entity
 * type <select> above the table ("All entity types" plus each distinct
 * entity type in the loaded events) filters the already-loaded events
 * client-side; nothing in the section changes data (it renders, it does
 * not write — no forms, no buttons, no mutation endpoints).
 *
 * Security contract:
 *   • Only actor_username and actor_sub are read from each event; the
 *     actor's email is never rendered, stored or otherwise reaches the
 *     page.
 *   • Every dynamic value is written with textContent (never innerHTML),
 *     so hostile audit payloads render as inert text.
 *   • Fails closed: when the authentication state is unavailable (Auth
 *     missing or throwing, no authenticated user) or the current user is
 *     not an admin, the admin area is removed from the DOM (no element
 *     carrying data-requires-role="admin" survives), the section shows
 *     only "Audit history is available to administrators." and no
 *     request to /api/audit is made.
 */
'use strict';

const AuditView = {
    /** The API path init() reads (AC-1): the 100 most recent events. */
    API_PATH: '/audit?limit=100',

    /** The section element from studio.html, or null when absent. */
    _section() {
        return document.querySelector('[data-panel="audit"]');
    },

    /** The admin-only area inside the section, or null when absent. */
    _adminArea(section) {
        return section ? section.querySelector('[data-requires-role="admin"]') : null;
    },

    /** True only when the current user holds the admin role.  Never
     *  throws: a missing Auth or a throwing Auth.isAdmin() degrades to
     *  false, which fails the panel closed and sends no request. */
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

    /** null/undefined -> '' so missing fields render empty instead of
     *  throwing. */
    _text(value) {
        if (value === null || value === undefined) return '';
        return String(value);
    },

    /** Actor cell text: the username, or the actor_sub when there is no
     *  username (AC-1).  The actor's email is never read. */
    _actorLabel(event) {
        const username = this._text(event.actor_username).trim();
        return username !== '' ? username : this._text(event.actor_sub);
    },

    /** Details cell text: compact "key: value" pairs joined by ", ".
     *  Strings render verbatim, null renders as "null", numbers/booleans
     *  as their plain text and anything else as JSON.  A hostile or
     *  malformed shape (non-object, array, missing) renders as ''. */
    _detailsLabel(details) {
        if (!details || typeof details !== 'object' || Array.isArray(details)) return '';
        const parts = [];
        for (const key of Object.keys(details)) {
            const value = details[key];
            let rendered;
            if (value === null || value === undefined) {
                rendered = 'null';
            } else if (typeof value === 'string') {
                rendered = value;
            } else if (typeof value === 'object') {
                try {
                    rendered = JSON.stringify(value);
                } catch (e) {
                    rendered = String(value);
                }
            } else {
                rendered = String(value);
            }
            parts.push(this._text(key) + ': ' + rendered);
        }
        return parts.join(', ');
    },

    /** Events sorted newest timestamp first (AC-1).  ISO-8601 strings
     *  compare chronologically; unparseable timestamps sink to the end
     *  in their original (stable) order. */
    _newestFirst(events) {
        const key = (event) => {
            const parsed = Date.parse(this._text(event && event.timestamp));
            return Number.isFinite(parsed) ? parsed : 0;
        };
        return events.slice().sort((a, b) => key(b) - key(a));
    },

    /** The distinct entity types, in first-seen (newest-first) order. */
    _entityTypes(events) {
        const types = [];
        for (const event of events) {
            const type = this._text(event && event.entity_type);
            if (type !== '' && types.indexOf(type) === -1) types.push(type);
        }
        return types;
    },

    /** One <tr> per event.  Every cell is written with textContent, so
     *  crafted field values (markup included) render as inert text
     *  (AC-4). */
    _renderRow(event) {
        const record = event && typeof event === 'object' ? event : {};
        const cells = [
            ['audit-time', this._text(record.timestamp)],
            ['audit-action', this._text(record.action)],
            ['audit-entity-type', this._text(record.entity_type)],
            ['audit-entity-id', this._text(record.entity_id)],
            ['audit-actor', this._actorLabel(record)],
            ['audit-details', this._detailsLabel(record.details)],
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
    _buildTable(events) {
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

    /** The loaded events matching the current select value (AC-2
     *  client-side filter; '' = all). */
    _visibleEvents() {
        const section = this._section();
        const select = section
            ? section.querySelector('[data-testid="audit-entity-type-filter"]')
            : null;
        const selected = select && select.value ? select.value : '';
        const all = this._events || [];
        if (selected === '') return all;
        return all.filter((event) => this._text(event && event.entity_type) === selected);
    },

    /** Render the filtered events into the content host — the table, or
     *  the empty note when there are no events. */
    _render() {
        const section = this._section();
        const host = section ? section.querySelector('[data-testid="audit-content"]') : null;
        if (!host) return;
        const events = this._visibleEvents();
        host.textContent = '';
        if (events.length === 0) {
            const empty = document.createElement('div');
            empty.setAttribute('data-testid', 'audit-empty');
            empty.textContent = 'No audit events yet.';
            host.appendChild(empty);
            return;
        }
        host.appendChild(this._buildTable(events));
    },

    /**
     * Boot the panel.  Called from studio.html on Studio boot (after
     * Auth.init()) like the other Studio modules.
     *
     * Fails closed (AC-5): when the authentication state is unavailable
     * or the current user is not an admin, the admin area is removed
     * from the DOM and the section shows only "Audit history is
     * available to administrators." — no request is made and nothing is
     * rendered.
     *
     * For an admin, fetches GET /api/audit?limit=100 through ApiClient
     * and renders the events newest-first with the entity-type filter
     * (AC-1, AC-2); "No audit events yet." for an empty list and
     * "Could not load audit history." when the request fails.
     */
    async init() {
        const section = this._section();
        if (!section) return;

        const adminArea = this._adminArea(section);

        if (!this._isAdmin()) {
            // The studio's pattern for admin-only controls: the admin
            // area leaves the DOM entirely, so no element carrying
            // data-requires-role="admin" survives for a non-admin.
            if (adminArea) adminArea.remove();
            const head = section.querySelector('.wh-panel-head');
            if (head) head.hidden = true;
            const notice = document.createElement('p');
            notice.className = 'audit-notice';
            notice.setAttribute('data-testid', 'audit-notice');
            notice.textContent = 'Audit history is available to administrators.';
            section.appendChild(notice);
            return;
        }

        section.hidden = false;
        if (!adminArea) return;

        const select = adminArea.querySelector('[data-testid="audit-entity-type-filter"]');
        const host = adminArea.querySelector('[data-testid="audit-content"]');
        if (!host) return;

        let res;
        try {
            res = await ApiClient.get(this.API_PATH);
        } catch (e) {
            res = null;
        }

        if (!res || !res.ok || !Array.isArray(res.data)) {
            host.textContent = '';
            const error = document.createElement('div');
            error.setAttribute('data-testid', 'audit-error');
            error.textContent = 'Could not load audit history.';
            host.appendChild(error);
            return;
        }

        this._events = this._newestFirst(res.data);

        if (select) {
            select.textContent = '';
            const options = ['All entity types'].concat(this._entityTypes(this._events));
            for (let i = 0; i < options.length; i++) {
                const option = document.createElement('option');
                option.value = i === 0 ? '' : options[i];
                option.textContent = options[i];
                select.appendChild(option);
            }
            select.addEventListener('change', () => this._render());
        }

        this._render();
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AuditView };
}
if (typeof window !== 'undefined') {
    window.AuditView = AuditView;
}

/**
 * Feed keys — Studio panel (issue #740).
 *
 * Read-only admin panel over GET /api/feed-credentials, through the
 * existing ApiClient (never fetch() directly).  When the current user is
 * an admin it shows, above the table:
 *   • the feed address /api/feed/v4
 *   • the note "Excel and BI tools read the feed with a key sent as the
 *     X-Api-Key header."
 * and one table row per credential with exactly five fields: name,
 * principal, key prefix (rendered as "<prefix>…" — or "no key issued"
 * when the row has no prefix), status ("Revoked" or "Active") and the
 * created time.
 *
 * Security contract:
 *   • Only those five fields (name, principal, key_prefix, revoked,
 *     created_at) are read from each row; no other field of the response
 *     (key_hash included) is ever rendered, stored or otherwise reaches
 *     the page.
 *   • Every dynamic value is written with textContent (never innerHTML),
 *     so hostile field values render as inert text.
 *   • When Auth.isAdmin() is false or throws, the section is removed
 *     from the DOM (the studio's pattern for admin-only controls, so
 *     no element carrying data-requires-role="admin" survives for a
 *     non-admin) and no request is made.
 *   • Nothing in this section changes data: it renders, it does not
 *     write (no forms, no buttons, no mutation endpoints).
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
     *  prefix, otherwise "no key issued".  Never throws on odd values. */
    _keyLabel(row) {
        const prefix = this._text(row.key_prefix).trim();
        return prefix !== '' ? prefix + '\u2026' : 'no key issued';
    },

    /** Status cell text: exactly "Revoked" when revoked === true,
     *  "Active" otherwise (false, null, missing or odd values). */
    _statusLabel(row) {
        return row.revoked === true ? 'Revoked' : 'Active';
    },

    /** One <tr> per credential.  Reads exactly five fields (name,
     *  principal, key_prefix, revoked, created_at) and writes every
     *  value with textContent — nothing else from the row is touched. */
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
        return tr;
    },

    /** The credentials table: a five-column header plus one row per
     *  credential.  Built entirely with createElement/textContent. */
    _renderTable(rows) {
        const table = document.createElement('table');
        table.className = 'wh-feedkeys-table';
        table.setAttribute('data-testid', 'feedkeys-table');

        const thead = document.createElement('thead');
        const headRow = document.createElement('tr');
        const headers = ['Name', 'Principal', 'Key', 'Status', 'Created'];
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

    /**
     * Boot the panel.  Called from studio.html on Studio boot like the
     * other Studio modules.
     *
     * When Auth.isAdmin() is false or throws, the section is removed
     * from the DOM and no request is made.  For an admin, fetches
     * GET /api/feed-credentials through ApiClient and renders the
     * credentials table, "No feed keys yet." for an empty list, or
     * "Could not load feed keys." when the request fails.
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

        const host = section.querySelector('[data-testid="feedkeys-table-wrap"]');
        if (!host) return;

        let res;
        try {
            res = await ApiClient.get('/feed-credentials');
        } catch (e) {
            res = null;
        }

        host.textContent = '';
        if (res && res.ok && Array.isArray(res.data)) {
            if (res.data.length === 0) {
                const empty = document.createElement('div');
                empty.setAttribute('data-testid', 'feedkeys-empty');
                empty.textContent = 'No feed keys yet.';
                host.appendChild(empty);
                return;
            }
            host.appendChild(this._renderTable(res.data));
            return;
        }
        const error = document.createElement('div');
        error.setAttribute('data-testid', 'feedkeys-error');
        error.textContent = 'Could not load feed keys.';
        host.appendChild(error);
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { FeedKeys };
}
if (typeof window !== 'undefined') {
    window.FeedKeys = FeedKeys;
}

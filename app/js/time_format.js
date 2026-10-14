/**
 * TimeFormat — shared, never-throwing timestamp helpers for the Studio
 * run lists (Load sequences run history, Ingestion pipeline runs and
 * Data retention sweep runs).
 *
 * The server sends run timestamps in two shapes — the Postgres text
 * form ("2026-10-13 07:30:17.18781+00") and ISO 8601
 * ("2026-10-13T07:30:39.930242+00:00") — plus occasional naive
 * (no time zone), numeric and Date values.  The helpers:
 *
 *   TimeFormat.stamp(value)   the value's date, hours and minutes in
 *                             UTC — "2026-10-13 07:30 UTC".  A value
 *                             that cannot be read is returned
 *                             unchanged as text; null or an empty value
 *                             renders an em dash.
 *   TimeFormat.span(start,end) the time between two timestamps in the
 *                             two largest units — "22 s", "8 min 1 s",
 *                             "3 h 12 min", "8 d 4 h" — the unit next
 *                             below the largest stays even when it is
 *                             zero ("8 d 0 h", "3 h 0 min").  An empty
 *                             string when either value is missing or
 *                             unreadable, or when the end is before
 *                             the start.
 *   TimeFormat.age(start,now) the same form for the time from start to
 *                             now.
 *
 * Every function is total: any input (empty, huge, non-numeric, control
 * characters, NUL bytes) yields a string and never throws.
 */
'use strict';

const TimeFormat = (function () {
    const EM_DASH = '\u2014';

    // The only string shape this reader accepts: a calendar date plus
    // an optional time (seconds and a decimal fraction optional) and
    // an optional zone designator ("Z"/"z", "+00", "+00:00", "+0530").
    // The shape is checked strictly and the Date is built from the
    // captured parts, so a lenient engine date parser never sees a
    // hostile string — anything off-shape is unreadable.
    const ISO_SHAPE =
        /^(\d{4})-(\d{2})-(\d{2})(?:[ Tt](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?([Zz]|[+-]\d{2}(?::?\d{2})?)?)?$/;

    const MS_PER_DAY = 86400000;

    /**
     * Proleptic Gregorian days from 1970-01-01 to the civil date
     * (Hinnant's days_from_civil).  Exact for every year, so the
     * Date.UTC two-digit-year quirk (0000–0099 read as
     * 1900–1999) never applies.
     */
    function daysFromCivil(year, month, day) {
        const y = month <= 2 ? year - 1 : year;
        const era = Math.floor(y / 400);
        const yearOfEra = y - era * 400; // [0, 399]
        const dayOfYear =
            Math.floor((153 * (month + (month > 2 ? -3 : 9)) + 2) / 5) + day - 1;
        const dayOfEra =
            yearOfEra * 365 + Math.floor(yearOfEra / 4) - Math.floor(yearOfEra / 100) + dayOfYear;
        return era * 146097 + dayOfEra - 719468;
    }

    /**
     * Parse a timestamp value into a Date, or null when the value is
     * missing or unreadable.  Strings must match the strict shape
     * above (the two forms the server send, plus naive values read as
     * UTC and a bare date read as midnight UTC); finite numbers are
     * epoch seconds (a magnitude of 1e11 or more epoch milliseconds)
     * and Date objects are passed through.  Never throws.
     */
    function parse(value) {
        try {
            if (value === null || value === undefined) return null;
            if (value instanceof Date) {
                return Number.isNaN(value.getTime()) ? null : value;
            }
            if (typeof value === 'number') {
                if (!Number.isFinite(value)) return null;
                const ms = Math.abs(value) >= 1e11 ? value : value * 1000;
                const date = new Date(ms);
                return Number.isNaN(date.getTime()) ? null : date;
            }
            if (typeof value !== 'string') return null;
            const match = value.trim().match(ISO_SHAPE);
            if (match === null) return null;
            const year = Number(match[1]);
            const month = Number(match[2]);
            const day = Number(match[3]);
            const hasTime = match[4] !== undefined;
            const hours = hasTime ? Number(match[4]) : 0;
            const minutes = hasTime ? Number(match[5]) : 0;
            const seconds = hasTime && match[6] !== undefined ? Number(match[6]) : 0;
            const fraction = match[7] !== undefined ? match[7] : '';
            const millis = fraction === '' ? 0 : Number(fraction.slice(0, 3).padEnd(3, '0'));
            if (
                month < 1 || month > 12 || day < 1 || day > 31 ||
                hours > 23 || minutes > 59 || seconds > 59
            ) return null;
            let offsetMinutes = 0;
            const zone = hasTime ? match[8] : undefined;
            if (zone !== undefined && zone !== 'Z' && zone !== 'z') {
                const sign = zone.charAt(0) === '-' ? -1 : 1;
                offsetMinutes = sign * Number(zone.slice(1, 3)) * 60;
                if (zone.length > 3) {
                    offsetMinutes += sign * Number(zone.slice(-2));
                }
            }
            // The instant is built from the exact proleptic Gregorian
            // date, so the Date.UTC two-digit-year quirk never applies.
            // The zone is applied only after the local date itself is
            // validated (a day that rolls into the next month, e.g.
            // February 31, is not a real date: unreadable), so a valid
            // timestamp whose UTC date differs from its local date — an
            // offset crossing midnight — is read correctly.
            const localMs =
                daysFromCivil(year, month, day) * MS_PER_DAY +
                hours * 3600000 + minutes * 60000 + seconds * 1000 + millis;
            const localDate = new Date(localMs);
            if (
                localDate.getUTCFullYear() !== year ||
                localDate.getUTCMonth() !== month - 1 ||
                localDate.getUTCDate() !== day
            ) return null;
            return new Date(localMs - offsetMinutes * 60000);
        } catch (_err) {
            return null;
        }
    }

    function pad2(n) {
        return (n < 10 ? '0' : '') + n;
    }

    /**
     * The "returned unchanged as text" form of a value: strings pass
     * through, everything else is String()ed — and a value whose own
     * conversion throws (Object.create(null), a throwing toString)
     * falls back to the neutral object tag.  Never throws.
     */
    function toText(value) {
        try {
            return String(value);
        } catch (_err) {
            return Object.prototype.toString.call(value);
        }
    }

    /**
     * "2026-10-13 07:30 UTC" — the value's date, hours and minutes in
     * UTC.  A value that cannot be read is returned unchanged as text;
     * null or an empty value renders an em dash.  Never throws.
     */
    function stamp(value) {
        if (value === null || value === undefined) return EM_DASH;
        if (typeof value === 'string' && value.trim() === '') return EM_DASH;
        const date = parse(value);
        if (date === null) {
            return toText(value);
        }
        const year = date.getUTCFullYear();
        const yearText = year < 0 || year > 9999 ? String(year) : String(year).padStart(4, '0');
        return (
            yearText +
            '-' + pad2(date.getUTCMonth() + 1) +
            '-' + pad2(date.getUTCDate()) +
            ' ' + pad2(date.getUTCHours()) +
            ':' + pad2(date.getUTCMinutes()) +
            ' UTC'
        );
    }

    /**
     * The time between two timestamps in the two largest units:
     * "22 s", "8 min 1 s", "3 h 12 min", "8 d 4 h".  The unit next
     * below the largest is always shown, even when it is zero —
     * "8 d 0 h", "3 h 0 min", "8 min 0 s".  An empty string when
     * either value is missing or unreadable, or when the end is
     * before the start.  Never throws.
     */
    function span(start, end) {
        const startDate = parse(start);
        const endDate = parse(end);
        if (startDate === null || endDate === null) return '';
        const seconds = Math.floor((endDate.getTime() - startDate.getTime()) / 1000);
        if (seconds < 0) return '';
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        // The largest non-zero unit plus the unit next below it.  The
        // second unit is kept even when it is zero, so a span of
        // 3 h 0 min 45 s reads "3 h 0 min" and never "3 h 45 s".
        if (days > 0) {
            return days + ' d ' + hours + ' h';
        }
        if (hours > 0) {
            return hours + ' h ' + minutes + ' min';
        }
        if (minutes > 0) {
            return minutes + ' min ' + secs + ' s';
        }
        return secs + ' s';
    }

    /** The same form as span(), for the time from start to now. */
    function age(start, now) {
        return span(start, now);
    }

    return { parse, stamp, span, age };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { TimeFormat };
}
if (typeof window !== 'undefined') {
    window.TimeFormat = TimeFormat;
}

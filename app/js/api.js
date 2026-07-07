/**
 * API Client — Centralized HTTP client and contract boundary.
 *
 * This is the single place where the frontend talks to the backend.
 * All domain data-source files consume API methods from here;
 * they should not call fetch() directly or reinvent response parsing.
 *
 * Contract rules:
 *   • Success responses:  { ok: true, data: <parsed JSON> }
 *   • Failure responses:  { ok: false, error: <ApiError>, status: <number> }
 *   • Auth header injection is automatic via Auth.getAuthorizationHeader()
 *   • 401/403 are classified as auth errors for consistent UI handling
 *   • List endpoints are expected to return arrays
 *   • Detail/mutation endpoints are expected to return objects with an id
 *
 * When the backend contract changes:
 *   1. Update the OpenAPI artifact (backend/openapi.json)
 *   2. Update response-shape expectations here if needed
 *   3. Verify domain data-source files still parse correctly
 */

/**
 * ApiError — Normalized error class for all API failures.
 *
 * Every API error flows through this class so the rest of the app
 * can inspect status, type, and message consistently.
 */
class ApiError extends Error {
    /**
     * @param {string} message - Human-readable error message
     * @param {object} options - Additional context
     * @param {number} [options.status] - HTTP status code
     * @param {'auth'|'validation'|'network'|'server'} [options.type] - Error category
     * @param {object} [options.responseBody] - Raw response body (if available)
     * @param {string} [options.path] - Request path that failed
     */
    constructor(message, options = {}) {
        super(message);
        this.name = 'ApiError';
        this.status = options.status || 0;
        this.type = options.type || 'server';
        this.responseBody = options.responseBody || null;
        this.path = options.path || null;
    }

    /**
     * Factory: create an ApiError from an ApiClient failure result.
     * @param {{ error: string, status: number }} result
     * @returns {ApiError}
     */
    static fromResult(result) {
        const err = new ApiError(result.error || 'An unexpected error occurred.', {
            status: result.status || 0,
            type: result._errorType || 'server',
            responseBody: result._responseBody || null,
            path: result._path || null,
        });
        return err;
    }
}

const ApiClient = {
    BASE_URL: Config.API_BASE_URL,

    // -----------------------------------------------------------------------
    // Request execution
    // -----------------------------------------------------------------------

    /**
     * Build common headers, including Authorization when available.
     */
    _headers(extra = {}) {
        const headers = { 'Content-Type': 'application/json', ...extra };
        const authHeader = Auth.getAuthorizationHeader();
        if (authHeader) {
            headers['Authorization'] = authHeader;
        }
        return headers;
    },

    /**
     * Execute an HTTP request and return a normalized result.
     *
     * Returns { ok: true, data } on success or
     *         { ok: false, error, status, _errorType, _responseBody, _path } on failure.
     *
     * This is the single place where fetch(), JSON parsing, and error
     * normalization happen.  Domain-specific methods should call the
     * generic helpers (get/post/put/delete) and never touch fetch() directly.
     */
    async _execute(method, path, body) {
        const url = this.BASE_URL + path;
        try {
            const opts = { method, headers: this._headers() };
            if (body !== undefined && body !== null) {
                opts.body = JSON.stringify(body);
            }

            const response = await fetch(url, opts);

            if (response.ok) {
                if (response.status === 204) {
                    return { ok: true, data: null };
                }
                return { ok: true, data: await response.json() };
            }

            // Non-OK response — extract error details
            const { message, errorType, responseBody } =
                await this._parseErrorResponse(response);

            return {
                ok: false,
                error: message,
                status: response.status,
                _errorType: errorType,
                _responseBody: responseBody,
                _path: path,
            };
        } catch (e) {
            console.warn(`API ${method} ${path} failed:`, e.message);
            return {
                ok: false,
                error: `Network error: ${e.message}`,
                _errorType: 'network',
                _path: path,
            };
        }
    },

    /**
     * Generic GET helper.
     */
    async get(path) {
        return this._execute('GET', path);
    },

    /**
     * Paged GET: fetch a list endpoint in capped chunks (limit=100, offset
     * paging) until every row is retrieved. The backend enforces a default
     * page size, so an unpaged GET would silently truncate long lists.
     */
    async getAllPages(path) {
        const sep = path.includes('?') ? '&' : '?';
        const all = [];
        for (let offset = 0; ; offset += 100) {
            const page = await this.get(`${path}${sep}limit=100&offset=${offset}`);
            const rows = this.assertList(page);
            all.push(...rows);
            if (rows.length < 100) { break; }
        }
        return all;
    },

    /**
     * Generic POST helper.
     */
    async post(path, body) {
        return this._execute('POST', path, body);
    },

    /**
     * Generic PUT helper.
     */
    async put(path, body) {
        return this._execute('PUT', path, body);
    },

    /**
     * Generic PATCH helper.
     */
    async patch(path, body) {
        return this._execute('PATCH', path, body);
    },

    /**
     * Generic DELETE helper.
     */
    async delete(path) {
        return this._execute('DELETE', path);
    },

    // -----------------------------------------------------------------------
    // Error parsing and classification
    // -----------------------------------------------------------------------

    /**
     * Parse an HTTP error response into a structured error.
     *
     * Classifies errors into types for consistent frontend handling:
     *   - 'auth'       → 401 Unauthorized or 403 Forbidden
     *   - 'validation' → 422 Unprocessable Entity (FastAPI validation)
     *   - 'server'     → 5xx or other non-OK responses
     *
     * @returns {{ message: string, errorType: string, responseBody: object|null }}
     */
    async _parseErrorResponse(response) {
        let responseBody = null;
        try {
            responseBody = await response.json();
        } catch {
            // Response body wasn't JSON — use fallback
        }

        // Classify by status code
        let errorType;
        if (response.status === 401) {
            errorType = 'auth';
        } else if (response.status === 403) {
            errorType = 'auth';
        } else if (response.status === 422) {
            errorType = 'validation';
        } else if (response.status >= 500) {
            errorType = 'server';
        } else {
            errorType = 'server';
        }

        // Extract human-readable message
        let message;
        if (responseBody) {
            if (responseBody.detail) {
                if (Array.isArray(responseBody.detail)) {
                    message = responseBody.detail.map(d => d.msg).join('; ');
                } else {
                    message = responseBody.detail;
                }
            } else if (responseBody.message) {
                message = responseBody.message;
            }
        }
        if (!message) {
            message = `Server error (${response.status})`;
        }

        return { message, errorType, responseBody };
    },

    /**
     * Health check – returns true when the backend is reachable.
     * Uses the shallow /api/health endpoint (no dependency checks).
     */
    async isHealthy() {
        const result = await this.get('/health');
        return result.ok && result.data && result.data.status === 'ok';
    },

    /**
     * Readiness check – returns true when the backend and all dependencies are healthy.
     * Uses the /api/health/ready endpoint which tests database connectivity.
     * Returns the full readiness response for diagnostics.
     */
    async isReady() {
        const result = await this.get('/health/ready');
        if (!result.ok) {
            return { ready: false, reason: result.error || 'Backend unreachable' };
        }
        return {
            ready: result.data.status === 'ok',
            status: result.data.status,
            dependencies: result.data.dependencies || [],
        };
    },

    // -----------------------------------------------------------------------
    // Response-shape validators
    //
    // Lightweight runtime guards that make frontend contract assumptions
    // explicit.  When the backend response shape drifts, these fail fast
    // with a clear error instead of producing confusing UI bugs.
    // -----------------------------------------------------------------------

    /**
     * Assert that a result contains a valid list (array) response.
     * @param {{ ok: boolean, data: any }} result
     * @returns {any[]}
     */
    assertList(result) {
        if (!result.ok) {
            throw ApiError.fromResult(result);
        }
        if (!Array.isArray(result.data)) {
            throw new ApiError(
                `Expected array response but got ${typeof result.data}. Contract drift detected.`,
                { type: 'server' }
            );
        }
        return result.data;
    },

    /**
     * Assert that a result contains a valid entity (object with id) response.
     * @param {{ ok: boolean, data: any }} result
     * @returns {object}
     */
    assertEntity(result) {
        if (!result.ok) {
            throw ApiError.fromResult(result);
        }
        if (!result.data || typeof result.data !== 'object' || !result.data.id) {
            throw new ApiError(
                `Expected entity object with 'id' but got: ${JSON.stringify(result.data)}. Contract drift detected.`,
                { type: 'server' }
            );
        }
        return result.data;
    },

    /**
     * Assert that a result contains a valid object response (no id required).
     * Used for settings, config, and other non-entity objects.
     * @param {{ ok: boolean, data: any }} result
     * @returns {object}
     */
    assertObject(result) {
        if (!result.ok) {
            throw ApiError.fromResult(result);
        }
        if (!result.data || typeof result.data !== 'object') {
            throw new ApiError(
                `Expected object response but got: ${JSON.stringify(result.data)}. Contract drift detected.`,
                { type: 'server' }
            );
        }
        return result.data;
    },

    /**
     * Assert that a result contains a valid auth/me response.
     * Expected shape: { authenticated: boolean, user: { username, roles, ... } }
     * @param {{ ok: boolean, data: any }} result
     * @returns {{ authenticated: boolean, user: object|null }}
     */
    assertAuthMe(result) {
        if (!result.ok) {
            throw ApiError.fromResult(result);
        }
        const data = result.data;
        if (!data || typeof data !== 'object') {
            throw new ApiError(
                `Expected auth/me object but got: ${JSON.stringify(data)}. Contract drift detected.`,
                { type: 'server' }
            );
        }
        return {
            authenticated: !!data.user,
            user: data.user || null,
        };
    },

};

/**
 * Frontend Authentication State
 *
 * Minimal auth-awareness layer.  Stores the current authentication state
 * in memory and exposes helpers the rest of the app can use to decide
 * whether protected operations are available.
 *
 * Contract consumption:
 *   • Consumes /api/auth/me through ApiClient (never fetch() directly)
 *   • Uses ApiClient.assertAuthMe() for explicit response shape validation
 *   • Stores tokens in sessionStorage only (never localStorage)
 *
 * Design goals:
 *   - Know whether auth is enabled on the backend
 *   - Fetch /api/auth/me to establish identity from a real IdP token
 *   - Expose getCurrentUser() and isAuthenticated()
 *   - Handle 401 failures honestly (no silent retries)
 *   - Support tokens from sessionStorage or URL hash fragment (OIDC)
 *
 * Full SSO / OIDC redirect flow is deferred to a later step.
 */
const Auth = {
    // In-memory auth state (never persisted to localStorage for security)
    _user: null,
    _initialized: false,

    /**
     * Initialize auth state by calling /api/auth/me.
     *
     * Should be called once during app startup.  If the backend rejects
     * the call (no token or invalid token), the app is left in an
     * unauthenticated state and the UI will reflect that.
     *
     * Token resolution order:
     *   1. URL hash fragment (e.g. after OIDC redirect: #access_token=...)
     *   2. sessionStorage  (set by loginWithToken or manual injection)
     */
    async init() {
        if (this._initialized) return;
        this._initialized = true;

        // Migrate a token from the URL hash fragment into sessionStorage
        // so subsequent page loads don't lose it.
        this._migrateTokenFromHash();

        // First, fetch public auth config to confirm auth is enabled
        try {
            const configResult = await ApiClient.get('/auth/config');
            if (configResult.ok && configResult.data) {
                // Config.AUTH_ENABLED is a compile-time default; the
                // backend's runtime value is authoritative.
                if (configResult.data.authEnabled === false) {
                    console.info('Auth is disabled on the backend.');
                    return;
                }
            }
        } catch {
            // If /auth/config is unreachable, proceed — /me will fail
            // if auth is actually required.
        }

        // Attempt to resolve the current user
        this._setUserFromAuthResult(await ApiClient.get('/auth/me'));
    },

    /**
     * Parse /api/auth/me response and update local auth state.
     *
     * Expected response shape (governed by backend contract):
     *   { authenticated: boolean, user: { username, roles, ... } | null }
     *
     * If the response is missing or malformed, auth state is cleared.
     */
    _setUserFromAuthResult(meResult) {
        try {
            const parsed = ApiClient.assertAuthMe(meResult);
            if (parsed.authenticated && parsed.user) {
                this._user = parsed.user;
                console.info(`Authenticated as: ${this._user.username || this._user.sub}`);
            } else {
                this._user = null;
                console.warn('No authenticated user — protected operations will be blocked.');
            }
        } catch (e) {
            // Auth response shape mismatch or network failure
            this._user = null;
            console.warn('Auth initialization failed:', e.message);
        }
    },

    /**
     * Return the current authenticated user, or null.
     */
    getCurrentUser() {
        return this._user;
    },

    /**
     * Return true when a valid user context is present.
     */
    isAuthenticated() {
        return this._user !== null;
    },

    /**
     * Return true when the current user holds the specified role.
     */
    hasRole(role) {
        if (!this._user || !this._user.roles) return false;
        return this._user.roles.includes(role);
    },

    /**
     * Convenience helper — return true when the current user is an admin.
     */
    isAdmin() {
        return this.hasRole('admin');
    },

    /**
     * Clear the auth state (logout).
     */
    logout() {
        this._setToken(null);
        this._user = null;
        console.info('Logged out.');
    },

    /**
     * Return the Authorization header value if a token is available,
     * or undefined when not.
     */
    getAuthorizationHeader() {
        const token = this._getToken();
        return token ? `Bearer ${token}` : undefined;
    },

    /**
     * Retrieve the bearer token.
     *
     * Resolution order:
     *   1. sessionStorage  (set by loginWithToken or OIDC redirect)
     */
    _getToken() {
        try {
            return sessionStorage.getItem('aicrm_token');
        } catch {
            // sessionStorage may be unavailable in some contexts
        }
        return null;
    },

    /**
     * Set (or clear) the bearer token in sessionStorage.
     */
    _setToken(token) {
        try {
            if (token) {
                sessionStorage.setItem('aicrm_token', token);
            } else {
                sessionStorage.removeItem('aicrm_token');
            }
        } catch {
            console.warn('Could not store token in sessionStorage.');
        }
    },

    /**
     * If the URL contains an access_token in the hash fragment
     * (common after an OIDC implicit-flow redirect), extract it and
     * store it in sessionStorage.  Then clean the URL.
     *
     * Example hash:
     *   #access_token=eyJ...&token_type=Bearer&expires_in=3600
     */
    _migrateTokenFromHash() {
        if (!window.location.hash) return;

        const hash = window.location.hash.slice(1); // strip leading '#'
        const params = new URLSearchParams(hash);
        const token = params.get('access_token');

        if (token) {
            console.info('Migrating access_token from URL hash fragment.');
            this._setToken(token);

            // Clean the URL so the token doesn't sit in the address bar
            const cleanUrl = window.location.pathname + window.location.search;
            window.history.replaceState({}, document.title, cleanUrl);
        }
    },

    /**
     * Authenticate with a bearer token (real IdP JWT or dev token).
     *
     * Stores the token, calls /api/auth/me to validate it, and updates
     * local auth state.  Works for both development tokens and real
     * IdP JWTs — the backend decides which validation path to use.
     */
    async loginWithToken(token) {
        this._setToken(token);
        const meResult = await ApiClient.get('/auth/me');
        try {
            const parsed = ApiClient.assertAuthMe(meResult);
            if (parsed.authenticated && parsed.user) {
                this._user = parsed.user;
                return { ok: true, user: this._user };
            }
        } catch (e) {
            console.warn('Auth response parse failed during login:', e.message);
        }
        this._user = null;
        this._setToken(null); // clear invalid token
        return { ok: false, error: meResult.error || 'Invalid token' };
    },
};

/**
 * Frontend Configuration
 *
 * Central place for runtime configuration.  Override any value by setting
 * the matching key on `window.AICRM_CONFIG` *before* this script loads,
 * or by injecting a small <script> block in index.html:
 *
 *   <script>
 *     window.AICRM_CONFIG = { API_BASE_URL: 'http://localhost:9000/api' };
 *   </script>
 *
 * Runtime modes:
 *
 *   • Local dev (file:// or localhost:8080):
 *       API calls go to http://localhost:9000/api
 *
 *   • Container (docker-compose, nginx reverse proxy):
 *       API calls go to /api (relative path — nginx proxies to backend)
 *
 *   • Manual override:
 *       Set window.AICRM_CONFIG.API_BASE_URL before this script loads.
 */
const Config = Object.freeze({
    /**
     * Base URL for the AICRM backend API.
     *
     * Resolution order:
     *   1. window.AICRM_CONFIG.API_BASE_URL  (manual override)
     *   2. relative '/api' if served from same origin as backend
     *   3. explicit default 'http://localhost:9000/api'
     */
    API_BASE_URL: (function () {
        const manual = (typeof window.AICRM_CONFIG !== 'undefined')
            && window.AICRM_CONFIG.API_BASE_URL;
        if (manual) return manual.replace(/\/+$/, '');          // strip trailing slashes

        // When served from the backend's own origin (e.g. behind a reverse
        // proxy), use same-origin relative path so no CORS is needed.
        if (window.location.origin === 'http://localhost:9000') {
            return '/api';
        }

        // Default for local dev behind nginx: use relative path so nginx
        // reverse-proxies /api/* to the backend container.
        return '/api';
    })(),

    /** Human-readable environment label (shown in settings, logs, etc.) */
    ENVIRONMENT: 'development',

    // -----------------------------------------------------------------------
    // Authentication (public client configuration only — no secrets)
    // -----------------------------------------------------------------------

    /**
     * Whether the backend enforces authentication.
     * Overridden at runtime by /api/auth/config; the default is a safe
     * fallback so the UI can render before the network call completes.
     */
    AUTH_ENABLED: true,

    /** Identity Provider issuer URL (Keycloak, Entra ID, Auth0, …) */
    AUTH_ISSUER: (function () {
        const manual = (typeof window.AICRM_CONFIG !== 'undefined')
            && window.AICRM_CONFIG.AUTH_ISSUER;
        return manual || 'https://dev.example.com/realms/aicrm';
    })(),

    /** Public client ID — safe to expose in frontend code. */
    AUTH_CLIENT_ID: (function () {
        const manual = (typeof window.AICRM_CONFIG !== 'undefined')
            && window.AICRM_CONFIG.AUTH_CLIENT_ID;
        return manual || 'aicrm-frontend';
    })(),

    /** Redirect URI for code-flow login (placeholder for future SSO). */
    AUTH_REDIRECT_URI: (function () {
        const manual = (typeof window.AICRM_CONFIG !== 'undefined')
            && window.AICRM_CONFIG.AUTH_REDIRECT_URI;
        return manual || window.location.origin + window.location.pathname;
    })(),
});

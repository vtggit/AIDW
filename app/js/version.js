/**
 * AICRM Version Configuration
 *
 * The canonical version source is the VERSION file at repo root.
 * The backend reads it and exposes it via /api/health.
 * This module fetches the version from the backend at runtime to
 * avoid frontend/backend version drift.
 *
 * Contract consumption:
 *   • Uses ApiClient.get() instead of raw fetch() for consistency
 *   • Health endpoint response shape: { status, app_version, ... }
 */

/**
 * Fetch the current application version from the backend.
 * Falls back to a placeholder if the backend is unreachable.
 */
async function fetchAppVersion() {
    try {
        const result = await ApiClient.get('/health');
        if (result.ok && result.data) {
            return result.data.app_version || 'unknown';
        }
    } catch (_error) {
        // Backend not reachable yet; will retry on next load
    }
    return 'loading...';
}

// Expose APP_VERSION as a promise that resolves to the version string.
// Code that needs the version synchronously can use the initial placeholder
// and update the UI once the promise resolves.
const APP_VERSION_INITIAL = 'loading...';
const APP_VERSION = fetchAppVersion();

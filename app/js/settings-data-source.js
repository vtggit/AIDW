/**
 * Settings Data Source — Primary data access layer for application settings.
 *
 * The backend API is the single source of truth for all settings operations.
 * There is no localStorage fallback — when the backend fails, an error is
 * propagated to the UI so the user sees an honest failure.
 *
 * Contract consumption:
 *   • Calls ApiClient domain methods (never fetch() directly)
 *   • ApiClient validates response shapes and throws ApiError on failure
 */
const SettingsDataSource = {

    /**
     * Get current settings from the backend.
     * Throws ApiError on failure so the caller can surface an error to the user.
     */
    async getSettings() {
        return await ApiClient.getSettingsFromApi();
    },

    /**
     * Update settings via the backend (admin only).
     * Throws ApiError on failure — no local fallback.
     */
    async updateSettings(payload) {
        return await ApiClient.updateSettingsInApi(payload);
    },
};

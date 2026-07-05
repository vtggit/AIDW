/**
 * Activities Data Source — Primary data access layer for activities.
 *
 * The backend API is the single source of truth for all activity operations.
 * There is no localStorage fallback — when the backend fails, an error is
 * propagated to the UI so the user sees an honest failure.
 *
 * Contract consumption:
 *   • Calls ApiClient domain methods (never fetch() directly)
 *   • ApiClient validates response shapes and throws ApiError on failure
 *   • This layer normalizes backend snake_case → frontend camelCase
 */
const ActivitiesDataSource = {

    /**
     * Get activities from the backend.
     * Throws ApiError on failure so the caller can surface an error to the user.
     */
    async getActivities() {
        const activities = await ApiClient.getActivitiesFromApi();
        return activities.map(a => this._normalizeActivity(a));
    },

    /**
     * Create an activity via the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async createActivity(activity) {
        const entity = await ApiClient.createActivityInApi(activity);
        return this._normalizeActivity(entity);
    },

    /**
     * Update an existing activity via the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async updateActivity(id, activity) {
        const entity = await ApiClient.updateActivityInApi(id, activity);
        return this._normalizeActivity(entity);
    },

    /**
     * Delete an activity via the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async deleteActivity(id) {
        await ApiClient.deleteActivityInApi(id);
    },

    /**
     * Normalize an activity object from the backend (snake_case → camelCase).
     */
    _normalizeActivity(a) {
        if (!a) return a;
        return {
            ...a,
            createdAt: a.created_at || a.createdAt,
            updatedAt: a.updated_at || a.updatedAt,
        };
    },
};

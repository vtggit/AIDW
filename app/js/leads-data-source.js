/**
 * Leads Data Source — Primary data access layer for leads.
 *
 * The backend API is the single source of truth for all lead operations.
 * There is no localStorage fallback — when the backend fails, an error is
 * propagated to the UI so the user sees an honest failure.
 *
 * Contract consumption:
 *   • Calls ApiClient domain methods (never fetch() directly)
 *   • ApiClient validates response shapes and throws ApiError on failure
 *   • This layer normalizes backend snake_case → frontend camelCase
 */
const LeadsDataSource = {

    /**
     * Get leads from the backend.
     * Throws ApiError on failure so the caller can surface an error to the user.
     */
    async getLeads() {
        const leads = await ApiClient.getLeadsFromApi();
        return leads.map(l => this._normalizeLead(l));
    },

    /**
     * Get a single lead by ID from the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async getLead(id) {
        const result = await ApiClient.get(`/leads/${id}`);
        if (!result.ok) {
            throw ApiError.fromResult(result);
        }
        return this._normalizeLead(result.data);
    },

    /**
     * Create a lead via the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async createLead(lead) {
        const entity = await ApiClient.createLeadInApi(lead);
        return this._normalizeLead(entity);
    },

    /**
     * Update a lead via the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async updateLead(id, lead) {
        const entity = await ApiClient.updateLeadInApi(id, lead);
        return this._normalizeLead(entity);
    },

    /**
     * Delete a lead via the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async deleteLead(id) {
        await ApiClient.deleteLeadInApi(id);
    },

    /**
     * Normalize a lead object from the backend (snake_case → camelCase).
     */
    _normalizeLead(l) {
        if (!l) return l;
        return {
            ...l,
            createdAt: l.created_at || l.createdAt,
            updatedAt: l.updated_at || l.updatedAt,
        };
    },
};

/**
 * Templates Data Source — Primary data access layer for templates.
 *
 * The backend API is the single source of truth for all template operations.
 * There is no localStorage fallback — when the backend fails, an error is
 * propagated to the UI so the user sees an honest failure.
 *
 * Contract consumption:
 *   • Calls ApiClient domain methods (never fetch() directly)
 *   • ApiClient validates response shapes and throws ApiError on failure
 *   • This layer normalizes backend snake_case → frontend camelCase
 */
const TemplatesDataSource = {

    /**
     * Get templates from the backend.
     * Throws ApiError on failure so the caller can surface an error to the user.
     */
    async getTemplates() {
        const templates = await ApiClient.getTemplatesFromApi();
        return templates.map(t => this._normalizeTemplate(t));
    },

    /**
     * Create a template via the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async createTemplate(template) {
        const entity = await ApiClient.createTemplateInApi(template);
        return this._normalizeTemplate(entity);
    },

    /**
     * Update a template via the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async updateTemplate(id, template) {
        const entity = await ApiClient.updateTemplateInApi(id, template);
        return this._normalizeTemplate(entity);
    },

    /**
     * Delete a template via the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async deleteTemplate(id) {
        await ApiClient.deleteTemplateInApi(id);
    },

    /**
     * Normalize a template object from the backend (snake_case → camelCase).
     */
    _normalizeTemplate(t) {
        if (!t) return t;
        return {
            ...t,
            body: t.content || t.body,
            createdAt: t.created_at || t.createdAt,
            updatedAt: t.updated_at || t.updatedAt,
        };
    },
};

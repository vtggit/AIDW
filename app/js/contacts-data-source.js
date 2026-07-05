/**
 * Contacts Data Source — Primary data access layer for contacts.
 *
 * The backend API is the single source of truth for all contact operations.
 * There is no localStorage fallback — when the backend fails, an error is
 * propagated to the UI so the user sees an honest failure.
 *
 * Contract consumption:
 *   • Calls ApiClient domain methods (never fetch() directly)
 *   • ApiClient validates response shapes and throws ApiError on failure
 *   • This layer normalizes backend snake_case → frontend camelCase
 */
const ContactsDataSource = {

    /**
     * Get contacts from the backend.
     * Throws ApiError on failure so the caller can surface an error to the user.
     */
    async getContacts() {
        const contacts = await ApiClient.getContactsFromApi();
        return contacts.map(c => this._normalizeContact(c));
    },

    /**
     * Create a contact via the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async createContact(contact) {
        const entity = await ApiClient.createContactInApi(contact);
        return this._normalizeContact(entity);
    },

    /**
     * Update a contact via the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async updateContact(id, contact) {
        const entity = await ApiClient.updateContactInApi(id, contact);
        return this._normalizeContact(entity);
    },

    /**
     * Delete a contact via the backend.
     * Throws ApiError on failure — no local fallback.
     */
    async deleteContact(id) {
        await ApiClient.deleteContactInApi(id);
    },

    /**
     * Set tags for a contact.
     */
    async setContactTags(contactId, tagIds) {
        await ApiClient.setContactTagsInApi(contactId, tagIds);
    },

    /**
     * Normalize a contact object from the backend (snake_case → camelCase).
     */
    _normalizeContact(c) {
        if (!c) return c;
        return {
            ...c,
            createdAt: c.created_at || c.createdAt,
            updatedAt: c.updated_at || c.updatedAt,
            tags: Array.isArray(c.tags) ? c.tags : [],
        };
    },
};

/**
 * Tags Data Source — CRUD for tag definitions.
 */
const TagsDataSource = {
    async getTags() {
        return await ApiClient.getTagsFromApi();
    },

    async createTag(name, color = '#3b82f6') {
        return await ApiClient.createTagInApi({ name, color });
    },

    async updateTag(id, data) {
        return await ApiClient.updateTagInApi(id, data);
    },

    async deleteTag(id) {
        await ApiClient.deleteTagInApi(id);
    },
};

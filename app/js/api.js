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
    async getCompaniesFromApi() {
        return this.getAllPages('/companies');
    },

    async createCompanyInApi(company) {
        const payload = { name: company.name, website: company.website, industry: company.industry, employee_count: company.employee_count };
        const result = await this.post('/companies', payload);
        return this.assertEntity(result);
    },

    async updateCompanyInApi(id, company) {
        const payload = {};
        for (const key of ['name', 'website', 'industry', 'employee_count']) {
            if (company[key] !== undefined) { payload[key] = company[key]; }
        }
        const result = await this.put(`/companies/${id}`, payload);
        return this.assertEntity(result);
    },

    async deleteCompanyInApi(id) {
        const result = await this.delete(`/companies/${id}`);
        if (!result.ok) { throw ApiError.fromResult(result); }
    },

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

    // === Contacts ===

    /**
     * Fetch contacts from the backend API.
     * Returns a validated array of contact objects.
     * Throws ApiError on HTTP failure or contract drift.
     */
    async getContactsFromApi() {
        return this.getAllPages('/contacts');
    },

    /**
     * Create a contact via the backend API.
     * Returns a validated contact entity (object with id).
     * Throws ApiError on HTTP failure or contract drift.
     */
    async createContactInApi(contact) {
        const payload = {
            name: contact.name,
            email: contact.email || null,
            phone: contact.phone || null,
            company: contact.company || null,
            status: contact.status || 'active',
            notes: contact.notes || null,
        };
        const result = await this.post('/contacts', payload);
        return this.assertEntity(result);
    },

    /**
     * Update a contact via the backend API.
     * Returns a validated contact entity (object with id).
     * Throws ApiError on HTTP failure or contract drift.
     */
    async updateContactInApi(id, contact) {
        const payload = {};
        for (const key of ['name', 'email', 'phone', 'company', 'status', 'notes', 'tag_ids']) {
            if (contact[key] !== undefined) {
                payload[key] = contact[key] || null;
            }
        }
        const result = await this.put(`/contacts/${id}`, payload);
        return this.assertEntity(result);
    },

    /**
     * Delete a contact via the backend API.
     * Returns void on success (204).
     * Throws ApiError on HTTP failure.
     */
    async deleteContactInApi(id) {
        const result = await this.delete(`/contacts/${id}`);
        if (!result.ok) {
            throw ApiError.fromResult(result);
        }
    },

    async bulkDeleteContactsInApi(ids) {
        const result = await this.post('/contacts/bulk-delete', { ids });
        if (!result.ok) {
            throw ApiError.fromResult(result);
        }
        return result.data;
    },

    async bulkUpdateContactsStatusInApi(ids, status) {
        const result = await this.post('/contacts/bulk-update-status', { ids, status });
        return this.assertEntity(result);
    },

    /**
     * Find duplicate contacts via the backend API.
     * Returns { totalGroups, totalDuplicates, groups: [{ groupId, matchType, contacts: [...] }] }.
     */
    async findDuplicateContactsInApi() {
        const result = await this.get('/contacts/duplicates');
        return this.assertObject(result);
    },

    // === Tags ===

    async getTagsFromApi() {
        return this.getAllPages('/tags');
    },

    async createTagInApi(tag) {
        const result = await this.post('/tags', tag);
        return this.assertEntity(result);
    },

    async updateTagInApi(id, tag) {
        const result = await this.put(`/tags/${id}`, tag);
        return this.assertEntity(result);
    },

    async deleteTagInApi(id) {
        const result = await this.delete(`/tags/${id}`);
        if (!result.ok) {
            throw ApiError.fromResult(result);
        }
    },

    async setContactTagsInApi(contactId, tagIds) {
        const result = await this.put(`/tags/contacts/${contactId}/tags`, { tag_ids: tagIds });
        if (!result.ok) {
            throw ApiError.fromResult(result);
        }
    },

    // === Templates ===

    /**
     * Fetch templates from the backend API.
     * Returns a validated array of template objects.
     * Throws ApiError on HTTP failure or contract drift.
     */
    async getTemplatesFromApi() {
        return this.getAllPages('/templates');
    },

    /**
     * Create a template via the backend API.
     * Returns a validated template entity (object with id).
     * Throws ApiError on HTTP failure or contract drift.
     */
    async createTemplateInApi(template) {
        const payload = {
            name: template.name,
            category: template.category || 'other',
            subject: template.subject || null,
            content: template.body || template.content || '',
        };
        const result = await this.post('/templates', payload);
        return this.assertEntity(result);
    },

    /**
     * Update a template via the backend API.
     * Returns a validated template entity (object with id).
     * Throws ApiError on HTTP failure or contract drift.
     */
    async updateTemplateInApi(id, template) {
        const payload = {};
        for (const key of ['name', 'category', 'subject']) {
            if (template[key] !== undefined) {
                payload[key] = template[key] || null;
            }
        }
        if (template.body !== undefined || template.content !== undefined) {
            payload.content = template.body || template.content || '';
        }
        const result = await this.put(`/templates/${id}`, payload);
        return this.assertEntity(result);
    },

    /**
     * Delete a template via the backend API.
     * Returns void on success (204).
     * Throws ApiError on HTTP failure.
     */
    async deleteTemplateInApi(id) {
        const result = await this.delete(`/templates/${id}`);
        if (!result.ok) {
            throw ApiError.fromResult(result);
        }
    },

    // === Leads ===

    /**
     * Fetch leads from the backend API.
     * Returns a validated array of lead objects.
     * Throws ApiError on HTTP failure or contract drift.
     */
    async getLeadsFromApi() {
        return this.getAllPages('/leads');
    },

    /**
     * Create a lead via the backend API.
     * Returns a validated lead entity (object with id).
     * Throws ApiError on HTTP failure or contract drift.
     */
    async createLeadInApi(lead) {
        const payload = {
            name: lead.name,
            company: lead.company || null,
            email: lead.email || null,
            phone: lead.phone || null,
            value: lead.value ? Number(lead.value) : null,
            stage: lead.stage || 'new',
            source: lead.source || null,
            notes: lead.notes || null,
        };
        const result = await this.post('/leads', payload);
        return this.assertEntity(result);
    },

    /**
     * Update a lead via the backend API.
     * Returns a validated lead entity (object with id).
     * Throws ApiError on HTTP failure or contract drift.
     */
    async updateLeadInApi(id, lead) {
        const payload = {};
        for (const key of ['name', 'company', 'email', 'phone', 'stage', 'source', 'notes']) {
            if (lead[key] !== undefined) {
                payload[key] = lead[key] || null;
            }
        }
        if (lead.value !== undefined) {
            payload.value = lead.value ? Number(lead.value) : null;
        }
        const result = await this.put(`/leads/${id}`, payload);
        return this.assertEntity(result);
    },

    /**
     * Update a lead's stage via PATCH (used by Kanban drag-and-drop).
     * Returns the updated lead entity.
     */
    async updateLeadStageInApi(id, stage) {
        const result = await this.patch(`/leads/${id}/stage`, { stage });
        return this.assertEntity(result);
    },

    /**
     * Delete a lead via the backend API.
     * Returns void on success (204).
     * Throws ApiError on HTTP failure.
     */
    async deleteLeadInApi(id) {
        const result = await this.delete(`/leads/${id}`);
        if (!result.ok) {
            throw ApiError.fromResult(result);
        }
    },

    // === Activities ===

    /**
     * Fetch activities from the backend API.
     * Returns a validated array of activity objects.
     * Throws ApiError on HTTP failure or contract drift.
     */
    async getActivitiesFromApi() {
        return this.getAllPages('/activities');
    },

    /**
     * Create an activity via the backend API.
     * Returns a validated activity entity (object with id).
     * Throws ApiError on HTTP failure or contract drift.
     */
    async createActivityInApi(activity) {
        const payload = {
            type: activity.type || 'note',
            description: activity.description || '',
            contact_name: activity.contactName || activity.contact_name || null,
            occurred_at: activity.date || activity.occurred_at || null,
            due_date: activity.dueDate || activity.due_date || null,
            status: activity.status || 'pending',
        };
        const result = await this.post('/activities', payload);
        return this.assertEntity(result);
    },

    /**
     * Update an activity via the backend API.
     * Returns a validated activity entity (object with id).
     * Throws ApiError on HTTP failure or contract drift.
     */
    async updateActivityInApi(id, activity) {
        const payload = {};
        if (activity.type !== undefined) payload.type = activity.type;
        if (activity.description !== undefined) payload.description = activity.description;
        if (activity.contactName !== undefined || activity.contact_name !== undefined) {
            payload.contact_name = activity.contactName || activity.contact_name || null;
        }
        if (activity.date !== undefined || activity.occurred_at !== undefined) {
            payload.occurred_at = activity.date || activity.occurred_at || null;
        }
        if (activity.dueDate !== undefined || activity.due_date !== undefined) {
            payload.due_date = activity.dueDate || activity.due_date || null;
        }
        if (activity.status !== undefined) payload.status = activity.status;
        const result = await this.put(`/activities/${id}`, payload);
        return this.assertEntity(result);
    },

    /**
     * Delete an activity via the backend API.
     * Returns void on success (204).
     * Throws ApiError on HTTP failure.
     */
    async deleteActivityInApi(id) {
        const result = await this.delete(`/activities/${id}`);
        if (!result.ok) {
            throw ApiError.fromResult(result);
        }
    },

    // === Settings ===

    /**
     * Fetch current settings from the backend API.
     * Returns a validated settings object.
     * Throws ApiError on HTTP failure or contract drift.
     */
    async getSettingsFromApi() {
        const result = await this.get('/settings');
        return this.assertObject(result);
    },

    /**
     * Update settings via the backend API (admin only).
     * Returns a validated settings object.
     * Throws ApiError on HTTP failure or contract drift.
     */
    async updateSettingsInApi(payload) {
        const result = await this.put('/settings', { payload });
        return this.assertObject(result);
    },

    /**
     * Reset all settings to defaults via the backend API.
     */
    async resetSettingsInApi() {
        const result = await this.delete('/settings');
        return this.assertObject(result);
    },

    // === Analytics ===

    /**
     * Fetch the lead conversion funnel analytics from the backend API.
     * Returns a validated funnel analytics object.
     * Throws ApiError on HTTP failure or contract drift.
     */
    async getFunnelAnalyticsFromApi() {
        const result = await this.get('/analytics/funnel');
        return this.assertObject(result);
    },

    /**
     * Fetch activity trend data from the backend API.
     * @param {string} range - '7d', '30d', or '90d'
     * @param {string} group - 'day' or 'week'
     */
    async getActivityTrendsFromApi(range = '30d', group = 'day') {
        const result = await this.get(`/analytics/activity-trends?range=${encodeURIComponent(range)}&group=${encodeURIComponent(group)}`);
        return this.assertObject(result);
    },

    // === Deal Outcomes (Win/Loss Reasons) ===

    /**
     * Fetch all deal outcomes from the backend API.
     */
    async getDealOutcomesFromApi() {
        return this.getAllPages('/deal-outcomes');
    },

    /**
     * Create a deal outcome via the backend API.
     */
    async createDealOutcomeInApi(payload) {
        const result = await this.post('/deal-outcomes', payload);
        return this.assertObject(result);
    },

    /**
     * Fetch win/loss analytics summary from the backend API.
     */
    async getDealOutcomeAnalyticsFromApi() {
        const result = await this.get('/deal-outcomes/analytics');
        return this.assertObject(result);
    },

    /**
     * Fetch the deal outcome for a specific lead.
     */
    async getOutcomeForLeadInApi(leadId) {
        const result = await this.get(`/deal-outcomes/leads/${leadId}`);
        if (result.status === 204 || result.data === null) {
            return null;
        }
        return this.assertObject(result);
    },

    // ── Sales Goals ──────────────────────────────────────────────────

    /**
     * Fetch all sales goals from the backend API.
     */
    async getSalesGoals(activeOnly = '') {
        return this.getAllPages('/sales-goals' + activeOnly);
    },

    /**
     * Fetch a single sales goal by ID.
     */
    async getSalesGoal(id) {
        const result = await this.get(`/sales-goals/${id}`);
        return this.assertObject(result);
    },

    /**
     * Create a new sales goal.
     */
    async createSalesGoal(goal) {
        const payload = {
            name: goal.name,
            type: goal.type,
            target_value: goal.targetValue,
            period: goal.period,
            start_date: goal.startDate,
            end_date: goal.endDate,
        };
        const result = await this.post('/sales-goals', payload);
        return this.assertObject(result);
    },

    /**
     * Update an existing sales goal.
     */
    async updateSalesGoal(id, goal) {
        const payload = {};
        if (goal.name !== undefined) payload.name = goal.name;
        if (goal.targetValue !== undefined) payload.target_value = goal.targetValue;
        if (goal.startDate !== undefined) payload.start_date = goal.startDate;
        if (goal.endDate !== undefined) payload.end_date = goal.endDate;
        const result = await this.patch(`/sales-goals/${id}`, payload);
        return this.assertObject(result);
    },

    /**
     * Delete a sales goal.
     */
    async deleteSalesGoal(id) {
        await this.delete(`/sales-goals/${id}`);
    },

    /**
     * Fetch progress summary for all active goals.
     */
    async getSalesGoalsProgress() {
        const result = await this.get('/sales-goals/progress');
        return this.assertObject(result);
    },

    /**
     * Recalculate current values from CRM data.
     */
    async recalculateSalesGoals() {
        const result = await this.post('/sales-goals/recalculate', {});
        return Array.isArray(result) ? result : [];
    },
};

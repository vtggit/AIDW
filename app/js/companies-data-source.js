/**
 * Companies Data Source — backend-backed data access for companies.
 * Calls ApiClient domain methods (never fetch() directly) and normalizes
 * the backend snake_case into the frontend camelCase. No local fallback.
 */
const CompaniesDataSource = {
    async getCompanies() {
        const items = await ApiClient.getCompaniesFromApi();
        return items.map(c => this._normalizeCompany(c));
    },

    async createCompany(data) {
        const entity = await ApiClient.createCompanyInApi(data);
        return this._normalizeCompany(entity);
    },

    async updateCompany(id, data) {
        const entity = await ApiClient.updateCompanyInApi(id, data);
        return this._normalizeCompany(entity);
    },

    async deleteCompany(id) {
        await ApiClient.deleteCompanyInApi(id);
    },

    _normalizeCompany(c) {
        if (!c) return c;
        return {
            ...c,
            createdAt: c.created_at || c.createdAt,
            updatedAt: c.updated_at || c.updatedAt,
            employeeCount: c.employee_count || c.employeeCount,
        };
    },
};

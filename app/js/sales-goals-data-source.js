/**
 * Sales Goals Data Source
 *
 * Communicates with the /api/sales-goals endpoints via ApiClient.
 */

const SalesGoalsDataSource = {
    async getGoals(activeOnly = false) {
        const params = activeOnly ? '?active_only=true' : '';
        const goals = await ApiClient.getSalesGoals(params);
        return goals.map(g => this._normalizeGoal(g));
    },

    async getGoal(id) {
        const goal = await ApiClient.getSalesGoal(id);
        return this._normalizeGoal(goal);
    },

    async createGoal(goal) {
        const entity = await ApiClient.createSalesGoal(goal);
        return this._normalizeGoal(entity);
    },

    async updateGoal(id, goal) {
        const entity = await ApiClient.updateSalesGoal(id, goal);
        return this._normalizeGoal(entity);
    },

    async deleteGoal(id) {
        return ApiClient.deleteSalesGoal(id);
    },

    async getProgress() {
        const result = await ApiClient.getSalesGoalsProgress();
        return {
            goals: (result.goals || []).map(g => this._normalizeGoal(g)),
            overall_progress: result.overall_progress || 0,
        };
    },

    async recalculateValues() {
        const goals = await ApiClient.recalculateSalesGoals();
        return goals.map(g => this._normalizeGoal(g));
    },

    _normalizeGoal(g) {
        return {
            ...g,
            id: g.id,
            name: g.name,
            type: g.type,
            targetValue: parseFloat(g.target_value) || 0,
            currentValue: parseFloat(g.current_value) || 0,
            period: g.period,
            startDate: g.start_date,
            endDate: g.end_date,
            progressPercent: parseFloat(g.progress_percent) || 0,
            createdAt: g.created_at,
            updatedAt: g.updated_at,
        };
    },
};

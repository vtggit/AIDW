/**
 * AICRM - Main Application Logic
 */
const App = {
    currentPage: 'dashboard',
    editId: null,
    editType: null,

    async init() {
        this._selectedContactIds = new Set();
        this._currentContactIds = [];
        this.bindNavigation();
        this.bindThemeToggle();
        this.bindMenuToggle();
        this.bindSearch();
        this.bindContacts();
        this.bindLeads();
        this.bindActivities();
        this.bindTemplates();
        this.bindSettings();
        this.bindModal();
        this.bindKeyboardShortcuts();
        this.bindFAB();
        this.bindBulkOperations();
        this.bindPdfExport();
        this.bindVersion();
        this.bindAuth();
        this.loadTheme();

        // Check backend availability before rendering
        const backendAvailable = await this._checkBackendAvailability();
        if (!backendAvailable) {
            this._showBackendUnavailableBanner(true);
        }

        this.renderDashboard();
        this.updateLastBackupDisplay();
        this.updateOverdueBadge();
        this.loadReminderSettings();

        // Auto-start reminder checker if previously enabled
        this._autoStartReminders();
    },

    /**
     * Check if reminders were previously enabled and auto-start the checker.
     */
    async _autoStartReminders() {
        try {
            const settings = await SettingsDataSource.getSettings();
            const reminder = settings?.payload?.reminder;
            if (reminder && reminder.enabled) {
                this._startReminderChecker();
            }
        } catch (err) {
            console.warn('Failed to auto-start reminders:', err);
        }
    },

    /**
     * Check if the backend is available at startup.
     * Returns true if the backend responds to a health check.
     */
    async _checkBackendAvailability() {
        try {
            return await ApiClient.isHealthy();
        } catch (err) {
            console.warn('Backend health check failed at startup:', err.message);
            return false;
        }
    },

    // === Navigation ===
    bindNavigation() {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                const page = item.dataset.page;
                this.navigate(page);
            });
        });
    },

    async navigate(page) {
        this.currentPage = page;
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.querySelector(`.nav-item[data-page="${page}"]`).classList.add('active');
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.getElementById(`page-${page}`).classList.add('active');
        document.getElementById('page-title').textContent = this.getPageTitle(page);

        if (page === 'dashboard') await this.renderDashboard();
        if (page === 'contacts') await this.renderContacts();
        if (page === 'leads') await this.renderLeads();
        if (page === 'analytics') await this.renderAnalytics();
        if (page === 'activities') await this._renderActivitiesView();
        if (page === 'templates') this.renderTemplates();
        if (page === 'winloss') await this.renderWinLossPage();
        if (page === 'salesgoals') await this.renderSalesGoals();
        if (page === 'settings') this.renderSettings();
        if (page === 'companies') await this.renderCompanies();

        this.updateOverdueBadge();

        // Close mobile sidebar
        document.getElementById('sidebar').classList.remove('open');
    },

    getPageTitle(page) {
        const titles = {
            dashboard: 'Dashboard',
            contacts: 'Contacts',
            leads: 'Leads',
            analytics: 'Analytics',
            activities: 'Activities',
            templates: 'Email Templates',
            winloss: 'Win/Loss Reasons',
            companies: 'Companies',
            settings: 'Settings'
        };
        return titles[page] || page;
    },

    // === Theme ===
    bindThemeToggle() {
        document.getElementById('theme-toggle').addEventListener('click', async () => {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const newTheme = isDark ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', newTheme);
            document.getElementById('theme-toggle').textContent = isDark ? '🌙' : '☀️';
            // Persist theme change to backend
            try {
                await SettingsDataSource.updateSettings({ theme: newTheme });
            } catch (err) {
                this.showNotification(`Failed to save theme: ${err.message}`, 'error');
            }
        });
    },

    bindVersion() {
        const sidebarEl = document.getElementById('app-version-sidebar');
        const settingsEl = document.getElementById('app-version-settings');
        // APP_VERSION is now a Promise (fetched from backend at runtime).
        // Show initial placeholder, then update once resolved.
        if (sidebarEl) sidebarEl.textContent = `v${APP_VERSION_INITIAL}`;
        if (settingsEl) settingsEl.textContent = APP_VERSION_INITIAL;

        APP_VERSION.then(version => {
            if (sidebarEl) sidebarEl.textContent = `v${version}`;
            if (settingsEl) settingsEl.textContent = version;
        });
    },

    // === Authentication ===
    bindAuth() {
        const statusEl = document.getElementById('auth-status');
        if (!statusEl) return;

        // Clicking the status opens the login dialog when not authenticated
        statusEl.addEventListener('click', () => {
            if (Auth.isAuthenticated()) {
                // Logged in — offer logout
                if (confirm('Log out?')) {
                    Auth.logout();
                    this._updateAuthStatus();
                    this._showAuthBanner(true);
                    this._applyAdminOnlyVisibility();
                }
            } else {
                this._openLoginModal();
            }
        });

        // Initialize auth state asynchronously (don't block render)
        Auth.init().then(() => {
            this._updateAuthStatus();
            this._showAuthBanner(!Auth.isAuthenticated());
            this._applyAdminOnlyVisibility();
        });
    },

    /**
     * Hide or show elements marked with data-admin-only="true"
     * based on the current user's admin role.
     */
    _applyAdminOnlyVisibility() {
        document.querySelectorAll('[data-admin-only="true"]').forEach(el => {
            el.style.display = Auth.isAdmin() ? '' : 'none';
        });
    },

    /** Update the header auth indicator to reflect current state. */
    _updateAuthStatus() {
        const statusEl = document.getElementById('auth-status');
        if (!statusEl) return;

        if (Auth.isAuthenticated()) {
            const user = Auth.getCurrentUser();
            statusEl.innerHTML =
                `<span class="auth-indicator">🟢</span>` +
                `<span class="auth-username" title="${user.display_name || user.sub}">${user.display_name || user.sub}</span>`;
            statusEl.title = `Logged in as ${user.display_name || user.sub}`;
        } else {
            statusEl.innerHTML = `<span class="auth-indicator">🔴</span>`;
            statusEl.title = 'Not authenticated — click to log in';
        }
    },

    /** Show or hide the "authentication required" banner. */
    _showAuthBanner(show) {
        let banner = document.getElementById('auth-required-banner');
        if (show) {
            if (!banner) {
                banner = document.createElement('div');
                banner.id = 'auth-required-banner';
                banner.className = 'auth-required-banner active';
                banner.innerHTML =
                    '⚠️ Authentication required to access Contacts. ' +
                    '<button id="auth-banner-login-btn" style="margin-left:8px;cursor:pointer;">Log In</button>';
                const mainContent = document.getElementById('main-content');
                if (mainContent) {
                    mainContent.insertBefore(banner, mainContent.firstChild);
                }
                document.getElementById('auth-banner-login-btn').addEventListener('click', () => {
                    this._openLoginModal();
                });
            }
        } else if (banner) {
            banner.remove();
        }
    },

    /** Open the simple login modal (Step 8 placeholder). */
    _openLoginModal() {
        // Remove existing modal if any
        const existing = document.getElementById('login-modal');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'login-modal';
        overlay.className = 'modal-overlay active';
        overlay.innerHTML = `
            <div class="modal-box">
                <h3>🔐 Sign In</h3>
                <p>Enter your authentication token to access AICRM.</p>
                <div class="modal-error" id="login-error"></div>
                <input type="text" id="login-token" placeholder="Bearer token" autocomplete="off">
                <div class="modal-actions">
                    <button id="login-cancel">Cancel</button>
                    <button id="login-submit" class="primary">Sign In</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        const tokenInput = document.getElementById('login-token');
        const errorEl = document.getElementById('login-error');

        // Focus the token input
        requestAnimationFrame(() => tokenInput.focus());

        const close = () => overlay.remove();

        document.getElementById('login-cancel').addEventListener('click', close);

        // Close on overlay click (not on the box)
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) close();
        });

        const attemptLogin = async () => {
            const token = tokenInput.value.trim();
            if (!token) {
                errorEl.textContent = 'Please enter a token.';
                return;
            }
            errorEl.textContent = '';
            const result = await Auth.loginWithToken(token);
            if (result.ok) {
                close();
                this._updateAuthStatus();
                this._showAuthBanner(false);
                this._applyAdminOnlyVisibility();
                // Refresh the current page so data loads with the new auth token
                if (this.currentPage === 'dashboard') {
                    await this.renderDashboard();
                } else {
                    await this.renderCurrentPage();
                }
                this.showNotification(`Welcome, ${result.user.display_name || result.user.sub}`, 'success');
            } else {
                errorEl.textContent = result.error || 'Invalid token.';
            }
        };

        document.getElementById('login-submit').addEventListener('click', attemptLogin);
        tokenInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') attemptLogin();
        });
    },

    // === Theme ===
    loadTheme() {
        // Load theme from backend settings
        this._loadThemeFromBackend();
    },

    /**
     * Load theme preference from the backend settings.
     * Falls back to 'light' if the backend is unavailable.
     */
    async _loadThemeFromBackend() {
        try {
            const settings = await SettingsDataSource.getSettings();
            if (settings && settings.payload && settings.payload.theme === 'dark') {
                document.documentElement.setAttribute('data-theme', 'dark');
                const toggle = document.getElementById('theme-toggle');
                if (toggle) toggle.textContent = '🌙';
            }
        } catch (err) {
            console.warn('Could not load theme from backend:', err.message);
            // Default to light theme
        }
    },

    // === Menu Toggle (Mobile) ===
    bindMenuToggle() {
        document.getElementById('menu-toggle').addEventListener('click', () => {
            document.getElementById('sidebar').classList.toggle('open');
        });
    },

    // === Global Search ===
    bindSearch() {
        const searchInput = document.getElementById('global-search');
        let searchTimeout;
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                const query = searchInput.value.toLowerCase().trim();
                if (!query) {
                    this.renderCurrentPage();
                    return;
                }
                this.performSearch(query);
            }, 300);
        });
    },

    async performSearch(query) {
        let allContacts;
        try {
            allContacts = await ContactsDataSource.getContacts();
        } catch (err) {
            console.error('Failed to load contacts for search:', err);
            allContacts = [];
        }
        const contacts = allContacts.filter(c =>
            c.name.toLowerCase().includes(query) ||
            (c.email || '').toLowerCase().includes(query) ||
            (c.company || '').toLowerCase().includes(query)
        );

        let allLeads;
        try {
            allLeads = await LeadsDataSource.getLeads();
        } catch (err) {
            console.error('Failed to load leads for search:', err);
            allLeads = [];
        }
        const leads = allLeads.filter(l =>
            l.name.toLowerCase().includes(query) ||
            (l.company || '').toLowerCase().includes(query) ||
            (l.source || '').toLowerCase().includes(query)
        );

        if (contacts.length > 0) {
            this.navigate('contacts');
            this.renderContacts(contacts);
        } else if (leads.length > 0) {
            this.navigate('leads');
            this.renderLeads(leads);
        }
    },

    async renderCurrentPage() {
        if (this.currentPage === 'contacts') await this.renderContacts();
        if (this.currentPage === 'leads') await this.renderLeads();
        if (this.currentPage === 'activities') await this._renderActivitiesView();
    },

    // === Dashboard ===
    async renderDashboard() {
        let contacts;
        try {
            contacts = await ContactsDataSource.getContacts();
        } catch (err) {
            console.error('Failed to load contacts for dashboard:', err);
            contacts = [];
        }
        let leads;
        try {
            leads = await LeadsDataSource.getLeads();
        } catch (err) {
            console.error('Failed to load leads for dashboard:', err);
            leads = [];
        }
        let activities;
        try {
            activities = await ActivitiesDataSource.getActivities();
        } catch (err) {
            console.error('Failed to load activities for dashboard:', err);
            activities = [];
        }
        activities = this._normalizeActivities(activities);
        const today = new Date().toDateString();

        document.getElementById('stat-total-contacts').textContent = contacts.length;
        document.getElementById('stat-total-leads').textContent = leads.length;
        document.getElementById('stat-converted-leads').textContent = leads.filter(l => l.stage === 'won').length;
        document.getElementById('stat-today-activities').textContent = activities.filter(a =>
            new Date(a.date).toDateString() === today
        ).length;

        // Revenue calculations
        const activeLeads = leads.filter(l => l.stage !== 'lost' && l.stage !== 'won');
        const pipelineValue = activeLeads.reduce((sum, l) => sum + (Number(l.value) || 0), 0);
        const wonLeads = leads.filter(l => l.stage === 'won');
        const wonRevenue = wonLeads.reduce((sum, l) => sum + (Number(l.value) || 0), 0);

        document.getElementById('stat-pipeline-value').textContent = this.formatCurrency(pipelineValue);
        document.getElementById('stat-won-revenue').textContent = this.formatCurrency(wonRevenue);

        // Overdue activities
        const overdueCount = await this.getOverdueCount();
        document.getElementById('stat-overdue-activities').textContent = overdueCount;

        // Pipeline counts + per-stage revenue
        const stages = ['new', 'contacted', 'qualified', 'proposal', 'won'];
        stages.forEach(stage => {
            const stageLeads = leads.filter(l => l.stage === stage);
            document.getElementById(`pipeline-${stage}`).textContent = stageLeads.length;
            const stageValue = stageLeads.reduce((sum, l) => sum + (Number(l.value) || 0), 0);
            const valueEl = document.getElementById(`pipeline-${stage}-value`);
            if (valueEl) {
                valueEl.textContent = stageValue > 0 ? this.formatCurrency(stageValue) : '';
            }
        });

        // Recent activities
        const recent = activities.slice(-5).reverse();
        const container = document.getElementById('recent-activities');
        if (recent.length === 0) {
            container.innerHTML = '<p class="empty-state">No recent activities</p>';
        } else {
            container.innerHTML = recent.map(a => `
                <div class="activity-item">
                    <span class="activity-type-icon">${this.getActivityIcon(a.type)}</span>
                    <div class="activity-details">
                        <p>${this.escapeHtml(a.description)}</p>
                        <small>${this.formatDate(a.date)}</small>
                    </div>
                </div>
            `).join('');
        }

        // Recommended Actions (AI-Powered Lead Recommendations)
        this.renderRecommendedActions(leads);

        // Recent Contacts (Item 14)
        this.renderRecentContacts(contacts);

        // Recent Leads (Item 14)
        this.renderRecentLeads(leads);

        // Activity Trends
        this._renderActivityTrends();
        this._bindTrendControls();
    },

    // === AI-Powered Lead Recommendations ===
    async getLeadRecommendations(leads) {
        let activities;
        try {
            activities = await ActivitiesDataSource.getActivities();
        } catch (err) {
            console.error('Failed to load activities for recommendations:', err);
            activities = [];
        }
        activities = this._normalizeActivities(activities);
        const now = new Date();

        // Only active leads (not won or lost)
        const activeLeads = leads.filter(l => l.stage !== 'won' && l.stage !== 'lost');
        if (activeLeads.length === 0) return [];

        // Calculate days since last activity for each lead
        const leadActivityMap = {};
        activities.forEach(a => {
            if (a.leadId) {
                const d = new Date(a.date);
                if (!leadActivityMap[a.leadId] || d > leadActivityMap[a.leadId]) {
                    leadActivityMap[a.leadId] = d;
                }
            }
        });

        // Score each lead for recommendation priority
        const scored = activeLeads.map(lead => {
            const baseScore = this.calculateLeadScore(lead);
            const value = Number(lead.value) || 0;
            const lastActivity = leadActivityMap[lead.id] || new Date(lead.createdAt);
            const daysSinceContact = Math.max(0, Math.floor((now - lastActivity) / 86400000));

            // Recency score: 30 points at day 0, drops to 0 at day 14+
            const recencyScore = Math.max(0, 30 - (daysSinceContact * 30 / 14));
            // Value score: normalize to 0-30 range (max $500k = 30 pts)
            const valueScore = Math.min(30, (value / 500000) * 30);
            // Stale penalty: add urgency for leads not contacted in 7+ days
            const staleBonus = daysSinceContact >= 7 ? 15 : 0;

            const priority = (baseScore * 0.4) + recencyScore + valueScore + staleBonus;

            return { lead, priority, daysSinceContact, value };
        });

        // Sort by priority descending, return top 3
        scored.sort((a, b) => b.priority - a.priority);
        return scored.slice(0, 3);
    },

    async renderRecommendedActions(leads) {
        const recommendations = await this.getLeadRecommendations(leads);
        const container = document.getElementById('recommended-actions');

        if (recommendations.length === 0) {
            container.innerHTML = '<p class="empty-state">No recommendations yet. Add leads to see AI-powered suggestions.</p>';
            return;
        }

        container.innerHTML = recommendations.map(r => {
            const { lead, daysSinceContact, value } = r;
            const score = this.calculateLeadScore(lead);
            const tier = this.getScoreTier(score);
            let suggestion = '';
            let urgency = '';

            if (daysSinceContact >= 7) {
                suggestion = `Follow up — last contacted ${daysSinceContact} days ago`;
                urgency = 'recommendation-urgent';
            } else if (lead.stage === 'new') {
                suggestion = 'Schedule initial outreach';
                urgency = 'recommendation-normal';
            } else if (lead.stage === 'contacted') {
                suggestion = 'Move to qualification stage';
                urgency = 'recommendation-normal';
            } else if (lead.stage === 'qualified') {
                suggestion = 'Prepare proposal';
                urgency = 'recommendation-high';
            } else if (lead.stage === 'proposal') {
                suggestion = 'Follow up on proposal';
                urgency = 'recommendation-urgent';
            } else {
                suggestion = 'Review and advance';
                urgency = 'recommendation-normal';
            }

            return `
                <div class="recommendation-item ${urgency}">
                    <div class="recommendation-header">
                        <span class="recommendation-name" onclick="App.navigate('leads')" style="cursor:pointer">${this.escapeHtml(lead.name)}</span>
                        <span class="score-badge ${tier.class}" title="Score: ${score}/100">${score} ${tier.label}</span>
                    </div>
                    <div class="recommendation-body">
                        <span class="recommendation-suggestion">${suggestion}</span>
                        ${value > 0 ? `<span class="recommendation-value">${this.formatCurrency(value)}</span>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    },

    // === Dashboard Recent Items (Item 14) ===
    renderRecentContacts(contacts) {
        const container = document.getElementById('recent-contacts');
        if (!container) return;

        if (!contacts || contacts.length === 0) {
            container.innerHTML = '<p class="empty-state">No recent contacts</p>';
            return;
        }

        const recent = [...contacts]
            .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
            .slice(0, 5);

        container.innerHTML = recent.map(c => `
            <div class="recent-item" onclick="App.viewContact('${c.id}')" title="Click to view ${this.escapeHtml(c.name)}">
                <span class="recent-item-icon">👤</span>
                <div class="recent-item-details">
                    <div class="recent-item-name">${this.escapeHtml(c.name)}</div>
                    <div class="recent-item-meta">${c.email ? this.escapeHtml(c.email) : (c.company ? this.escapeHtml(c.company) : 'No details')}</div>
                </div>
                <span class="recent-item-time">${this.getRelativeTime(c.createdAt)}</span>
            </div>
        `).join('');
    },

    renderRecentLeads(leads) {
        const container = document.getElementById('recent-leads');
        if (!container) return;

        if (!leads || leads.length === 0) {
            container.innerHTML = '<p class="empty-state">No recent leads</p>';
            return;
        }

        const recent = [...leads]
            .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
            .slice(0, 5);

        container.innerHTML = recent.map(l => `
            <div class="recent-item" onclick="App.editLead('${l.id}')" title="Click to view ${this.escapeHtml(l.name)}">
                <span class="recent-item-icon">🎯</span>
                <div class="recent-item-details">
                    <div class="recent-item-name">${this.escapeHtml(l.name)}</div>
                    <div class="recent-item-meta">${l.company ? this.escapeHtml(l.company) : 'No company'} · <span class="badge badge-${l.stage}">${l.stage}</span></div>
                </div>
                <span class="recent-item-time">${this.getRelativeTime(l.createdAt)}</span>
            </div>
        `).join('');
    },

    getRelativeTime(dateStr) {
        if (!dateStr) return '';
        const now = new Date();
        const date = new Date(dateStr);
        const diffMs = now - date;
        const diffSec = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSec / 60);
        const diffHour = Math.floor(diffMin / 60);
        const diffDay = Math.floor(diffHour / 24);
        const diffWeek = Math.floor(diffDay / 7);
        const diffMonth = Math.floor(diffDay / 30);

        if (diffSec < 60) return 'Just now';
        if (diffMin < 60) return `${diffMin}m ago`;
        if (diffHour < 24) return `${diffHour}h ago`;
        if (diffDay < 7) return `${diffDay}d ago`;
        if (diffWeek < 5) return `${diffWeek}w ago`;
        return `${diffMonth}mo ago`;
    },

    // === Contacts ===
    bindContacts() {
        document.getElementById('btn-add-contact').addEventListener('click', () => {
            this.editId = null;
            this.editType = 'contact';
            this.showContactModal();
        });

        document.getElementById('btn-manage-tags').addEventListener('click', () => {
            this.showManageTagsModal();
        });

        document.getElementById('contact-filter-status').addEventListener('change', () => this.renderContacts());
        document.getElementById('contact-sort').addEventListener('change', () => this.renderContacts());
        document.getElementById('btn-export-csv').addEventListener('click', () => this.exportContactsCSV());
        document.getElementById('btn-import-csv').addEventListener('click', () => {
            document.getElementById('csv-file-input').click();
        });
        document.getElementById('csv-file-input').addEventListener('change', (e) => this.importContactsCSV(e));
        document.getElementById('btn-import-vcard').addEventListener('click', () => {
            document.getElementById('vcard-file-input').click();
        });
        document.getElementById('vcard-file-input').addEventListener('change', (e) => this.importContactsVCard(e));
        document.getElementById('btn-find-duplicates').addEventListener('click', () => this.findDuplicates());
    },

    async renderCompanies(companiesOverride) {
        let companies;
        try {
            companies = companiesOverride || await CompaniesDataSource.getCompanies();
        } catch (err) {
            console.error('Failed to load companies:', err);
            document.getElementById('companies-list').innerHTML =
                `<div class="empty-state-card"><p>⚠️ ${this.escapeHtml(err.message)}</p></div>`;
            return;
        }

        const container = document.getElementById('companies-list');
        if (!companies || companies.length === 0) {
            container.innerHTML = '<div class="empty-state-card"><p>No companies found.</p></div>';
            return;
        }

        const isAdmin = Auth.isAdmin();
        container.innerHTML = companies.map(item => `
            <div class="contact-card" data-company-id="${this.escapeHtml(String(item.id))}">
                <div class="card-header">
                    <div class="card-header-left"><h4>${this.escapeHtml(item.name)}</h4></div>
                    <div class="card-actions">
                        ${isAdmin ? '<button class="card-action-btn" data-action="edit" title="Edit">✏️</button>' : ''}
                        ${isAdmin ? '<button class="card-action-btn" data-action="delete" title="Delete">🗑️</button>' : ''}
                    </div>
                </div>
                <div class="card-body">
                    ${item.website != null && item.website !== '' ? `<p>Website: ${this.escapeHtml(String(item.website))}</p>` : ''}
                    ${item.industry != null && item.industry !== '' ? `<p>Industry: ${this.escapeHtml(String(item.industry))}</p>` : ''}
                    ${item.employeeCount != null && item.employeeCount !== '' ? `<p>Employee Count: ${this.escapeHtml(String(item.employeeCount))}</p>` : ''}
                </div>
                <div class="card-meta">
                    <small class="text-secondary">${this.formatDate(item.createdAt)}</small>
                </div>
            </div>`).join('');
        container.querySelectorAll('.card-action-btn[data-action]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const id = btn.closest('[data-company-id]').getAttribute('data-company-id');
                if (btn.dataset.action === 'edit') { this.editCompany(id); } else { this.deleteCompany(id); }
            });
        });
    },

    showCompanyModal(item) {
        document.getElementById('modal-title').textContent = item ? 'Edit Company' : 'Add Company';
        document.getElementById('modal-body').innerHTML = `
            <form id="company-form">
                <div class="form-group">
                    <label for="company-name">Name *</label>
                    <input type="text" id="company-name" value="${item ? this.escapeHtml(item.name || '') : ''}" required>
                </div>
                <div class="form-group">
                    <label for="company-website">Website</label>
                    <input type="text" id="company-website" value="${item ? this.escapeHtml(item.website || '') : ''}">
                </div>
                <div class="form-group">
                    <label for="company-industry">Industry</label>
                    <input type="text" id="company-industry" value="${item ? this.escapeHtml(item.industry || '') : ''}">
                </div>
                <div class="form-group">
                    <label for="company-employee_count">Employee Count</label>
                    <input type="number" id="company-employee_count" value="${item && item.employeeCount != null ? this.escapeHtml(String(item.employeeCount)) : ''}" step="any">
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="App.closeModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary">${item ? 'Update' : 'Create'}</button>
                </div>
            </form>`;
        document.getElementById('company-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveCompany(item);
        });
        this.openModal();
    },

    async saveCompany(existing) {
        const data = {
            name: document.getElementById('company-name').value.trim(),
            website: document.getElementById('company-website').value.trim(),
            industry: document.getElementById('company-industry').value.trim(),
            employee_count: document.getElementById('company-employee_count').value.trim() === '' ? null : Number(document.getElementById('company-employee_count').value),
        };
        if (!data.name) return;
        try {
            if (existing) {
                await CompaniesDataSource.updateCompany(existing.id, data);
            } else {
                await CompaniesDataSource.createCompany(data);
            }
            this.closeModal();
            await this.renderCompanies();
            this.showNotification(existing ? 'Company updated.' : 'Company created.', 'success');
        } catch (err) {
            console.error('Failed to save company:', err);
            this.closeModal();
            this.showNotification(this._handleApiError(err), 'error');
        }
    },

    async editCompany(id) {
        try {
            const found = (await CompaniesDataSource.getCompanies()).find(x => x.id === id);
            if (found) {
                this.showCompanyModal(found);
            } else {
                this.showNotification('Company not found.', 'error');
            }
        } catch (err) {
            console.error('Failed to load company:', err);
            this.showNotification(this._handleApiError(err), 'error');
        }
    },

    async deleteCompany(id) {
        if (!confirm('Are you sure you want to delete this company?')) return;
        try {
            await CompaniesDataSource.deleteCompany(id);
            await this.renderCompanies();
            this.showNotification('Company deleted.', 'success');
        } catch (err) {
            console.error('Failed to delete company:', err);
            this.showNotification(this._handleApiError(err), 'error');
        }
    },

    async renderContacts(contactsOverride) {
        let contacts;
        try {
            contacts = contactsOverride || await ContactsDataSource.getContacts();
        } catch (err) {
            console.error('Failed to load contacts:', err);
            document.getElementById('contacts-list').innerHTML =
                `<div class="empty-state-card"><p>⚠️ ${this.escapeHtml(err.message)}</p></div>`;
            return;
        }

        const filterStatus = document.getElementById('contact-filter-status').value;
        const sortMode = document.getElementById('contact-sort').value;

        if (filterStatus) {
            contacts = contacts.filter(c => c.status === filterStatus);
        }

        contacts.sort((a, b) => {
            if (sortMode === 'name-asc') return a.name.localeCompare(b.name);
            if (sortMode === 'name-desc') return b.name.localeCompare(a.name);
            return new Date(b.createdAt) - new Date(a.createdAt);
        });

        // Pre-compute duplicate groups for badge display
        let allContacts;
        try {
            allContacts = await ContactsDataSource.getContacts();
        } catch (err) {
            console.error('Failed to load contacts for duplicate check:', err);
            allContacts = contacts;
        }
        const duplicateGroups = this.getDuplicateGroups(allContacts);

        // Pre-compute activity counts per contact
        let activities;
        try {
            activities = await ActivitiesDataSource.getActivities();
            activities = this._normalizeActivities(activities);
        } catch (err) {
            console.error('Failed to load activities for contact counts:', err);
            activities = [];
        }
        const activityCounts = {};
        activities.forEach(a => {
            if (a.contactName) {
                activityCounts[a.contactName] = (activityCounts[a.contactName] || 0) + 1;
            }
        });

        // Store current contact IDs for bulk operations
        this._currentContactIds = contacts.map(c => c.id);

        const container = document.getElementById('contacts-list');
        if (contacts.length === 0) {
            container.innerHTML = '<div class="empty-state-card"><p>No contacts found.</p></div>';
            this.updateBulkActionBar();
            return;
        }

        const isAdmin = Auth.isAdmin();
        container.innerHTML = contacts.map(c => {
            const isDuplicate = duplicateGroups.some(g => g.length > 1 && g.some(d => d.id === c.id));
            const activityCount = activityCounts[c.name] || 0;
            const isSelected = (this._selectedContactIds || new Set()).has(c.id);
            const tagsHtml = (c.tags || []).map(t =>
                `<span class="contact-tag-badge" style="background-color:${t.color || '#3b82f6'}" title="${this.escapeHtml(t.name)}">${this.escapeHtml(t.name)}</span>`
            ).join('');
            return `
            <div class="contact-card${isDuplicate ? ' contact-card-duplicate' : ''}${isSelected ? ' contact-card-selected' : ''}" data-contact-id="${c.id}">
                <div class="card-header">
                    <div class="card-header-left">
                        <input type="checkbox" class="contact-checkbox" data-contact-id="${c.id}" ${isSelected ? 'checked' : ''} title="Select for bulk operations">
                        <h4>${this.escapeHtml(c.name)}</h4>
                    </div>
                    <div class="card-actions">
                        ${isDuplicate ? '<span class="duplicate-badge" title="Duplicate contact detected">⚠️ Duplicate</span>' : ''}
                        <button class="card-action-btn" onclick="App.viewContact('${c.id}')" title="View Details">👁️</button>
                        ${isAdmin ? `<button class="card-action-btn" onclick="App.editContact('${c.id}')" title="Edit">✏️</button>` : ''}
                        ${isAdmin ? `<button class="card-action-btn" onclick="App.deleteContact('${c.id}')" title="Delete">🗑️</button>` : ''}
                    </div>
                </div>
                <div class="card-quick-actions">
                    <button class="quick-activity-btn" onclick="App.quickLogActivity('${this.escapeHtml(c.name)}', 'call')" title="Quick log a call">📞 Call</button>
                    <button class="quick-activity-btn" onclick="App.quickLogActivity('${this.escapeHtml(c.name)}', 'email')" title="Quick log an email">📧 Email</button>
                    <button class="quick-activity-btn" onclick="App.quickLogActivity('${this.escapeHtml(c.name)}', 'meeting')" title="Quick log a meeting">🤝 Meeting</button>
                    <button class="quick-activity-btn" onclick="App.quickLogActivity('${this.escapeHtml(c.name)}', 'note')" title="Quick add a note">📝 Note</button>
                </div>
                <div class="card-body">
                    ${c.email ? `<p>📧 ${this.escapeHtml(c.email)}</p>` : ''}
                    ${c.phone ? `<p>📱 ${this.escapeHtml(c.phone)}</p>` : ''}
                    ${c.company ? `<p>🏢 ${this.escapeHtml(c.company)}</p>` : ''}
                    ${tagsHtml ? `<div class="contact-tags-row">${tagsHtml}</div>` : ''}
                </div>
                <div class="card-meta">
                    <span class="badge badge-${c.status}">${c.status}</span>
                    ${activityCount > 0 ? `<span class="activity-count-badge" title="${activityCount} activit${activityCount === 1 ? 'y' : 'ies'}">📋 ${activityCount}</span>` : ''}
                    <small class="text-secondary">${this.formatDate(c.createdAt)}</small>
                </div>
            </div>
        `}).join('');

        // Bind checkbox events
        container.querySelectorAll('.contact-checkbox').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const contactId = e.target.dataset.contactId;
                if (e.target.checked) {
                    this._selectedContactIds.add(contactId);
                } else {
                    this._selectedContactIds.delete(contactId);
                }
                this.updateBulkActionBar();
                this._highlightSelectedCard(e.target, contactId);
            });
        });

        this.updateBulkActionBar();
    },

    _highlightSelectedCard(checkbox, contactId) {
        const card = checkbox.closest('.contact-card');
        if (card) {
            card.classList.toggle('contact-card-selected', checkbox.checked);
        }
    },

    updateBulkActionBar() {
        const bar = document.getElementById('bulk-action-bar');
        const countEl = document.getElementById('bulk-selection-count');
        const statusBtn = document.getElementById('btn-bulk-status');
        const tagBtn = document.getElementById('btn-bulk-tag');
        const statusSelect = document.getElementById('bulk-status-change');
        const tagSelect = document.getElementById('bulk-tag-select');
        const selectedCount = this._selectedContactIds ? this._selectedContactIds.size : 0;

        if (selectedCount > 0) {
            bar.classList.remove('hidden');
            countEl.textContent = selectedCount;
            statusBtn.disabled = !statusSelect.value;
            tagBtn.disabled = !tagSelect.value;
        } else {
            bar.classList.add('hidden');
        }

        // Populate tag dropdown once tags are loaded
        if (tagSelect.options.length <= 1 && this._allTags && this._allTags.length > 0) {
            this._allTags.forEach(tag => {
                const option = document.createElement('option');
                option.value = tag.id;
                option.textContent = tag.name;
                tagSelect.appendChild(option);
            });
        }
    },

    bindBulkOperations() {
        const bar = document.getElementById('bulk-action-bar');
        if (!bar) return;

        // Select All
        document.getElementById('btn-select-all').addEventListener('click', () => {
            if (!this._selectedContactIds) this._selectedContactIds = new Set();
            (this._currentContactIds || []).forEach(id => this._selectedContactIds.add(id));
            this.renderContacts();
        });

        // Select None
        document.getElementById('btn-select-none').addEventListener('click', () => {
            this._selectedContactIds = new Set();
            this.renderContacts();
        });

        // Status change select enables/disables button
        document.getElementById('bulk-status-change').addEventListener('change', () => {
            const statusBtn = document.getElementById('btn-bulk-status');
            const statusSelect = document.getElementById('bulk-status-change');
            statusBtn.disabled = !statusSelect.value || (this._selectedContactIds && this._selectedContactIds.size === 0);
        });

        // Tag select enables/disables button
        document.getElementById('bulk-tag-select').addEventListener('change', () => {
            const tagBtn = document.getElementById('btn-bulk-tag');
            const tagSelect = document.getElementById('bulk-tag-select');
            tagBtn.disabled = !tagSelect.value || (this._selectedContactIds && this._selectedContactIds.size === 0);
        });

        // Apply bulk status
        document.getElementById('btn-bulk-status').addEventListener('click', () => {
            this.applyBulkStatus();
        });

        // Apply bulk tag
        document.getElementById('btn-bulk-tag').addEventListener('click', () => {
            this.applyBulkTags();
        });

        // Bulk delete
        document.getElementById('btn-bulk-delete').addEventListener('click', () => {
            this.bulkDeleteContacts();
        });
    },

    // === PDF Export (Item 16) ===
    bindPdfExport() {
        const btn = document.getElementById('btn-export-pdf');
        if (!btn) return;
        btn.addEventListener('click', () => {
            this.exportDashboardPdf();
        });
    },

    exportDashboardPdf() {
        // Add print class to body to trigger print-specific CSS
        document.body.classList.add('printing-report');

        // Build a timestamp for the report header
        const now = new Date();
        const timestamp = now.toLocaleString();
        const reportDateEl = document.getElementById('report-generation-date');
        if (reportDateEl) {
            reportDateEl.textContent = 'Generated: ' + timestamp;
        }

        // Trigger browser print dialog
        window.print();

        // Remove print class after print dialog closes
        setTimeout(() => {
            document.body.classList.remove('printing-report');
        }, 500);
    },

    async applyBulkStatus() {
        const statusSelect = document.getElementById('bulk-status-change');
        const newStatus = statusSelect.value;
        if (!newStatus || !this._selectedContactIds || this._selectedContactIds.size === 0) return;

        const ids = Array.from(this._selectedContactIds);
        try {
            const result = await ApiClient.bulkUpdateContactsStatusInApi(ids, newStatus);
            this._selectedContactIds = new Set();
            statusSelect.value = '';
            this.showNotification(result.message || `Status updated for ${ids.length} contact(s)`, 'success');
            await this.renderContacts();
            this.renderDashboard();
        } catch (err) {
            console.error('Bulk status update failed:', err);
            this.showNotification('Failed to update status for some contacts.', 'error');
        }
    },

    async applyBulkTags() {
        const tagSelect = document.getElementById('bulk-tag-select');
        const tagId = tagSelect.value;
        if (!tagId || !this._selectedContactIds || this._selectedContactIds.size === 0) return;

        const ids = Array.from(this._selectedContactIds);
        let successCount = 0;

        for (const id of ids) {
            try {
                const existing = await ContactsDataSource.getContactTags(id);
                const existingIds = (existing || []).map(t => t.id);
                if (!existingIds.includes(tagId)) {
                    existingIds.push(tagId);
                    await ContactsDataSource.setContactTags(id, existingIds);
                }
                successCount++;
            } catch (err) {
                console.error(`Failed to assign tag to contact ${id}:`, err);
            }
        }

        this._selectedContactIds = new Set();
        tagSelect.value = '';
        this.showNotification(`Tag assigned to ${successCount} contact(s)`, 'success');
        await this.renderContacts();
    },

    async bulkDeleteContacts() {
        if (!this._selectedContactIds || this._selectedContactIds.size === 0) return;

        const ids = Array.from(this._selectedContactIds);
        const count = ids.length;
        if (!confirm(`Are you sure you want to delete ${count} contact(s)? This action cannot be undone.`)) return;

        try {
            const result = await ApiClient.bulkDeleteContactsInApi(ids);
            this._selectedContactIds = new Set();
            this.showNotification(result.message || `${count} contact(s) deleted`, 'success');
            await this.renderContacts();
            this.renderDashboard();
        } catch (err) {
            console.error('Bulk delete failed:', err);
            this.showNotification('Failed to delete some contacts.', 'error');
        }
    },

    showContactModal(contact) {
        const title = contact ? 'Edit Contact' : 'Add Contact';
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-body').innerHTML = `
            <form id="contact-form">
                <div class="form-group">
                    <label for="contact-name">Name *</label>
                    <input type="text" id="contact-name" value="${contact ? this.escapeHtml(contact.name) : ''}" required>
                </div>
                <div class="form-group">
                    <label for="contact-email">Email</label>
                    <input type="email" id="contact-email" value="${contact ? this.escapeHtml(contact.email || '') : ''}">
                </div>
                <div class="form-group">
                    <label for="contact-phone">Phone</label>
                    <input type="tel" id="contact-phone" value="${contact ? this.escapeHtml(contact.phone || '') : ''}">
                </div>
                <div class="form-group">
                    <label for="contact-company">Company</label>
                    <input type="text" id="contact-company" value="${contact ? this.escapeHtml(contact.company || '') : ''}">
                </div>
                <div class="form-group">
                    <label for="contact-status">Status</label>
                    <select id="contact-status">
                        <option value="active" ${contact && contact.status === 'active' ? 'selected' : ''}>Active</option>
                        <option value="inactive" ${contact && contact.status === 'inactive' ? 'selected' : ''}>Inactive</option>
                        <option value="vip" ${contact && contact.status === 'vip' ? 'selected' : ''}>VIP</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="contact-notes">Notes</label>
                    <textarea id="contact-notes">${contact ? this.escapeHtml(contact.notes || '') : ''}</textarea>
                </div>
                <div class="form-group" id="contact-tags-group">
                    <label>Tags</label>
                    <div class="contact-tags-selector" id="contact-tags-selector">
                        <span class="text-secondary tags-loading">Loading tags...</span>
                    </div>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="App.closeModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary">${contact ? 'Update' : 'Create'}</button>
                </div>
            </form>
        `;

        document.getElementById('contact-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveContact(contact);
        });

        this.openModal();
        this._populateTagsSelector(contact);
    },

    /**
     * Populate the tags selector in the contact form with checkboxes.
     */
    async _populateTagsSelector(contact) {
        const container = document.getElementById('contact-tags-selector');
        if (!container) return;
        try {
            const tags = await TagsDataSource.getTags();
            const contactTagIds = (contact && contact.tags) ? contact.tags.map(t => t.id) : [];
            if (tags.length === 0) {
                container.innerHTML = `
                    <div class="tags-empty">
                        <span class="text-secondary">No tags yet. </span>
                        <a href="#" onclick="App.showManageTagsModal(); return false;">Create tags</a>
                    </div>`;
                return;
            }
            container.innerHTML = tags.map(t => {
                const checked = contactTagIds.includes(t.id) ? 'checked' : '';
                return `<label class="tag-checkbox-item">
                    <input type="checkbox" class="tag-checkbox" value="${t.id}" ${checked}>
                    <span class="tag-color-dot" style="background-color:${t.color || '#3b82f6'}"></span>
                    ${this.escapeHtml(t.name)}
                </label>`;
            }).join('');
            // Add "manage" link
            container.innerHTML += `<div class="tags-manage-link"><a href="#" onclick="App.showManageTagsModal(); return false;">Manage tags</a></div>`;
        } catch (err) {
            container.innerHTML = '<span class="text-secondary">Could not load tags.</span>';
            console.error('Failed to load tags:', err);
        }
    },

    /**
     * Gather selected tag IDs from the tags selector checkboxes.
     */
    _getSelectedTagIds() {
        const checkboxes = document.querySelectorAll('#contact-tags-selector .tag-checkbox:checked');
        return Array.from(checkboxes).map(cb => cb.value);
    },

    /**
     * View contact detail with activity timeline.
     * Opens a modal showing contact info and all related activities.
     */
    async viewContact(contactId) {
        const contacts = await ContactsDataSource.getContacts();
        const contact = contacts.find(c => c.id === contactId);
        if (!contact) {
            this.showNotification('Contact not found.', 'error');
            return;
        }
        this.showContactDetail(contact);
    },

    /**
     * Show contact detail modal with activity history timeline.
     */
    async showContactDetail(contact) {
        let activities = [];
        try {
            const allActivities = await ActivitiesDataSource.getActivities();
            activities = this._normalizeActivities(allActivities).filter(a => a.contactName === contact.name);
            activities.sort((a, b) => new Date(b.date) - new Date(a.date));
        } catch (err) {
            console.error('Failed to load activities for contact:', err);
        }

        document.getElementById('modal-title').textContent = 'Contact Details';
        document.getElementById('modal-container').classList.add('modal-wide');

        const timelineHtml = this._renderTimelineView(activities);

        document.getElementById('modal-body').innerHTML = `
            <div class="contact-detail-view">
                <div class="contact-detail-header">
                    <div class="contact-detail-info">
                        <h3>${this.escapeHtml(contact.name)}</h3>
                        <span class="badge badge-${contact.status}">${contact.status}</span>
                    </div>
                    <div class="contact-detail-actions">
                        <button class="btn btn-secondary" onclick="App.quickAddActivityForContact('${this.escapeHtml(contact.name)}')">+ Add Activity</button>
                        <button class="btn btn-secondary" onclick="App.closeModal(); App.editContact('${contact.id}')">✏️ Edit</button>
                    </div>
                </div>
                <div class="contact-detail-fields">
                    ${contact.email ? `<div class="detail-field"><span class="field-label">Email</span><span class="field-value">📧 ${this.escapeHtml(contact.email)}</span></div>` : ''}
                    ${contact.phone ? `<div class="detail-field"><span class="field-label">Phone</span><span class="field-value">📱 ${this.escapeHtml(contact.phone)}</span></div>` : ''}
                    ${contact.company ? `<div class="detail-field"><span class="field-label">Company</span><span class="field-value">🏢 ${this.escapeHtml(contact.company)}</span></div>` : ''}
                    ${contact.notes ? `<div class="detail-field"><span class="field-label">Notes</span><span class="field-value">${this.escapeHtml(contact.notes)}</span></div>` : ''}
                    <div class="detail-field"><span class="field-label">Created</span><span class="field-value">${this.formatDate(contact.createdAt)}</span></div>
                </div>
                <div class="contact-activity-timeline">
                    <h4>Activity History <span class="activity-count-label">(${activities.length})</span></h4>
                    <div class="timeline-list">
                        ${timelineHtml}
                    </div>
                </div>
            </div>
        `;

        this.openModal();
    },

    /**
     * Open the activity creation modal with a contact pre-filled.
     */
    quickAddActivityForContact(contactName) {
        this.closeModal();
        setTimeout(() => {
            this.showActivityModal(null, contactName);
        }, 100);
    },

    /**
     * Quick log an activity from a contact card.
     * Opens a compact modal with the contact and type pre-filled.
     */
    quickLogActivity(contactName, type) {
        this.closeModal();
        setTimeout(() => {
            this.showActivityModal(null, type, contactName);
        }, 100);
    },

    async saveContact(existing) {
        const data = {
            name: document.getElementById('contact-name').value.trim(),
            email: document.getElementById('contact-email').value.trim(),
            phone: document.getElementById('contact-phone').value.trim(),
            company: document.getElementById('contact-company').value.trim(),
            status: document.getElementById('contact-status').value,
            notes: document.getElementById('contact-notes').value.trim(),
            tag_ids: this._getSelectedTagIds(),
        };

        if (!data.name) return;

        if (existing) {
            try {
                await ContactsDataSource.updateContact(existing.id, data);
                this.closeModal();
                await this.renderContacts();
                await this.renderDashboard();
                this.showNotification('Contact updated.', 'success');
            } catch (err) {
                console.error('Failed to update contact:', err);
                this.closeModal();
                this.showNotification(this._handleApiError(err), 'error');
            }
        } else {
            // Check for duplicates before saving new contact
            try {
                const allContacts = await ContactsDataSource.getContacts();
                const duplicates = this.findDuplicateContacts(data.name, data.email, data.company, data.phone, null, allContacts);
                if (duplicates.length > 0) {
                    this.showDuplicateWarning(data, duplicates);
                    return;
                }
            } catch (err) {
                console.error('Failed to load contacts for duplicate check:', err);
                // Continue with create — duplicate check is advisory
            }
            try {
                await ContactsDataSource.createContact(data);
                this.closeModal();
                await this.renderContacts();
                await this.renderDashboard();
                this.showNotification('Contact created.', 'success');
            } catch (err) {
                console.error('Failed to create contact:', err);
                this.closeModal();
                this.showNotification(this._handleApiError(err), 'error');
            }
        }
    },

    async editContact(id) {
        try {
            const contacts = await ContactsDataSource.getContacts();
            const contact = contacts.find(c => c.id === id);
            if (contact) {
                this.showContactModal(contact);
            } else {
                this.showNotification('Contact not found.', 'error');
            }
        } catch (err) {
            console.error('Failed to load contact:', err);
            this.showNotification(this._handleApiError(err), 'error');
        }
    },

    async deleteContact(id) {
        if (!confirm('Are you sure you want to delete this contact?')) return;
        try {
            await ContactsDataSource.deleteContact(id);
            await this.renderContacts();
            await this.renderDashboard();
            this.showNotification('Contact deleted.', 'success');
        } catch (err) {
            console.error('Failed to delete contact:', err);
            this.showNotification(this._handleApiError(err), 'error');
        }
    },

    /**
     * Convert an API error into a user-friendly message.
     * Distinguishes between:
     *   - 401: Authentication required (no/invalid token)
     *   - 403: Forbidden (authenticated but insufficient permissions)
     *   - 422: Validation error (bad request data)
     *   - 503: Backend/database unavailable
     *   - 5xx: Internal server error
     *   - network: Backend unreachable
     *   - other: Pass through original message
     */
    _handleApiError(err) {
        if (!err) return 'An unexpected error occurred.';

        // Auth errors — distinguish unauthenticated vs forbidden
        if (err.status === 401) {
            return 'You must sign in to perform this action.';
        }
        if (err.status === 403) {
            return 'You do not have permission to perform this action.';
        }

        // Validation errors
        if (err.status === 422) {
            return err.message || 'The request contained invalid data. Please check your input.';
        }

        // Service unavailable (database down, etc.)
        if (err.status === 503) {
            return 'The service is temporarily unavailable. Please try again later.';
        }

        // Other server errors (5xx)
        if (err.status >= 500) {
            return 'An internal server error occurred. Please try again later.';
        }

        // Network errors (backend unreachable)
        if (err.type === 'network') {
            return 'Cannot reach the backend server. Please check your connection and try again.';
        }

        // Pass through original message for other cases
        return err.message || 'An unexpected error occurred.';
    },

    /**
     * Show or hide the backend-unavailable banner.
     * This is a persistent, non-dismissable banner shown when the backend
     * is unreachable during startup or when multiple requests fail.
     */
    _showBackendUnavailableBanner(show) {
        let banner = document.getElementById('backend-unavailable-banner');

        if (show) {
            if (!banner) {
                banner = document.createElement('div');
                banner.id = 'backend-unavailable-banner';
                banner.className = 'backend-unavailable-banner active';
                banner.innerHTML =
                    '⚠️ Backend server is unreachable. Some features may not work correctly. ' +
                    '<button id="backend-banner-retry-btn" style="margin-left:8px;cursor:pointer;">Retry</button>';
                const mainContent = document.getElementById('main-content');
                if (mainContent) {
                    mainContent.insertBefore(banner, mainContent.firstChild);
                }
                document.getElementById('backend-banner-retry-btn').addEventListener('click', async () => {
                    const healthy = await ApiClient.isHealthy();
                    if (healthy) {
                        banner.remove();
                        this.showNotification('Backend connection restored.', 'success');
                        await this.renderCurrentPage();
                    } else {
                        this.showNotification('Backend is still unreachable.', 'error');
                    }
                });
            }
        } else if (banner) {
            banner.remove();
        }
    },

    // === Duplicate Detection ===

    /**
     * Find contacts that match the given name/email/company.
     * Matches: exact email (case-insensitive) OR same name+company (both non-empty, case-insensitive).
     * excludeId: optional ID to exclude from results (e.g. when editing an existing contact).
     * contacts: optional contacts array; defaults to reading from data source.
     */
    findDuplicateContacts(name, email, company, phone, excludeId, contacts) {
        if (!contacts) {
            // Caller must pass contacts array — don't block the UI with an await here.
            // This function is synchronous; the caller is responsible for providing the data.
            return [];
        }
        const searchEmail = email ? email.toLowerCase().trim() : '';
        const searchName = name ? name.toLowerCase().trim() : '';
        const searchCompany = company ? company.toLowerCase().trim() : '';
        const searchPhone = phone ? phone.replace(/\D/g, '') : '';

        return contacts.filter(c => {
            if (c.id === excludeId) return false;
            const cEmail = c.email ? c.email.toLowerCase().trim() : '';
            const cName = c.name ? c.name.toLowerCase().trim() : '';
            const cCompany = c.company ? c.company.toLowerCase().trim() : '';
            const cPhone = c.phone ? c.phone.replace(/\D/g, '') : '';

            // Exact email match
            if (searchEmail && cEmail === searchEmail) return true;

            // Exact phone match (digits-only comparison)
            if (searchPhone && cPhone && searchPhone === cPhone) return true;

            // Name + company match (both must be non-empty)
            if (searchName && searchCompany && cName === searchName && cCompany === searchCompany) return true;

            return false;
        });
    },

    /**
     * Get all duplicate groups from the contact list.
     * Returns an array of arrays, where each inner array contains contacts that are duplicates of each other.
     */
    getDuplicateGroups(contacts) {
        const groups = [];
        const processed = new Set();

        for (const c of contacts) {
            if (processed.has(c.id)) continue;
            const matches = this.findDuplicateContacts(c.name, c.email, c.company, c.phone, c.id, contacts);
            if (matches.length > 0) {
                groups.push([c, ...matches]);
                processed.add(c.id);
                matches.forEach(m => processed.add(m.id));
            }
        }
        return groups;
    },

    /**
     * Show a warning modal when duplicates are detected during contact creation.
     */
    showDuplicateWarning(newData, duplicates) {
        const duplicateRows = duplicates.map(d => `
            <div class="duplicate-match-card">
                <strong>${this.escapeHtml(d.name)}</strong>
                ${d.email ? `<span>📧 ${this.escapeHtml(d.email)}</span>` : ''}
                ${d.phone ? `<span>📱 ${this.escapeHtml(d.phone)}</span>` : ''}
                ${d.company ? `<span>🏢 ${this.escapeHtml(d.company)}</span>` : ''}
                <div class="duplicate-match-actions">
                    <button class="btn btn-primary btn-sm" onclick="App.mergeWithExisting('${d.id}')">Merge</button>
                </div>
            </div>
        `).join('');

        document.getElementById('modal-title').textContent = '⚠️ Duplicate Contact Detected';
        document.getElementById('modal-body').innerHTML = `
            <p class="text-secondary">A contact with the same email, phone, or name+company already exists:</p>
            ${duplicateRows}
            <div class="form-actions" style="margin-top: 1rem;">
                <button type="button" class="btn btn-secondary" onclick="App.closeModal()">Cancel</button>
                <button type="button" class="btn btn-primary" id="btn-keep-both">Keep Both</button>
            </div>
        `;
        this._pendingContactData = newData;
        this.openModal();
        document.getElementById('btn-keep-both').addEventListener('click', () => this.saveContactAsNew());
    },

    // ── Tag Management ─────────────────────────────────────────────

    /**
     * Open the tag management modal for CRUD operations on tags.
     */
    async showManageTagsModal() {
        let tags = [];
        try {
            tags = await TagsDataSource.getTags();
        } catch (err) {
            console.error('Failed to load tags:', err);
        }

        document.getElementById('modal-title').textContent = 'Manage Tags';
        document.getElementById('modal-container').classList.add('modal-wide');
        document.getElementById('modal-body').innerHTML = `
            <div class="tags-manager">
                <div class="tags-manager-header">
                    <h4>All Tags</h4>
                    <button class="btn btn-sm btn-primary" onclick="App.showCreateTagForm()">+ New Tag</button>
                </div>
                <div id="tags-create-form-container"></div>
                <div id="tags-list-container">
                    ${tags.length === 0 ? '<p class="text-secondary">No tags created yet.</p>' :
                        tags.map(t => `
                        <div class="tag-list-item" data-tag-id="${t.id}">
                            <span class="tag-list-color" style="background-color:${t.color || '#3b82f6'}"></span>
                            <span class="tag-list-name">${this.escapeHtml(t.name)}</span>
                            <div class="tag-list-actions">
                                <button class="btn btn-sm btn-secondary" onclick="App.editTagInline('${t.id}')">Edit</button>
                                <button class="btn btn-sm btn-danger" onclick="App.deleteTagConfirm('${t.id}', '${this.escapeHtml(t.name)}')">Delete</button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
        this.openModal();
    },

    showCreateTagForm() {
        document.getElementById('tags-create-form-container').innerHTML = `
            <form id="tag-create-form" class="tag-create-form">
                <input type="text" id="tag-create-name" placeholder="Tag name *" required maxlength="100">
                <input type="color" id="tag-create-color" value="#3b82f6" title="Tag color">
                <button type="submit" class="btn btn-sm btn-primary">Create</button>
                <button type="button" class="btn btn-sm btn-secondary" onclick="document.getElementById('tags-create-form-container').innerHTML=''">Cancel</button>
            </form>
        `;
        document.getElementById('tag-create-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.createTag();
        });
    },

    async createTag() {
        const name = document.getElementById('tag-create-name').value.trim();
        const color = document.getElementById('tag-create-color').value;
        if (!name) return;
        try {
            await TagsDataSource.createTag(name, color);
            document.getElementById('tags-create-form-container').innerHTML = '';
            this.showNotification(`Tag "${name}" created.`, 'success');
            await this.showManageTagsModal();
        } catch (err) {
            console.error('Failed to create tag:', err);
            this.showNotification('Could not create tag.', 'error');
        }
    },

    async editTagInline(tagId) {
        const newName = prompt('Enter new tag name:');
        if (newName === null) return;
        try {
            await TagsDataSource.updateTag(tagId, { name: newName.trim() });
            this.showNotification('Tag updated.', 'success');
            await this.showManageTagsModal();
        } catch (err) {
            console.error('Failed to update tag:', err);
            this.showNotification('Could not update tag.', 'error');
        }
    },

    async deleteTagConfirm(tagId, tagName) {
        if (!confirm(`Delete tag "${tagName}"? Contacts will lose this tag.`)) return;
        try {
            await TagsDataSource.deleteTag(tagId);
            this.showNotification(`Tag "${tagName}" deleted.`, 'success');
            await this.showManageTagsModal();
        } catch (err) {
            console.error('Failed to delete tag:', err);
            this.showNotification('Could not delete tag.', 'error');
        }
    },

    /**
     * Save the pending contact as a new record (user chose "Keep Both").
     */
    async saveContactAsNew() {
        const data = this._pendingContactData;
        if (!data) return;
        try {
            await ContactsDataSource.createContact(data);
            delete this._pendingContactData;
            this.closeModal();
            await this.renderContacts();
            await this.renderDashboard();
            this.showNotification('Contact created (duplicate kept).', 'info');
        } catch (err) {
            console.error('Failed to create contact:', err);
            this.showNotification(err.message, 'error');
        }
    },

    /**
     * Merge the pending new contact data into an existing contact.
     */
    async mergeWithExisting(keepId) {
        const newData = this._pendingContactData;
        if (!newData) return;

        // Merge: update existing contact with new data where new fields are non-empty
        const updatePayload = {};
        for (const key of ['name', 'email', 'phone', 'company', 'status', 'notes']) {
            if (newData[key]) {
                updatePayload[key] = newData[key];
            }
        }

        try {
            // Get existing contact for notes merging
            const contacts = await ContactsDataSource.getContacts();
            const existing = contacts.find(c => c.id === keepId);
            if (!existing) {
                this.showNotification('Target contact not found.', 'error');
                return;
            }

            // Combine notes if both exist
            if (newData.notes && existing.notes) {
                updatePayload.notes = existing.notes + '\n---\n' + newData.notes;
            }

            await ContactsDataSource.updateContact(keepId, updatePayload);
            delete this._pendingContactData;
            this.closeModal();
            await this.renderContacts();
            await this.renderDashboard();
            this.showNotification(`Merged into "${newData.name}".`, 'success');
        } catch (err) {
            console.error('Failed to merge contact:', err);
            this.showNotification(err.message, 'error');
        }
    },

    /**
     * Scan all contacts for duplicates and show results.
     * Uses the backend API for server-side duplicate detection with phone matching.
     */
    async findDuplicates() {
        let result;
        try {
            result = await ApiClient.findDuplicateContactsInApi();
        } catch (err) {
            console.error('Failed to find duplicates via API:', err);
            this.showNotification(this._handleApiError(err), 'error');
            return;
        }

        const groups = result.groups || [];

        if (groups.length === 0) {
            this.showNotification('No duplicate contacts found.', 'info');
            return;
        }

        const totalDuplicates = result.totalDuplicates || groups.reduce((sum, g) => sum + g.contacts.length, 0);
        const matchTypeLabels = { email: '📧 Email', phone: '📱 Phone', name_company: '👤 Name + Company' };

        const groupRows = groups.map((group, gi) => {
            const matchLabel = matchTypeLabels[group.matchType] || group.matchType;
            return `
            <div class="duplicate-group">
                <h4>Group ${gi + 1} — ${matchLabel} match (${group.contacts.length} contacts)</h4>
                ${group.contacts.map((c, ci) => `
                    <div class="duplicate-match-card">
                        <strong>${this.escapeHtml(c.name)}</strong>
                        ${c.email ? `<span>📧 ${this.escapeHtml(c.email)}</span>` : ''}
                        ${c.phone ? `<span>📱 ${this.escapeHtml(c.phone)}</span>` : ''}
                        ${c.company ? `<span>🏢 ${this.escapeHtml(c.company)}</span>` : ''}
                        <span class="text-secondary">${this.formatDate(c.createdAt || c.created_at)}</span>
                        ${ci < group.contacts.length - 1 ? `<div class="duplicate-match-actions">
                            <button class="btn btn-primary btn-sm" onclick="App.mergeContacts('${group.contacts[0].id}', '${c.id}')">Merge into first</button>
                        </div>` : '<div class="text-secondary"><em>Keep</em></div>'}
                    </div>
                `).join('')}
            </div>
        `;
        }).join('');

        document.getElementById('modal-title').textContent = `🔍 Duplicate Contacts Found`;
        document.getElementById('modal-body').innerHTML = `
            <p class="text-secondary">${totalDuplicates} contacts in ${groups.length} group(s) appear to be duplicates:</p>
            ${groupRows}
            <div class="form-actions" style="margin-top: 1rem;">
                <button type="button" class="btn btn-secondary" onclick="App.closeModal()">Close</button>
            </div>
        `;
        this.openModal();
    },

    /**
     * Merge two contacts: keep keepId, remove removeId, combine notes, transfer activities.
     */
    async mergeContacts(keepId, removeId) {
        if (!confirm('Merge the second contact into the first? The second contact will be deleted.')) return;

        try {
            const contacts = await ContactsDataSource.getContacts();
            const keepIdx = contacts.findIndex(c => c.id === keepId);
            const removeIdx = contacts.findIndex(c => c.id === removeId);
            if (keepIdx === -1 || removeIdx === -1) {
                this.showNotification('One or both contacts not found.', 'error');
                return;
            }

            const keep = contacts[keepIdx];
            const remove = contacts[removeIdx];

            // Combine notes
            if (remove.notes) {
                keep.notes = keep.notes
                    ? keep.notes + '\n---\n' + remove.notes
                    : remove.notes;
            }

            // Update kept contact with combined data
            await ContactsDataSource.updateContact(keepId, keep);
            // Delete removed contact
            await ContactsDataSource.deleteContact(removeId);

            // Transfer activities from removed contact to kept contact
            const activities = await ActivitiesDataSource.getActivities();
            activities.forEach(a => {
                if (a.contactName === remove.name) {
                    a.contactName = keep.name;
                }
            });
            // Update each changed activity via backend
            for (const a of activities) {
                if (a.contactName === keep.name) {
                    await ActivitiesDataSource.updateActivity(a.id, { contactName: keep.name });
                }
            }

            this.closeModal();
            await this.renderContacts();
            await this.renderDashboard();
            this.showNotification(`Merged "${remove.name}" into "${keep.name}".`, 'success');
        } catch (err) {
            console.error('Failed to merge contacts:', err);
            this.showNotification(err.message, 'error');
        }
    },

    // === CSV Import/Export ===
    async exportContactsCSV() {
        let contacts;
        try {
            contacts = await ContactsDataSource.getContacts();
        } catch (err) {
            console.error('Failed to load contacts for export:', err);
            this.showNotification(err.message, 'error');
            return;
        }
        if (contacts.length === 0) {
            this.showNotification('No contacts to export.', 'error');
            return;
        }

        const headers = ['Name', 'Email', 'Phone', 'Company', 'Status', 'Notes'];
        const rows = contacts.map(c => [
            `"${(c.name || '').replace(/"/g, '""')}"`,
            `"${(c.email || '').replace(/"/g, '""')}"`,
            `"${(c.phone || '').replace(/"/g, '""')}"`,
            `"${(c.company || '').replace(/"/g, '""')}"`,
            `"${(c.status || 'active').replace(/"/g, '""')}"`,
            `"${(c.notes || '').replace(/"/g, '""')}"`
        ]);

        const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `contacts_${new Date().toISOString().slice(0, 10)}.csv`;
        link.click();
        URL.revokeObjectURL(url);
        this.showNotification(`Exported ${contacts.length} contacts to CSV.`, 'success');
    },

    async importContactsCSV(event) {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async (e) => {
            try {
                const text = e.target.result;
                const lines = text.split('\n').filter(l => l.trim());
                if (lines.length < 2) {
                    this.showNotification('CSV file is empty or has no data rows.', 'error');
                    event.target.value = '';
                    return;
                }

                let imported = 0;
                let skipped = 0;

                for (let i = 1; i < lines.length; i++) {
                    const values = this.parseCSVLine(lines[i]);
                    if (values.length < 2 || !values[0]) {
                        skipped++;
                        continue;
                    }

                    const contact = {
                        name: values[0] || '',
                        email: values[1] || '',
                        phone: values[2] || '',
                        company: values[3] || '',
                        status: values[4] || 'active',
                        notes: values[5] || ''
                    };

                    if (contact.name) {
                        try {
                            await ContactsDataSource.createContact(contact);
                            imported++;
                        } catch (err) {
                            console.error(`Failed to import contact "${contact.name}":`, err);
                            skipped++;
                        }
                    } else {
                        skipped++;
                    }
                }

                await this.renderContacts();
                await this.renderDashboard();
                this.showNotification(
                    `Imported ${imported} contacts${skipped > 0 ? ` (${skipped} skipped)` : ''}.`,
                    skipped > imported ? 'error' : 'success'
                );
            } catch (err) {
                this.showNotification('Error parsing CSV: ' + err.message, 'error');
            }
            event.target.value = '';
        };
        reader.readAsText(file);
    },

    // === vCard Import ===
    async importContactsVCard(event) {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async (e) => {
            try {
                const text = e.target.result;
                const vcards = this.parseVCard(text);
                if (vcards.length === 0) {
                    this.showNotification('No valid vCard records found in file.', 'error');
                    event.target.value = '';
                    return;
                }

                let imported = 0;
                let skipped = 0;

                for (const contact of vcards) {
                    if (!contact.name || contact.name.trim() === '') {
                        skipped++;
                        continue;
                    }
                    try {
                        await ContactsDataSource.createContact(contact);
                        imported++;
                    } catch (err) {
                        console.error(`Failed to import vCard contact "${contact.name}":`, err);
                        skipped++;
                    }
                }

                await this.renderContacts();
                await this.renderDashboard();
                this.showNotification(
                    `Imported ${imported} contact(s) from vCard${skipped > 0 ? ` (${skipped} skipped)` : ''}.`,
                    skipped > imported ? 'error' : 'success'
                );
            } catch (err) {
                this.showNotification('Error parsing vCard: ' + err.message, 'error');
            }
            event.target.value = '';
        };
        reader.readAsText(file);
    },

    parseVCard(text) {
        const contacts = [];
        const lines = text.split(/\r?\n/);
        let current = null;

        for (let i = 0; i < lines.length; i++) {
            let line = lines[i];
            // Handle line folding (lines starting with space/continuation)
            if (line.startsWith(' ') || line.startsWith('\t')) {
                if (current) {
                    const lastKey = Object.keys(current._raw).pop();
                    if (lastKey) {
                        current._raw[lastKey] += line.trim();
                    }
                }
                continue;
            }

            if (line.trim() === 'BEGIN:VCARD') {
                current = { _raw: {}, _phones: [], _emails: [], _notes: [] };
                continue;
            }

            if (line.trim() === 'END:VCARD') {
                if (current) {
                    const name = this._extractVCardName(current._raw);
                    const email = current._emails[0] || '';
                    const phone = current._phones[0] || '';
                    const company = current._raw['ORG'] || '';
                    let notes = current._notes.join(' ').trim();
                    const title = current._raw['TITLE'] || '';
                    const status = 'active';

                    if (notes && title) {
                        notes = `Title: ${title}\n${notes}`;
                    } else if (title) {
                        notes = `Title: ${title}`;
                    }

                    contacts.push({
                        name: name || 'Unknown',
                        email: email,
                        phone: phone,
                        company: company,
                        status: status,
                        notes: notes
                    });
                }
                current = null;
                continue;
            }

            if (current) {
                const colonIdx = line.indexOf(':');
                if (colonIdx === -1) continue;

                let value = line.substring(colonIdx + 1);
                let paramStr = line.substring(0, colonIdx);
                let key = paramStr;
                const semiIdx = paramStr.indexOf(';');
                if (semiIdx !== -1) {
                    key = paramStr.substring(0, semiIdx);
                }

                key = key.toUpperCase();
                value = value.replace(/\\n/g, '\n').replace(/\\,/g, ',').replace(/\\;/g, ';').replace(/\\\\/g, '\\').trim();

                if (key === 'TEL' || key.startsWith('TEL')) {
                    current._phones.push(value);
                } else if (key === 'EMAIL' || key.startsWith('EMAIL')) {
                    current._emails.push(value);
                } else if (key === 'NOTE' || key.startsWith('NOTE')) {
                    current._notes.push(value);
                } else if (!key.includes(';') || key === 'N' || key === 'FN' || key === 'ORG' || key === 'TITLE' || key === 'URL') {
                    current._raw[key] = value;
                }
            }
        }

        return contacts;
    },

    _extractVCardName(raw) {
        if (raw['FN']) return raw['FN'];
        if (raw['N']) {
            const parts = raw['N'].split(';').filter(p => p.trim());
            return parts.join(' ').trim();
        }
        return '';
    },

    // === Lead CSV Export/Import ===
    async exportLeadsCSV() {
        let leads;
        try {
            leads = await LeadsDataSource.getLeads();
        } catch (err) {
            console.error('Failed to load leads for export:', err);
            this.showNotification('Failed to load leads from server.', 'error');
            return;
        }
        if (leads.length === 0) {
            this.showNotification('No leads to export.', 'error');
            return;
        }

        const headers = ['Name', 'Company', 'Email', 'Phone', 'Value', 'Stage', 'Source', 'Notes'];
        const rows = leads.map(l => [
            `"${(l.name || '').replace(/"/g, '""')}"`,
            `"${(l.company || '').replace(/"/g, '""')}"`,
            `"${(l.email || '').replace(/"/g, '""')}"`,
            `"${(l.phone || '').replace(/"/g, '""')}"`,
            `"${String(l.value || '').replace(/"/g, '""')}"`,
            `"${(l.stage || 'new').replace(/"/g, '""')}"`,
            `"${(l.source || '').replace(/"/g, '""')}"`,
            `"${(l.notes || '').replace(/"/g, '""')}"`
        ]);

        const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `leads_${new Date().toISOString().slice(0, 10)}.csv`;
        link.click();
        URL.revokeObjectURL(url);
        this.showNotification(`Exported ${leads.length} leads to CSV.`, 'success');
    },

    async importLeadsCSV(event) {
        const file = event.target.files[0];
        if (!file) return;

        const validStages = ['new', 'contacted', 'qualified', 'proposal', 'won', 'lost'];
        const validSources = ['website', 'referral', 'social media', 'cold call', 'event'];

        const reader = new FileReader();
        reader.onload = async (e) => {
            try {
                const text = e.target.result;
                const lines = text.split('\n').filter(l => l.trim());
                if (lines.length < 2) {
                    this.showNotification('CSV file is empty or has no data rows.', 'error');
                    event.target.value = '';
                    return;
                }

                let imported = 0;
                let skipped = 0;

                for (let i = 1; i < lines.length; i++) {
                    const values = this.parseCSVLine(lines[i]);
                    if (values.length < 2 || !values[0]) {
                        skipped++;
                        continue;
                    }

                    const stage = (values[5] || 'new').toLowerCase();
                    const source = (values[6] || '').toLowerCase();

                    const leadData = {
                        name: values[0] || '',
                        company: values[1] || '',
                        email: values[2] || '',
                        phone: values[3] || '',
                        value: Number(values[4]) || 0,
                        stage: validStages.includes(stage) ? stage : 'new',
                        source: validSources.includes(source) ? source : '',
                        notes: values[7] || '',
                    };

                    if (leadData.name) {
                        try {
                            await LeadsDataSource.createLead(leadData);
                            imported++;
                        } catch (err) {
                            console.error('Failed to import lead:', err);
                            skipped++;
                        }
                    } else {
                        skipped++;
                    }
                }

                await this.renderLeads();
                await this.renderDashboard();
                this.showNotification(
                    `Imported ${imported} leads${skipped > 0 ? ` (${skipped} skipped)` : ''}.`,
                    'success'
                );
            } catch (err) {
                this.showNotification('Error parsing CSV: ' + err.message, 'error');
            }
            event.target.value = '';
        };
        reader.readAsText(file);
    },

    parseCSVLine(line) {
        const result = [];
        let current = '';
        let inQuotes = false;

        for (let i = 0; i < line.length; i++) {
            const char = line[i];
            if (inQuotes) {
                if (char === '"') {
                    if (i + 1 < line.length && line[i + 1] === '"') {
                        current += '"';
                        i++;
                    } else {
                        inQuotes = false;
                    }
                } else {
                    current += char;
                }
            } else {
                if (char === '"') {
                    inQuotes = true;
                } else if (char === ',') {
                    result.push(current.trim());
                    current = '';
                } else {
                    current += char;
                }
            }
        }
        result.push(current.trim());
        return result;
    },

    showNotification(message, type) {
        const container = document.getElementById('notification-container');
        const notif = document.createElement('div');
        notif.className = `notification notification-${type || 'info'}`;
        notif.textContent = message;
        container.appendChild(notif);
        setTimeout(() => {
            notif.classList.add('fade-out');
            setTimeout(() => notif.remove(), 300);
        }, 3000);
    },

    // === Lead Scoring ===
    calculateLeadScore(lead) {
        let score = 0;
        const rules = this.getScoringRules();

        // Source scoring
        if (lead.source) {
            score += rules.source[lead.source] || 0;
        }

        // Stage scoring
        if (lead.stage) {
            score += rules.stage[lead.stage] || 0;
        }

        // Value scoring
        const value = Number(lead.value) || 0;
        if (value >= rules.valueThresholds[3]) score += rules.valueScores[3];
        else if (value >= rules.valueThresholds[2]) score += rules.valueScores[2];
        else if (value >= rules.valueThresholds[1]) score += rules.valueScores[1];
        else if (value > 0) score += rules.valueScores[0];

        // Engagement scoring (has contact info)
        if (lead.email) score += rules.engagement.email;
        if (lead.phone) score += rules.engagement.phone;
        if (lead.company) score += rules.engagement.company;
        if (lead.notes) score += rules.engagement.notes;

        return Math.min(score, 100);
    },

    getScoringRules() {
        return {
            source: { 'website': 5, 'referral': 15, 'social': 10, 'cold-call': 5, 'event': 10 },
            stage: { 'new': 0, 'contacted': 10, 'qualified': 25, 'proposal': 40, 'won': 50, 'lost': 0 },
            valueThresholds: [10000, 50000, 100000, 500000],
            valueScores: [5, 15, 25, 35],
            engagement: { email: 5, phone: 5, company: 10, notes: 5 }
        };
    },

    getScoreTier(score) {
        if (score >= 70) return { label: 'Critical', class: 'score-critical' };
        if (score >= 45) return { label: 'Hot', class: 'score-hot' };
        if (score >= 25) return { label: 'Warm', class: 'score-warm' };
        return { label: 'Cold', class: 'score-cold' };
    },

    // === Leads ===
    bindLeads() {
        document.getElementById('btn-add-lead').addEventListener('click', () => {
            this.editId = null;
            this.editType = 'lead';
            this.showLeadModal();
        });

        document.getElementById('btn-toggle-kanban').addEventListener('click', () => this.toggleKanbanView());
        document.getElementById('lead-filter-stage').addEventListener('change', () => {
            if (this._isKanbanView) {
                this.renderKanbanBoard();
            } else {
                this.renderLeads();
            }
        });
        document.getElementById('lead-sort').addEventListener('change', () => {
            if (this._isKanbanView) {
                this.renderKanbanBoard();
            } else {
                this.renderLeads();
            }
        });
        document.getElementById('lead-filter-score').addEventListener('change', () => {
            if (this._isKanbanView) {
                this.renderKanbanBoard();
            } else {
                this.renderLeads();
            }
        });
        document.getElementById('btn-export-leads-csv').addEventListener('click', () => this.exportLeadsCSV());
        document.getElementById('btn-import-leads-csv').addEventListener('click', () => {
            document.getElementById('leads-csv-file-input').click();
        });
        document.getElementById('leads-csv-file-input').addEventListener('change', (e) => this.importLeadsCSV(e));
    },

    async renderLeads(leadsOverride) {
        let leads;
        if (leadsOverride) {
            leads = leadsOverride;
        } else {
            try {
                leads = await LeadsDataSource.getLeads();
            } catch (err) {
                console.error('Failed to load leads:', err);
                document.getElementById('leads-list').innerHTML =
                    `<div class="empty-state-card"><p>⚠️ ${this.escapeHtml(err.message)}</p></div>`;
                return;
            }
        }
        const filterStage = document.getElementById('lead-filter-stage').value;
        const filterScore = document.getElementById('lead-filter-score').value;
        const sortMode = document.getElementById('lead-sort').value;

        if (filterStage) {
            leads = leads.filter(l => l.stage === filterStage);
        }

        if (filterScore) {
            leads = leads.filter(l => {
                const score = this.calculateLeadScore(l);
                const tier = this.getScoreTier(score);
                return tier.label.toLowerCase() === filterScore;
            });
        }

        leads.sort((a, b) => {
            if (sortMode === 'value-desc') return (b.value || 0) - (a.value || 0);
            if (sortMode === 'value-asc') return (a.value || 0) - (b.value || 0);
            if (sortMode === 'score-desc') return this.calculateLeadScore(b) - this.calculateLeadScore(a);
            return new Date(b.createdAt) - new Date(a.createdAt);
        });

        const container = document.getElementById('leads-list');
        if (leads.length === 0) {
            container.innerHTML = '<div class="empty-state-card"><p>No leads found.</p></div>';
            return;
        }

        container.innerHTML = leads.map(l => {
            const score = this.calculateLeadScore(l);
            const tier = this.getScoreTier(score);
            return `
            <div class="lead-card">
                <div class="card-header">
                    <h4>${this.escapeHtml(l.name)}</h4>
                    <div class="card-actions">
                        <button class="card-action-btn" onclick="App.editLead('${l.id}')" title="Edit">✏️</button>
                        <button class="card-action-btn" onclick="App.deleteLead('${l.id}')" title="Delete">🗑️</button>
                    </div>
                </div>
                <div class="card-body">
                    ${l.company ? `<p>🏢 ${this.escapeHtml(l.company)}</p>` : ''}
                    ${l.email ? `<p>📧 ${this.escapeHtml(l.email)}</p>` : ''}
                    ${l.value ? `<p class="lead-value">$${Number(l.value).toLocaleString()}</p>` : ''}
                </div>
                <div class="card-meta">
                    <span class="badge badge-${l.stage}">${l.stage}</span>
                    <span class="score-badge ${tier.class}" title="Score: ${score}/100">${score} ${tier.label}</span>
                    <small class="text-secondary">${this.formatDate(l.createdAt)}</small>
                </div>
            </div>
        `;}).join('');
    },

    // === Kanban Board View ===

    _isKanbanView: false,

    _KANBAN_STAGES: ['new', 'contacted', 'qualified', 'proposal', 'won', 'lost'],

    toggleKanbanView() {
        this._isKanbanView = !this._isKanbanView;
        const grid = document.getElementById('leads-list');
        const board = document.getElementById('kanban-board');
        const btn = document.getElementById('btn-toggle-kanban');

        if (this._isKanbanView) {
            grid.style.display = 'none';
            board.style.display = 'flex';
            btn.textContent = '📋 Grid';
            btn.title = 'Toggle Grid View (K)';
            this.renderKanbanBoard();
        } else {
            grid.style.display = '';
            board.style.display = 'none';
            btn.textContent = '📊 Kanban';
            btn.title = 'Toggle Kanban Board View (K)';
        }
    },

    async renderKanbanBoard(leadsOverride) {
        let leads;
        if (leadsOverride) {
            leads = leadsOverride;
        } else {
            try {
                leads = await LeadsDataSource.getLeads();
            } catch (err) {
                console.error('Failed to load leads for Kanban:', err);
                return;
            }
        }

        const filterStage = document.getElementById('lead-filter-stage').value;
        const filterScore = document.getElementById('lead-filter-score').value;

        if (filterStage) {
            leads = leads.filter(l => l.stage === filterStage);
        }
        if (filterScore) {
            leads = leads.filter(l => {
                const score = this.calculateLeadScore(l);
                const tier = this.getScoreTier(score);
                return tier.label.toLowerCase() === filterScore;
            });
        }

        for (const stage of this._KANBAN_STAGES) {
            const container = document.querySelector(`.kanban-cards[data-stage="${stage}"]`);
            const column = container.closest('.kanban-column');
            const stageLeads = leads.filter(l => l.stage === stage);
            const totalValue = stageLeads.reduce((s, l) => s + (Number(l.value) || 0), 0);

            column.querySelector('.kanban-count').textContent = stageLeads.length;
            column.querySelector('.kanban-value').textContent = totalValue > 0 ? `$${totalValue.toLocaleString()}` : '$0';

            container.innerHTML = stageLeads.map(l => this._renderKanbanCard(l)).join('');
        }

        this._bindKanbanDragDrop();
    },

    _renderKanbanCard(l) {
        const score = this.calculateLeadScore(l);
        const tier = this.getScoreTier(score);
        const daysInStage = this._getDaysInStage(l);
        const ageClass = daysInStage > 14 ? 'age-red' : daysInStage > 7 ? 'age-amber' : 'age-green';

        const stageOptions = this._KANBAN_STAGES.map(s =>
            `<option value="${s}" ${s === l.stage ? 'selected' : ''}>${s.charAt(0).toUpperCase() + s.slice(1)}</option>`
        ).join('');

        return `
            <div class="kanban-card" draggable="true" data-lead-id="${l.id}" data-lead-stage="${l.stage}">
                <p class="kanban-card-name">${this.escapeHtml(l.name)}</p>
                ${l.company ? `<p class="kanban-card-company">${this.escapeHtml(l.company)}</p>` : ''}
                ${l.value ? `<p class="kanban-card-value">$${Number(l.value).toLocaleString()}</p>` : ''}
                <div class="kanban-card-footer">
                    <span class="kanban-card-score ${tier.class}" title="Score: ${score}/100">${score}</span>
                    <span class="kanban-card-age ${ageClass}">${daysInStage}d</span>
                    <select class="kanban-card-stage-select" data-lead-id="${l.id}" title="Change stage">${stageOptions}</select>
                    <div class="kanban-card-actions">
                        <button class="kanban-card-action" onclick="App.editLead('${l.id}')" title="Edit">✏️</button>
                        <button class="kanban-card-action" onclick="App.deleteLead('${l.id}')" title="Delete">🗑️</button>
                    </div>
                </div>
            </div>
        `;
    },

    _getDaysInStage(lead) {
        const stage = lead.stage;
        const created = new Date(lead.createdAt);
        const updated = lead.updatedAt ? new Date(lead.updatedAt) : created;
        const now = new Date();
        const diffMs = now - updated;
        return Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
    },

    _bindKanbanDragDrop() {
        const cards = document.querySelectorAll('.kanban-card');
        const dropZones = document.querySelectorAll('.kanban-cards');

        cards.forEach(card => {
            card.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData('text/plain', card.dataset.leadId);
                e.dataTransfer.effectAllowed = 'move';
                card.classList.add('dragging');
            });
            card.addEventListener('dragend', () => {
                card.classList.remove('dragging');
                document.querySelectorAll('.kanban-column.drag-over').forEach(c => c.classList.remove('drag-over'));
            });
        });

        dropZones.forEach(zone => {
            zone.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                zone.closest('.kanban-column').classList.add('drag-over');
            });
            zone.addEventListener('dragleave', (e) => {
                if (!zone.contains(e.relatedTarget)) {
                    zone.closest('.kanban-column').classList.remove('drag-over');
                }
            });
            zone.addEventListener('drop', async (e) => {
                e.preventDefault();
                zone.closest('.kanban-column').classList.remove('drag-over');
                const leadId = e.dataTransfer.getData('text/plain');
                const newStage = zone.dataset.stage;
                const card = document.querySelector(`.kanban-card[data-lead-id="${leadId}"]`);
                if (!card) return;

                const currentStage = card.dataset.leadStage;
                if (currentStage === newStage) return;

                if (newStage === 'won' || newStage === 'lost') {
                    const proceeded = await this._promptWinLossReason(
                        leadId, card.querySelector('.kanban-card-name').textContent, newStage
                    );
                    if (!proceeded) return;
                    // If the user skipped the reason, just proceed with the stage change
                    card.style.opacity = '0.5';
                    try {
                        await ApiClient.updateLeadStageInApi(leadId, newStage);
                        card.dataset.leadStage = newStage;
                        this.renderKanbanBoard();
                        this.showNotification(`Lead moved to ${newStage}`, 'success');
                    } catch (err) {
                        card.style.opacity = '1';
                        console.error('Failed to update lead stage:', err);
                        this.showNotification('Failed to update lead stage', 'error');
                    }
                    return;
                }

                card.style.opacity = '0.5';
                try {
                    await ApiClient.updateLeadStageInApi(leadId, newStage);
                    card.dataset.leadStage = newStage;
                    this.renderKanbanBoard();
                    this.showNotification(`Lead moved to ${newStage}`, 'success');
                } catch (err) {
                    card.style.opacity = '1';
                    console.error('Failed to update lead stage:', err);
                    this.showNotification('Failed to update lead stage', 'error');
                }
            });
        });

        const stageSelects = document.querySelectorAll('.kanban-card-stage-select');
        stageSelects.forEach(select => {
            select.addEventListener('change', async (e) => {
                const leadId = e.target.dataset.leadId;
                const newStage = e.target.value;
                const card = e.target.closest('.kanban-card');

                if (card.dataset.leadStage === newStage) return;

                if (newStage === 'won' || newStage === 'lost') {
                    const leadName = card.querySelector('.kanban-card-name').textContent;
                    const proceeded = await this._promptWinLossReason(leadId, leadName, newStage);
                    if (!proceeded) {
                        this.renderKanbanBoard();
                        return;
                    }
                    try {
                        await ApiClient.updateLeadStageInApi(leadId, newStage);
                        this.renderKanbanBoard();
                        this.showNotification(`Lead moved to ${newStage}`, 'success');
                    } catch (err) {
                        this.renderKanbanBoard();
                        console.error('Failed to update lead stage:', err);
                        this.showNotification('Failed to update lead stage', 'error');
                    }
                    return;
                }

                try {
                    await ApiClient.updateLeadStageInApi(leadId, newStage);
                    this.renderKanbanBoard();
                    this.showNotification(`Lead moved to ${newStage}`, 'success');
                } catch (err) {
                    this.renderKanbanBoard();
                    console.error('Failed to update lead stage:', err);
                    this.showNotification('Failed to update lead stage', 'error');
                }
            });
        });
    },

    showLeadModal(lead) {
        document.getElementById('modal-title').textContent = lead ? 'Edit Lead' : 'Add Lead';
        document.getElementById('modal-body').innerHTML = `
            <form id="lead-form">
                <div class="form-group">
                    <label for="lead-name">Name *</label>
                    <input type="text" id="lead-name" value="${lead ? this.escapeHtml(lead.name) : ''}" required>
                </div>
                <div class="form-group">
                    <label for="lead-company">Company</label>
                    <input type="text" id="lead-company" value="${lead ? this.escapeHtml(lead.company || '') : ''}">
                </div>
                <div class="form-group">
                    <label for="lead-email">Email</label>
                    <input type="email" id="lead-email" value="${lead ? this.escapeHtml(lead.email || '') : ''}">
                </div>
                <div class="form-group">
                    <label for="lead-phone">Phone</label>
                    <input type="tel" id="lead-phone" value="${lead ? this.escapeHtml(lead.phone || '') : ''}">
                </div>
                <div class="form-group">
                    <label for="lead-value">Estimated Value ($)</label>
                    <input type="number" id="lead-value" min="0" step="100" value="${lead ? (lead.value || '') : ''}">
                </div>
                <div class="form-group">
                    <label for="lead-stage">Stage</label>
                    <select id="lead-stage">
                        <option value="new" ${lead && lead.stage === 'new' ? 'selected' : ''}>New</option>
                        <option value="contacted" ${lead && lead.stage === 'contacted' ? 'selected' : ''}>Contacted</option>
                        <option value="qualified" ${lead && lead.stage === 'qualified' ? 'selected' : ''}>Qualified</option>
                        <option value="proposal" ${lead && lead.stage === 'proposal' ? 'selected' : ''}>Proposal</option>
                        <option value="won" ${lead && lead.stage === 'won' ? 'selected' : ''}>Won</option>
                        <option value="lost" ${lead && lead.stage === 'lost' ? 'selected' : ''}>Lost</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="lead-source">Source</label>
                    <select id="lead-source">
                        <option value="" ${lead && !lead.source ? 'selected' : ''}>Select source</option>
                        <option value="website" ${lead && lead.source === 'website' ? 'selected' : ''}>Website</option>
                        <option value="referral" ${lead && lead.source === 'referral' ? 'selected' : ''}>Referral</option>
                        <option value="social" ${lead && lead.source === 'social' ? 'selected' : ''}>Social Media</option>
                        <option value="cold-call" ${lead && lead.source === 'cold-call' ? 'selected' : ''}>Cold Call</option>
                        <option value="event" ${lead && lead.source === 'event' ? 'selected' : ''}>Event</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="lead-notes">Notes</label>
                    <textarea id="lead-notes">${lead ? this.escapeHtml(lead.notes || '') : ''}</textarea>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="App.closeModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary">${lead ? 'Update' : 'Create'}</button>
                </div>
            </form>
        `;

        document.getElementById('lead-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveLead(lead);
        });

        this.openModal();
    },

    async saveLead(existing) {
        const data = {
            name: document.getElementById('lead-name').value.trim(),
            company: document.getElementById('lead-company').value.trim(),
            email: document.getElementById('lead-email').value.trim(),
            phone: document.getElementById('lead-phone').value.trim(),
            value: document.getElementById('lead-value').value || null,
            stage: document.getElementById('lead-stage').value,
            source: document.getElementById('lead-source').value,
            notes: document.getElementById('lead-notes').value.trim()
        };

        if (!data.name) return;

        try {
            if (existing) {
                await LeadsDataSource.updateLead(existing.id, data);
                this.showNotification('Lead updated.', 'success');
            } else {
                await LeadsDataSource.createLead(data);
                this.showNotification('Lead created.', 'success');
            }
        } catch (err) {
            this.showNotification(this._handleApiError(err), 'error');
            this.closeModal();
            return;
        }

        this.closeModal();
        await this.renderLeads();
        await this.renderDashboard();
    },

    async editLead(id) {
        try {
            const leads = await LeadsDataSource.getLeads();
            const lead = leads.find(l => l.id === id);
            if (lead) this.showLeadModal(lead);
        } catch (err) {
            console.error('Failed to load lead for editing:', err);
            this.showNotification('Failed to load lead.', 'error');
        }
    },

    async deleteLead(id) {
        if (!confirm('Are you sure you want to delete this lead?')) return;
        try {
            await LeadsDataSource.deleteLead(id);
            this.showNotification('Lead deleted.', 'success');
            await this.renderLeads();
            await this.renderDashboard();
        } catch (err) {
            this.showNotification(this._handleApiError(err), 'error');
        }
    },

    // === Activities ===
    bindActivities() {
        document.getElementById('btn-add-activity').addEventListener('click', async () => {
            await this.showActivityModal();
        });

        document.getElementById('activity-filter-type').addEventListener('change', () => this._renderActivitiesView());
        const statusFilter = document.getElementById('activity-filter-status');
        if (statusFilter) {
            statusFilter.addEventListener('change', () => this._renderActivitiesView());
        }

        const calendarToggle = document.getElementById('btn-toggle-calendar');
        if (calendarToggle) {
            calendarToggle.addEventListener('click', () => this.toggleCalendarView());
        }

        const prevBtn = document.getElementById('calendar-prev-month');
        if (prevBtn) {
            prevBtn.addEventListener('click', () => this._navigateCalendar(-1));
        }

        const nextBtn = document.getElementById('calendar-next-month');
        if (nextBtn) {
            nextBtn.addEventListener('click', () => this._navigateCalendar(1));
        }

        const todayBtn = document.getElementById('calendar-today');
        if (todayBtn) {
            todayBtn.addEventListener('click', () => this._goToToday());
        }
    },

    _renderActivitiesView() {
        if (this._calendarViewActive) {
            this.renderCalendar();
        } else {
            this.renderActivities();
        }
    },

    /**
     * Normalize backend activity field names to frontend field names.
     * Backend uses occurred_at, due_date, contact_name; frontend uses date, dueDate, contactName.
     */
    _normalizeActivities(activities) {
        return activities.map(a => ({
            ...a,
            date: a.date || a.occurred_at,
            dueDate: a.dueDate || a.due_date,
            contactName: a.contactName || a.contact_name,
            status: a.status || 'pending',
        }));
    },

    // === Analytics ===

    async renderAnalytics() {
        try {
            const funnel = await ApiClient.getFunnelAnalyticsFromApi();
            this._renderAnalyticsOverview(funnel);
            this._renderFunnelChart(funnel);
            this._renderFunnelBreakdown(funnel);
        } catch (err) {
            console.error('Failed to load analytics:', err);
            const el = document.getElementById('funnel-chart');
            if (el) {
                el.innerHTML = '<p class="empty-state">Failed to load analytics data.</p>';
            }
        }
        this._renderActivityTrends();
        this._bindTrendControls();
    },

    _bindTrendControls() {
        const rangeSelect = document.getElementById('trend-range');
        const groupSelect = document.getElementById('trend-group');
        if (rangeSelect) {
            rangeSelect.addEventListener('change', () => this._renderActivityTrends());
        }
        if (groupSelect) {
            groupSelect.addEventListener('change', () => this._renderActivityTrends());
        }
    },

    async _renderActivityTrends() {
        const range = document.getElementById('trend-range')?.value || '30d';
        const group = document.getElementById('trend-group')?.value || 'day';
        const overviewEl = document.getElementById('activity-trend-overview');
        const chartEl = document.getElementById('activity-trend-chart');
        const legendEl = document.getElementById('activity-trend-legend');

        try {
            const data = await ApiClient.getActivityTrendsFromApi(range, group);
            this._renderTrendOverview(data);
            this._renderTrendChart(data);
            this._renderTrendLegend(data);
        } catch (err) {
            console.error('Failed to load activity trends:', err);
            if (overviewEl) overviewEl.innerHTML = '<p class="empty-state">Failed to load trend data.</p>';
            if (chartEl) chartEl.innerHTML = '';
            if (legendEl) legendEl.innerHTML = '';
        }
    },

    _renderTrendOverview(data) {
        const el = document.getElementById('activity-trend-overview');
        if (!el) return;
        const total = data.total_activities ?? 0;
        const peak = data.peak_count ?? 0;
        const peakLabel = data.peak_bucket ? new Date(data.peak_bucket).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—';
        const buckets = data.buckets || [];
        const avgPerBucket = buckets.length ? (total / buckets.length).toFixed(1) : '0';

        el.innerHTML = `
            <div class="trend-stat">
                <span class="trend-stat-label">Total Activities</span>
                <span class="trend-stat-value">${total}</span>
            </div>
            <div class="trend-stat">
                <span class="trend-stat-label">Peak Day</span>
                <span class="trend-stat-value accent-text">${peak} <small>(${peakLabel})</small></span>
            </div>
            <div class="trend-stat">
                <span class="trend-stat-label">Avg per ${data.group === 'week' ? 'Week' : 'Day'}</span>
                <span class="trend-stat-value">${avgPerBucket}</span>
            </div>
        `;
    },

    _renderTrendChart(data) {
        const el = document.getElementById('activity-trend-chart');
        if (!el) return;
        const buckets = data.buckets || [];

        if (!buckets.length) {
            el.innerHTML = '<p class="empty-state">No activity data for the selected period.</p>';
            return;
        }

        const types = ['call', 'email', 'meeting', 'note', 'task'];
        const maxTotal = Math.max(...buckets.map(b => b.total), 1);

        let html = '<div class="trend-chart-scroll"><div class="trend-chart-grid">';

        buckets.forEach(b => {
            const dateLabel = new Date(b.bucket_date).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric'
            });
            const isPeak = b.bucket_date === data.peak_bucket;

            html += `<div class="trend-bar-group ${isPeak ? 'trend-peak' : ''}">`;
            html += `<div class="trend-bar-label">${dateLabel}</div>`;
            html += `<div class="trend-bars">`;

            types.forEach(type => {
                const val = b[type] || 0;
                if (val > 0) {
                    const heightPct = (val / maxTotal) * 100;
                    html += `<div class="trend-bar trend-bar-${type}" style="height: ${heightPct}%" title="${type}: ${val}"></div>`;
                }
            });

            html += `</div>`;
            html += `<div class="trend-bar-total">${b.total}</div>`;
            html += `</div>`;
        });

        html += '</div></div>';
        el.innerHTML = html;
    },

    _renderTrendLegend(data) {
        const el = document.getElementById('activity-trend-legend');
        if (!el) return;

        const types = [
            { key: 'call', label: 'Calls', icon: '📞' },
            { key: 'email', label: 'Emails', icon: '📧' },
            { key: 'meeting', label: 'Meetings', icon: '🤝' },
            { key: 'note', label: 'Notes', icon: '📝' },
            { key: 'task', label: 'Tasks', icon: '✅' },
        ];

        const buckets = data.buckets || [];
        let html = '<div class="trend-legend-items">';
        types.forEach(t => {
            const total = buckets.reduce((sum, b) => sum + (b[t.key] || 0), 0);
            if (total > 0) {
                html += `<span class="trend-legend-item trend-bar-${t.key}"><span class="trend-legend-dot"></span>${t.icon} ${t.label} (${total})</span>`;
            }
        });
        html += '</div>';
        el.innerHTML = html;
    },

    _renderAnalyticsOverview(data) {
        document.getElementById('analytics-total-leads').textContent = data.total_leads;
        document.getElementById('analytics-won-leads').textContent = data.won_leads;
        document.getElementById('analytics-conversion-rate').textContent =
            data.overall_conversion_rate + '%';
        document.getElementById('analytics-pipeline-value').textContent =
            '$' + data.total_pipeline_value.toLocaleString('en-US', { minimumFractionDigits: 2 });
    },

    _renderFunnelChart(data) {
        const container = document.getElementById('funnel-chart');
        const steps = data.funnel_steps;

        if (!steps || !steps.length) {
            container.innerHTML = '<p class="empty-state">No funnel data available.</p>';
            return;
        }

        const maxCount = Math.max(...steps.map(s => s.count), 1);
        let html = '';

        steps.forEach((step, i) => {
            const widthPct = Math.max((step.count / maxCount) * 100, 15);
            const colorClass = 'funnel-color-' + i;

            html += `
                <div class="funnel-step">
                    <div class="funnel-bar ${colorClass}" style="width: ${widthPct}%">
                        <div class="funnel-bar-content">
                            <span class="funnel-stage-label">${step.label}</span>
                            <span class="funnel-step-count">${step.count}</span>
                            ${step.value > 0 ? '<span class="funnel-step-value">$' + step.value.toLocaleString() + '</span>' : ''}
                        </div>
                    </div>
                </div>
            `;

            // Arrow between steps showing conversion rate
            if (i < steps.length - 1) {
                const nextStep = steps[i + 1];
                const dropClass = nextStep.drop_off > 0 ? 'funnel-arrow-drop' : '';
                html += `
                    <div class="funnel-arrow">
                        <span>▼</span>
                        <span class="funnel-arrow-rate">${nextStep.conversion_rate}% convert</span>
                        ${nextStep.drop_off > 0 ? '<span class="' + dropClass + '">(-' + nextStep.drop_off + ')</span>' : ''}
                    </div>
                `;
            }
        });

        container.innerHTML = html;
    },

    _renderFunnelBreakdown(data) {
        const container = document.getElementById('funnel-breakdown');
        const steps = data.funnel_steps;

        if (!steps || !steps.length) {
            container.innerHTML = '<p class="empty-state">No breakdown data available.</p>';
            return;
        }

        let html = `
            <table>
                <thead>
                    <tr>
                        <th>Stage</th>
                        <th>Count</th>
                        <th>Value</th>
                        <th>Conv. Rate</th>
                        <th>Drop-off</th>
                        <th>Avg. Days</th>
                    </tr>
                </thead>
                <tbody>
        `;

        steps.forEach(step => {
            const convClass = step.conversion_rate >= 70 ? 'metric-positive' :
                              step.conversion_rate >= 40 ? 'metric-neutral' : 'metric-negative';
            const dropClass = step.drop_off > 0 ? 'metric-negative' : 'metric-neutral';
            const avgDays = step.avg_days_in_stage !== null ? step.avg_days_in_stage + 'd' : '—';

            html += `
                <tr>
                    <td><strong>${step.label}</strong></td>
                    <td>${step.count}</td>
                    <td>$${step.value.toLocaleString()}</td>
                    <td class="${convClass}">${step.conversion_rate}%</td>
                    <td class="${dropClass}">${step.drop_off > 0 ? '-' + step.drop_off : '—'}</td>
                    <td>${avgDays}</td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    },

    // === Activities ===
    async renderActivities() {
        let activities;
        try {
            activities = await ActivitiesDataSource.getActivities();
        } catch (err) {
            console.error('Failed to load activities:', err);
            activities = [];
        }
        activities = this._normalizeActivities(activities);
        const filterType = document.getElementById('activity-filter-type').value;
        const filterStatus = document.getElementById('activity-filter-status') ? document.getElementById('activity-filter-status').value : '';

        if (filterType) {
            activities = activities.filter(a => a.type === filterType);
        }

        if (filterStatus === 'overdue') {
            activities = activities.filter(a => a.dueDate && a.status !== 'completed' && this.isOverdue(a.dueDate));
        } else if (filterStatus === 'completed') {
            activities = activities.filter(a => a.status === 'completed');
        } else if (filterStatus === 'active') {
            activities = activities.filter(a => a.status !== 'completed');
        }

        // Sort: overdue first, then by due date, then by date descending
        activities.sort((a, b) => {
            const aOverdue = a.dueDate && a.status !== 'completed' && this.isOverdue(a.dueDate) ? 0 : 1;
            const bOverdue = b.dueDate && b.status !== 'completed' && this.isOverdue(b.dueDate) ? 0 : 1;
            if (aOverdue !== bOverdue) return aOverdue - bOverdue;
            if (a.dueDate && b.dueDate) return new Date(a.dueDate) - new Date(b.dueDate);
            if (a.dueDate) return -1;
            if (b.dueDate) return 1;
            return new Date(b.date) - new Date(a.date);
        });

        const container = document.getElementById('activities-list');
        if (activities.length === 0) {
            container.innerHTML = '<div class="empty-state-card"><p>No activities found.</p></div>';
            return;
        }

        container.innerHTML = activities.map(a => {
            const isCompleted = a.status === 'completed';
            const isOverdue = a.dueDate && !isCompleted && this.isOverdue(a.dueDate);
            const overdueClass = isOverdue ? ' activity-overdue' : '';
            const completedClass = isCompleted ? ' activity-completed' : '';
            const dueDateHtml = a.dueDate ? `
                <span class="activity-due-date ${isOverdue ? 'due-overdue' : ''}">
                    ${isOverdue ? '⚠️ ' : '📅 '}Due: ${this.formatDateShort(a.dueDate)}
                </span>` : '';

            return `
            <div class="timeline-item${overdueClass}${completedClass}">
                <div class="timeline-marker">
                    <div class="timeline-dot"></div>
                </div>
                <div class="timeline-content">
                    <div class="timeline-header">
                        <h4>${this.getActivityIcon(a.type)} ${this.escapeHtml(a.type.charAt(0).toUpperCase() + a.type.slice(1))}</h4>
                        <div class="card-actions">
                            ${!isCompleted ? `<button class="card-action-btn btn-mark-complete" onclick="App.markActivityComplete('${a.id}')" title="Mark Complete">✅</button>` : ''}
                            <button class="card-action-btn" onclick="App.deleteActivity('${a.id}')" title="Delete">🗑️</button>
                        </div>
                    </div>
                    <p>${this.escapeHtml(a.description)}</p>
                    ${a.contactName ? `<p><small>Related: ${this.escapeHtml(a.contactName)}</small></p>` : ''}
                    <div class="activity-meta">
                        <span class="timeline-date">${this.formatDate(a.date)}</span>
                        ${dueDateHtml}
                    </div>
                </div>
            </div>
        `}).join('');
    },

    // === Calendar View State ===
    _calendarDate: null,
    _calendarViewActive: false,

    toggleCalendarView() {
        this._calendarViewActive = !this._calendarViewActive;
        const timelineEl = document.getElementById('activities-list');
        const calendarEl = document.getElementById('activities-calendar');
        const toggleBtn = document.getElementById('btn-toggle-calendar');

        if (this._calendarViewActive) {
            timelineEl.style.display = 'none';
            calendarEl.style.display = 'block';
            toggleBtn.textContent = '📋 Timeline';
            toggleBtn.classList.remove('btn-secondary');
            toggleBtn.classList.add('btn-primary');
            if (!this._calendarDate) {
                this._calendarDate = new Date();
            }
            this.renderCalendar();
        } else {
            timelineEl.style.display = 'block';
            calendarEl.style.display = 'none';
            toggleBtn.textContent = '📅 Calendar';
            toggleBtn.classList.remove('btn-primary');
            toggleBtn.classList.add('btn-secondary');
        }
    },

    _navigateCalendar(direction) {
        if (!this._calendarDate) {
            this._calendarDate = new Date();
        }
        this._calendarDate.setMonth(this._calendarDate.getMonth() + direction);
        this.renderCalendar();
    },

    _goToToday() {
        this._calendarDate = new Date();
        this.renderCalendar();
    },

    async renderCalendar() {
        if (!this._calendarDate) {
            this._calendarDate = new Date();
        }

        let activities;
        try {
            activities = await ActivitiesDataSource.getActivities();
        } catch (err) {
            console.error('Failed to load activities for calendar:', err);
            activities = [];
        }
        activities = this._normalizeActivities(activities);

        const filterType = document.getElementById('activity-filter-type').value;
        const filterStatus = document.getElementById('activity-filter-status') ? document.getElementById('activity-filter-status').value : '';

        if (filterType) {
            activities = activities.filter(a => a.type === filterType);
        }
        if (filterStatus === 'overdue') {
            activities = activities.filter(a => a.dueDate && a.status !== 'completed' && this.isOverdue(a.dueDate));
        } else if (filterStatus === 'completed') {
            activities = activities.filter(a => a.status === 'completed');
        } else if (filterStatus === 'active') {
            activities = activities.filter(a => a.status !== 'completed');
        }

        this._renderCalendarHeader();
        this._renderCalendarGrid(activities);
    },

    _renderCalendarHeader() {
        const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'];
        const header = document.getElementById('calendar-month-year');
        header.textContent = `${monthNames[this._calendarDate.getMonth()]} ${this._calendarDate.getFullYear()}`;
    },

    _renderCalendarGrid(activities) {
        const grid = document.getElementById('calendar-grid');
        const year = this._calendarDate.getFullYear();
        const month = this._calendarDate.getMonth();

        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const startDayOfWeek = firstDay.getDay();
        const daysInMonth = lastDay.getDate();

        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const activitiesByDate = {};
        activities.forEach(a => {
            const d = new Date(a.date);
            if (d.getFullYear() === year && d.getMonth() === month) {
                const dateKey = d.getDate();
                if (!activitiesByDate[dateKey]) {
                    activitiesByDate[dateKey] = [];
                }
                activitiesByDate[dateKey].push(a);
            }
        });

        let html = '';

        for (let i = 0; i < startDayOfWeek; i++) {
            html += '<div class="calendar-day calendar-day-empty"></div>';
        }

        for (let day = 1; day <= daysInMonth; day++) {
            const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            const dayDate = new Date(year, month, day);
            const isToday = dayDate.getTime() === today.getTime();
            const dayActivities = activitiesByDate[day] || [];

            const eventsHtml = dayActivities.slice(0, 3).map(a => {
                const isCompleted = a.status === 'completed';
                const isOverdue = a.dueDate && !isCompleted && this.isOverdue(a.dueDate);
                let cls = `calendar-event calendar-event-${a.type}`;
                if (isCompleted) cls += ' calendar-event-completed';
                if (isOverdue) cls += ' calendar-event-overdue';
                return `<div class="${cls}" title="${this.escapeHtml(a.description)}">${this.getActivityIcon(a.type)} ${this.escapeHtml(a.description.length > 20 ? a.description.slice(0, 20) + '...' : a.description)}</div>`;
            }).join('');

            const overflowHtml = dayActivities.length > 3
                ? `<div class="calendar-event-more">+${dayActivities.length - 3} more</div>` : '';

            html += `
                <div class="calendar-day ${isToday ? 'calendar-day-today' : ''}" data-date="${dateStr}">
                    <div class="calendar-day-number">${day}</div>
                    <div class="calendar-day-events">${eventsHtml}${overflowHtml}</div>
                </div>
            `;
        }

        grid.innerHTML = html;

        this._bindCalendarDayClicks();
        this._bindCalendarDrops(activities);
    },

    _bindCalendarDayClicks() {
        document.querySelectorAll('.calendar-day:not(.calendar-day-empty)').forEach(dayEl => {
            dayEl.addEventListener('dblclick', (e) => {
                if (e.target.closest('.calendar-event')) return;
                const date = dayEl.dataset.date;
                this._createActivityForDate(date);
            });
        });
    },

    async _createActivityForDate(date) {
        const modal = await this.showActivityModal(null, null, null, date);
    },

    _bindCalendarDrops(activities) {
        const grid = document.getElementById('calendar-grid');
        let draggedActivity = null;

        grid.querySelectorAll('.calendar-event').forEach(eventEl => {
            eventEl.draggable = true;
            eventEl.addEventListener('dragstart', (e) => {
                const title = e.target.title;
                const allActivities = activities;
                draggedActivity = allActivities.find(a => this.escapeHtml(a.description.length > 20 ? a.description.slice(0, 20) + '...' : a.description) === title.replace(/^[^\s]+\s/, ''));
                e.dataTransfer.effectAllowed = 'move';
                e.target.style.opacity = '0.5';
            });
            eventEl.addEventListener('dragend', (e) => {
                e.target.style.opacity = '1';
                draggedActivity = null;
                grid.querySelectorAll('.calendar-day').forEach(d => d.classList.remove('calendar-drop-target'));
            });
        });

        grid.querySelectorAll('.calendar-day:not(.calendar-day-empty)').forEach(dayEl => {
            dayEl.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                dayEl.classList.add('calendar-drop-target');
            });
            dayEl.addEventListener('dragleave', () => {
                dayEl.classList.remove('calendar-drop-target');
            });
            dayEl.addEventListener('drop', async (e) => {
                e.preventDefault();
                dayEl.classList.remove('calendar-drop-target');
                if (!draggedActivity) return;
                const newDate = dayEl.dataset.date;
                if (newDate && newDate !== new Date(draggedActivity.date).toISOString().split('T')[0]) {
                    try {
                        await ActivitiesDataSource.updateActivity(draggedActivity.id, { date: newDate });
                        this.showNotification('Activity rescheduled', 'success');
                        this.renderCalendar();
                    } catch (err) {
                        this.showNotification('Failed to reschedule activity.', 'error');
                    }
                }
            });
        });
    },

    isOverdue(dueDate) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        return new Date(dueDate) < today;
    },

    async getOverdueCount() {
        let activities;
        try {
            activities = await ActivitiesDataSource.getActivities();
        } catch (err) {
            console.error('Failed to load activities for overdue count:', err);
            return 0;
        }
        activities = this._normalizeActivities(activities);
        return activities.filter(a => a.dueDate && a.status !== 'completed' && this.isOverdue(a.dueDate)).length;
    },

    async markActivityComplete(id) {
        try {
            await ActivitiesDataSource.updateActivity(id, { status: 'completed' });
            await this._renderActivitiesView();
            await this.renderDashboard();
            await this.updateOverdueBadge();
            this.showNotification('Activity marked as complete', 'success');
        } catch (err) {
            this.showNotification('Failed to update activity.', 'error');
        }
    },

    async updateOverdueBadge() {
        const count = await this.getOverdueCount();
        const badge = document.getElementById('overdue-badge');
        if (badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'inline';
            } else {
                badge.style.display = 'none';
            }
        }
    },

    async showActivityModal(activity, prefillTypeOrContact, prefillContactName, prefillDate) {
        document.getElementById('modal-title').textContent = activity ? 'Edit Activity' : 'Add Activity';
        let contacts;
        try {
            contacts = await ContactsDataSource.getContacts();
        } catch (err) {
            console.error('Failed to load contacts for activity modal:', err);
            contacts = [];
        }
        if (activity) {
            activity = this._normalizeActivities([activity])[0];
        }
        const validTypes = ['call', 'email', 'meeting', 'note', 'task'];
        const prefillContact = prefillContactName || (validTypes.includes(prefillTypeOrContact) ? null : prefillTypeOrContact);
        const prefillType = validTypes.includes(prefillTypeOrContact) ? prefillTypeOrContact : null;
        const selectedType = activity ? activity.type : (prefillType || 'call');
        const contactOptions = contacts.map(c => {
            let isSelected = '';
            if (activity && activity.contactName === c.name) isSelected = 'selected';
            else if (prefillContact && c.name === prefillContact) isSelected = 'selected';
            return `<option value="${c.name}" ${isSelected}>${this.escapeHtml(c.name)}</option>`;
        }).join('');

        let defaultDateValue;
        if (activity) {
            defaultDateValue = this.toLocalDatetime(activity.date);
        } else if (prefillDate) {
            defaultDateValue = this.toLocalDatetime(new Date(prefillDate + 'T12:00:00').toISOString());
        } else {
            defaultDateValue = this.toLocalDatetime(new Date().toISOString());
        }

        document.getElementById('modal-body').innerHTML = `
            <form id="activity-form">
                <div class="form-group">
                    <label for="activity-type">Type *</label>
                    <select id="activity-type" required>
                        <option value="call" ${selectedType === 'call' ? 'selected' : ''}>📞 Call</option>
                        <option value="email" ${selectedType === 'email' ? 'selected' : ''}>📧 Email</option>
                        <option value="meeting" ${selectedType === 'meeting' ? 'selected' : ''}>🤝 Meeting</option>
                        <option value="note" ${selectedType === 'note' ? 'selected' : ''}>📝 Note</option>
                        <option value="task" ${selectedType === 'task' ? 'selected' : ''}>✅ Task</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="activity-description">Description *</label>
                    <textarea id="activity-description" required>${activity ? this.escapeHtml(activity.description || '') : ''}</textarea>
                </div>
                <div class="form-group">
                    <label for="activity-contact">Related Contact</label>
                    <select id="activity-contact">
                        <option value="">None</option>
                        ${contactOptions}
                    </select>
                </div>
                <div class="form-group">
                    <label for="activity-date">Date</label>
                    <input type="datetime-local" id="activity-date" value="${defaultDateValue}">
                </div>
                <div class="form-group">
                    <label for="activity-due-date">Due Date</label>
                    <input type="date" id="activity-due-date" value="${activity ? (activity.dueDate || '') : ''}">
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="App.closeModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary">${activity ? 'Update' : 'Create'}</button>
                </div>
            </form>
        `;

        document.getElementById('activity-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveActivity(activity);
        });

        this.openModal();
    },

    async saveActivity(existing) {
        const data = {
            type: document.getElementById('activity-type').value,
            description: document.getElementById('activity-description').value.trim(),
            contactName: document.getElementById('activity-contact').value,
            date: document.getElementById('activity-date').value ?
                new Date(document.getElementById('activity-date').value).toISOString() :
                new Date().toISOString(),
            dueDate: document.getElementById('activity-due-date').value || null,
            status: existing ? (existing.status || 'pending') : 'pending',
        };

        if (!data.description) return;

        try {
            if (existing) {
                const updated = await ActivitiesDataSource.updateActivity(existing.id, data);
                if (!updated) {
                    this.showNotification('Failed to update activity. Admin access required.', 'error');
                    this.closeModal();
                    return;
                }
            } else {
                const created = await ActivitiesDataSource.createActivity(data);
                if (!created) {
                    this.showNotification('Failed to create activity. Admin access required.', 'error');
                    this.closeModal();
                    return;
                }
            }
            this.closeModal();
            await this._renderActivitiesView();
            await this.renderDashboard();
            await this.updateOverdueBadge();
            this.showNotification(existing ? 'Activity updated.' : 'Activity created.', 'success');
        } catch (err) {
            this.showNotification('Failed to save activity.', 'error');
            this.closeModal();
        }
    },

    async deleteActivity(id) {
        if (!confirm('Are you sure you want to delete this activity?')) return;
        try {
            await ActivitiesDataSource.deleteActivity(id);
            await this._renderActivitiesView();
            await this.renderDashboard();
            await this.updateOverdueBadge();
            this.showNotification('Activity deleted.', 'success');
        } catch (err) {
            this.showNotification('Failed to delete activity.', 'error');
        }
    },

    // === Email Templates ===
    bindTemplates() {
        document.getElementById('btn-add-template').addEventListener('click', () => {
            if (!Auth.isAdmin()) {
                this.showNotification('Only administrators can create templates.', 'error');
                return;
            }
            this.showTemplateModal();
        });

        document.getElementById('template-filter-category').addEventListener('change', () => this.renderTemplates());

        // Variable help - click to insert
        document.querySelectorAll('#template-variable-help code').forEach(codeEl => {
            codeEl.addEventListener('click', () => {
                const textarea = document.getElementById('template-body');
                if (textarea && document.activeElement === textarea) {
                    const start = textarea.selectionStart;
                    const end = textarea.selectionEnd;
                    const text = textarea.value;
                    const varText = codeEl.textContent;
                    textarea.value = text.substring(0, start) + varText + text.substring(end);
                    textarea.selectionStart = textarea.selectionEnd = start + varText.length;
                    textarea.focus();
                }
            });
        });
    },

    async renderTemplates() {
        let templates;
        try {
            templates = await TemplatesDataSource.getTemplates();
        } catch (err) {
            console.error('Failed to load templates:', err);
            document.getElementById('templates-list').innerHTML =
                `<div class="empty-state-card"><p>⚠️ ${this.escapeHtml(err.message)}</p></div>`;
            return;
        }

        const filterCategory = document.getElementById('template-filter-category').value;
        if (filterCategory) {
            templates = templates.filter(t => t.category === filterCategory);
        }

        // Sort by most recently created
        templates.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

        const container = document.getElementById('templates-list');
        if (templates.length === 0) {
            container.innerHTML = '<div class="empty-state-card"><p>No templates found.</p></div>';
            return;
        }

        const isAdmin = Auth.isAdmin();
        container.innerHTML = templates.map(t => {
            const preview = (t.body || '').replace(/\{\{[^}]+\}\}/g, '[var]').slice(0, 150);
            return `
                <div class="template-card">
                    <div class="template-card-header">
                        <h4>${this.escapeHtml(t.name)}</h4>
                        <span class="template-category-badge ${t.category}">${this.escapeHtml(t.category)}</span>
                    </div>
                    <div class="template-subject">${this.escapeHtml(t.subject || 'No subject')}</div>
                    <div class="template-preview">${this.escapeHtml(preview)}</div>
                    <div class="template-actions">
                        ${isAdmin ? `<button class="btn-edit-template" onclick="App.editTemplate('${t.id}')">Edit</button>` : ''}
                        ${isAdmin ? `<button class="btn-delete-template" onclick="App.deleteTemplate('${t.id}')">Delete</button>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    },

    showTemplateModal(template) {
        document.getElementById('modal-title').textContent = template ? 'Edit Template' : 'Add Template';
        const categories = ['follow-up', 'introduction', 'proposal', 'thank-you', 'meeting', 'other'];

        document.getElementById('modal-body').innerHTML = `
            <form id="template-form" class="template-form">
                <div class="form-row">
                    <div class="form-group">
                        <label for="template-name">Template Name *</label>
                        <input type="text" id="template-name" value="${template ? this.escapeHtml(template.name) : ''}" required placeholder="e.g. Welcome Email">
                    </div>
                    <div class="form-group">
                        <label for="template-category">Category</label>
                        <select id="template-category">
                            ${categories.map(cat => `<option value="${cat}" ${template && template.category === cat ? 'selected' : ''}>${cat.charAt(0).toUpperCase() + cat.slice(1)}</option>`).join('')}
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <label for="template-subject">Email Subject</label>
                    <input type="text" id="template-subject" value="${template ? this.escapeHtml(template.subject || '') : ''}" placeholder="e.g. Welcome to {{contact_company}}!">
                </div>
                <div class="form-group">
                    <label for="template-body">Email Body *</label>
                    <textarea id="template-body" required placeholder="Dear {{contact_name}},

Thank you for your interest...">${template ? this.escapeHtml(template.body || '') : ''}</textarea>
                    <div class="variable-chips">
                        <span class="variable-chip" onclick="App.insertVariable('{{contact_name}}')">{{contact_name}}</span>
                        <span class="variable-chip" onclick="App.insertVariable('{{contact_email}}')">{{contact_email}}</span>
                        <span class="variable-chip" onclick="App.insertVariable('{{contact_phone}}')">{{contact_phone}}</span>
                        <span class="variable-chip" onclick="App.insertVariable('{{contact_company}}')">{{contact_company}}</span>
                        <span class="variable-chip" onclick="App.insertVariable('{{lead_name}}')">{{lead_name}}</span>
                        <span class="variable-chip" onclick="App.insertVariable('{{lead_company}}')">{{lead_company}}</span>
                        <span class="variable-chip" onclick="App.insertVariable('{{lead_value}}')">{{lead_value}}</span>
                    </div>
                </div>
                <div class="template-form-actions">
                    <button type="button" class="btn btn-secondary" onclick="App.closeModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary">${template ? 'Update' : 'Create'}</button>
                </div>
            </form>
        `;

        document.getElementById('template-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveTemplate(template);
        });

        this.openModal();
    },

    insertVariable(variable) {
        const textarea = document.getElementById('template-body');
        if (!textarea) return;
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const text = textarea.value;
        textarea.value = text.substring(0, start) + variable + text.substring(end);
        textarea.selectionStart = textarea.selectionEnd = start + variable.length;
        textarea.focus();
    },

    async saveTemplate(existing) {
        const data = {
            name: document.getElementById('template-name').value.trim(),
            category: document.getElementById('template-category').value,
            subject: document.getElementById('template-subject').value.trim(),
            body: document.getElementById('template-body').value.trim()
        };

        if (!data.name || !data.body) return;

        try {
            if (existing) {
                await TemplatesDataSource.updateTemplate(existing.id, data);
            } else {
                await TemplatesDataSource.createTemplate(data);
            }
            this.closeModal();
            await this.renderTemplates();
            this.showNotification(`Template "${data.name}" saved.`, 'success');
        } catch (err) {
            console.error('Failed to save template:', err);
            this.showNotification(this._handleApiError(err), 'error');
        }
    },

    async editTemplate(id) {
        if (!Auth.isAdmin()) {
            this.showNotification('Only administrators can edit templates.', 'error');
            return;
        }
        try {
            const templates = await TemplatesDataSource.getTemplates();
            const template = templates.find(t => t.id === id);
            if (template) {
                this.showTemplateModal(template);
            } else {
                this.showNotification('Template not found.', 'error');
            }
        } catch (err) {
            console.error('Failed to load template:', err);
            this.showNotification(this._handleApiError(err), 'error');
        }
    },

    async deleteTemplate(id) {
        if (!Auth.isAdmin()) {
            this.showNotification('Only administrators can delete templates.', 'error');
            return;
        }
        if (!confirm('Are you sure you want to delete this template?')) return;
        try {
            await TemplatesDataSource.deleteTemplate(id);
            await this.renderTemplates();
            this.showNotification('Template deleted.', 'success');
        } catch (err) {
            console.error('Failed to delete template:', err);
            this.showNotification(this._handleApiError(err), 'error');
        }
    },

    // === Settings ===
    bindSettings() {
        document.getElementById('btn-clear-data').addEventListener('click', () => this.clearData());
        document.getElementById('btn-create-backup').addEventListener('click', () => this.createBackup());
        document.getElementById('btn-restore-backup').addEventListener('click', () => {
            document.getElementById('backup-file-input').click();
        });
        document.getElementById('backup-file-input').addEventListener('change', (e) => this.restoreBackup(e));
        this.bindReminders();
    },

    // === Activity Reminders and Notifications ===
    bindReminders() {
        const saveBtn = document.getElementById('btn-save-reminders');
        const testBtn = document.getElementById('btn-test-notification');

        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveReminderSettings());
        }
        if (testBtn) {
            testBtn.addEventListener('click', () => this.testNotification());
        }
    },

    /**
     * Load reminder settings from backend and populate the settings form.
     */
    async loadReminderSettings() {
        try {
            const settings = await SettingsDataSource.getSettings();
            const payload = settings?.payload || {};
            const reminder = payload.reminder || {};

            const enabledEl = document.getElementById('reminder-enabled');
            const timeEl = document.getElementById('reminder-time');
            const advanceEl = document.getElementById('reminder-advance');
            const overdueEl = document.getElementById('reminder-overdue');

            if (enabledEl) enabledEl.checked = !!reminder.enabled;
            if (timeEl) timeEl.value = reminder.time || '09:00';
            if (advanceEl) advanceEl.value = reminder.advance != null ? String(reminder.advance) : '1';
            if (overdueEl) overdueEl.checked = reminder.overdue !== false;
        } catch (err) {
            console.warn('Failed to load reminder settings:', err);
        }
        this.updateNotificationPermissionDisplay();
    },

    /**
     * Save reminder settings to the backend.
     */
    async saveReminderSettings() {
        const enabled = document.getElementById('reminder-enabled')?.checked || false;
        const time = document.getElementById('reminder-time')?.value || '09:00';
        const advance = parseInt(document.getElementById('reminder-advance')?.value || '1', 10);
        const overdue = document.getElementById('reminder-overdue')?.checked !== false;

        try {
            const settings = await SettingsDataSource.getSettings();
            const payload = settings?.payload || {};
            payload.reminder = { enabled, time, advance, overdue };
            await SettingsDataSource.updateSettings(payload);
            this.showNotification('Reminder settings saved.', 'success');

            // Start or stop the reminder checker
            if (enabled) {
                this._startReminderChecker();
            } else {
                this._stopReminderChecker();
            }
        } catch (err) {
            this.showNotification(`Failed to save settings: ${err.message}`, 'error');
        }
    },

    /**
     * Test browser notification permission and show a sample notification.
     */
    async testNotification() {
        if (!('Notification' in window)) {
            this.showNotification('Browser notifications are not supported in this browser.', 'error');
            return;
        }

        if (Notification.permission === 'granted') {
            this._showBrowserNotification('AICRM Test Notification', 'Activity reminders are working! Configure them in Settings.');
            this.showNotification('Test notification sent (check your browser notifications).', 'success');
        } else if (Notification.permission !== 'denied') {
            const permission = await Notification.requestPermission();
            if (permission === 'granted') {
                this._showBrowserNotification('AICRM Test Notification', 'Activity reminders are working! Configure them in Settings.');
                this.showNotification('Permission granted. Test notification sent.', 'success');
            } else {
                this.showNotification('Notification permission was denied.', 'error');
            }
        } else {
            this.showNotification('Notifications are blocked. Please enable them in your browser settings.', 'error');
        }
        this.updateNotificationPermissionDisplay();
    },

    /**
     * Show a browser notification (native).
     */
    _showBrowserNotification(title, body) {
        if ('Notification' in window && Notification.permission === 'granted') {
            try {
                new Notification(title, {
                    body,
                    icon: '/favicon.ico',
                    tag: 'aicrm-reminder'
                });
            } catch (err) {
                console.warn('Failed to show browser notification:', err);
            }
        }
    },

    /**
     * Update the notification permission display in settings.
     */
    updateNotificationPermissionDisplay() {
        const el = document.getElementById('notif-permission');
        if (!el) return;

        if (!('Notification' in window)) {
            el.textContent = 'Not supported';
            el.style.color = '#ef4444';
        } else if (Notification.permission === 'granted') {
            el.textContent = 'Granted ✓';
            el.style.color = '#22c55e';
        } else if (Notification.permission === 'denied') {
            el.textContent = 'Blocked — enable in browser settings';
            el.style.color = '#ef4444';
        } else {
            el.textContent = 'Not requested — click Test to request';
            el.style.color = '#f59e0b';
        }
    },

    /**
     * Start the periodic reminder checker.
     */
    _startReminderChecker() {
        this._stopReminderChecker();

        // Check immediately on start
        this._checkReminders();

        // Then check every 5 minutes
        this._reminderInterval = setInterval(() => {
            this._checkReminders();
        }, 5 * 60 * 1000);
    },

    /**
     * Stop the periodic reminder checker.
     */
    _stopReminderChecker() {
        if (this._reminderInterval) {
            clearInterval(this._reminderInterval);
            this._reminderInterval = null;
        }
    },

    /**
     * Check for upcoming and overdue activities and send reminders.
     */
    async _checkReminders() {
        try {
            const settings = await SettingsDataSource.getSettings();
            const reminder = settings?.payload?.reminder;

            if (!reminder || !reminder.enabled) return;

            let activities;
            try {
                activities = await ActivitiesDataSource.getActivities();
            } catch (err) {
                console.warn('Failed to load activities for reminder check:', err);
                return;
            }
            activities = this._normalizeActivities(activities);

            const today = new Date();
            today.setHours(0, 0, 0, 0);

            const advanceDays = parseInt(reminder.advance, 10) || 1;
            const upcoming = [];
            const overdue = [];

            activities.forEach(a => {
                if (!a.dueDate || a.status === 'completed') return;

                const due = new Date(a.dueDate);
                due.setHours(0, 0, 0, 0);

                const diffDays = Math.floor((due - today) / (1000 * 60 * 60 * 24));

                if (diffDays < 0 && reminder.overdue !== false) {
                    overdue.push(a);
                } else if (diffDays >= 0 && diffDays <= advanceDays) {
                    upcoming.push(a);
                }
            });

            // Send in-app notification for upcoming activities
            if (upcoming.length > 0) {
                const todayUpcoming = upcoming.filter(a => {
                    const due = new Date(a.dueDate);
                    due.setHours(0, 0, 0, 0);
                    return due.getTime() === today.getTime();
                });

                if (todayUpcoming.length > 0) {
                    const desc = todayUpcoming.slice(0, 3).map(a => a.description).join(', ');
                    this._showInAppReminder(
                        `📅 ${todayUpcoming.length} activity${todayUpcoming.length > 1 ? 'ies' : ''} due today`,
                        desc + (todayUpcoming.length > 3 ? ` and ${todayUpcoming.length - 3} more` : '')
                    );

                    if ('Notification' in window && Notification.permission === 'granted') {
                        this._showBrowserNotification(
                            `📅 ${todayUpcoming.length} Activity Due Today`,
                            desc + (todayUpcoming.length > 3 ? ` and ${todayUpcoming.length - 3} more` : '')
                        );
                    }
                }
            }

            // Send in-app notification for overdue activities
            if (overdue.length > 0 && reminder.overdue !== false) {
                const desc = overdue.slice(0, 3).map(a => a.description).join(', ');
                this._showInAppReminder(
                    `⚠️ ${overdue.length} overdue activit${overdue.length > 1 ? 'ies' : 'y'}`,
                    desc + (overdue.length > 3 ? ` and ${overdue.length - 3} more` : '')
                );

                if ('Notification' in window && Notification.permission === 'granted') {
                    this._showBrowserNotification(
                        `⚠️ ${overdue.length} Overdue Activities`,
                        desc + (overdue.length > 3 ? ` and ${overdue.length - 3} more` : '')
                    );
                }
            }
        } catch (err) {
            console.warn('Reminder check failed:', err);
        }
    },

    /**
     * Show an in-app reminder notification (enhanced toast).
     */
    _showInAppReminder(title, description) {
        const container = document.getElementById('notification-container');
        const notif = document.createElement('div');
        notif.className = 'notification notification-info reminder-notification';
        notif.innerHTML = `
            <div class="notif-title">${this.escapeHtml(title)}</div>
            <div class="notif-desc">${this.escapeHtml(description)}</div>
        `;
        notif.style.cursor = 'pointer';
        notif.addEventListener('click', () => {
            this.navigate('activities');
        });
        container.appendChild(notif);
        setTimeout(() => {
            notif.classList.add('fade-out');
            setTimeout(() => notif.remove(), 300);
        }, 6000);
    },

    /**
     * Reset settings to defaults via the backend.
     * Only affects Settings — all other business data remains intact.
     */
    async clearData() {
        if (!confirm('Reset settings to defaults?\n\nThis will clear all current settings on the backend. Business data (Contacts, Templates, Leads, Activities) will not be affected.')) return;
        try {
            await SettingsDataSource.updateSettings({});
            this.showNotification('Settings reset to defaults on the backend.', 'success');
            this.renderCurrentPage();
            this.renderDashboard();
        } catch (err) {
            this.showNotification(`Failed to reset settings: ${err.message}`, 'error');
        }
    },

    // === Settings Backup and Restore ===
    /**
     * Create a settings backup from the backend.
     * This is a client-side convenience export — not a full system backup.
     */
    async createBackup() {
        try {
            const settings = await SettingsDataSource.getSettings();
            const version = await APP_VERSION;
            const backup = {
                metadata: {
                    appName: 'AICRM',
                    version: version,
                    createdAt: new Date().toISOString(),
                    scope: 'backend-managed',
                    note: 'This backup contains settings from the backend. All AICRM data is backend-managed.',
                    summary: {}
                },
                data: { SETTINGS: settings.payload }
            };
            const blob = new Blob([JSON.stringify(backup, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `aicrm_backup_${new Date().toISOString().slice(0, 10)}.json`;
            a.click();
            URL.revokeObjectURL(url);
            // Update last backup timestamp on backend
            await SettingsDataSource.updateSettings({ lastBackup: new Date().toISOString() });
            this.updateLastBackupDisplay(settings);
            this.showNotification('Backup created from backend settings.', 'success');
        } catch (err) {
            this.showNotification(`Backup failed: ${err.message}`, 'error');
        }
    },

    restoreBackup(event) {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const backup = JSON.parse(e.target.result);
                // Validate backup structure
                if (!backup.metadata || !backup.data) {
                    throw new Error('Invalid backup file: missing metadata or data sections');
                }
                // Show merge/replace dialog
                this._showRestoreDialog(backup);
            } catch (err) {
                this.showNotification('Restore failed: ' + err.message, 'error');
            }
        };
        reader.readAsText(file);
        event.target.value = '';
    },

    _showRestoreDialog(backup) {
        const modalBody = document.getElementById('modal-body');
        document.getElementById('modal-title').textContent = 'Restore Settings Backup';
        modalBody.innerHTML = `
            <div class="restore-dialog">
                <div class="restore-info">
                    <p><strong>Backup date:</strong> ${new Date(backup.metadata.createdAt).toLocaleString()}</p>
                    <p><strong>Version:</strong> ${backup.metadata.version || 'Unknown'}</p>
                    <p><strong>Contents:</strong> Settings</p>
                </div>
                <p>How would you like to restore this backup?</p>
                <div class="restore-actions">
                    <button id="btn-restore-replace" class="btn btn-primary">Replace Settings</button>
                    <button id="btn-restore-merge" class="btn btn-secondary">Merge with Existing</button>
                    <button id="btn-restore-cancel" class="btn btn-danger">Cancel</button>
                </div>
            </div>
        `;
        this.openModal();
        // Store backup data for the restore action
        this._pendingBackup = backup;
        document.getElementById('btn-restore-replace').addEventListener('click', () => {
            this._executeRestore(backup, 'replace');
            this.closeModal();
        });
        document.getElementById('btn-restore-merge').addEventListener('click', () => {
            this._executeRestore(backup, 'merge');
            this.closeModal();
        });
        document.getElementById('btn-restore-cancel').addEventListener('click', () => {
            this.closeModal();
        });
    },

    /**
     * Execute restore by pushing settings to the backend.
     */
    async _executeRestore(backup, mode) {
        const data = backup.data || backup;
        const backupSettings = data.SETTINGS || {};

        try {
            if (mode === 'replace') {
                await SettingsDataSource.updateSettings(backupSettings);
            } else {
                // Merge: get current backend settings, merge, push back
                const current = await SettingsDataSource.getSettings();
                const merged = { ...current.payload, ...backupSettings };
                await SettingsDataSource.updateSettings(merged);
            }

            this.renderCurrentPage();
            this.renderDashboard();
            const modeLabel = mode === 'replace' ? 'Replaced' : 'Merged';
            this.showNotification(`${modeLabel} settings on the backend.`, 'success');
        } catch (err) {
            this.showNotification(`Restore failed: ${err.message}`, 'error');
        }
    },

    updateLastBackupDisplay(settings) {
        const el = document.getElementById('last-backup-date');
        if (!el) return;
        // If settings object passed in, use it; otherwise load from backend
        const payload = settings ? settings.payload : null;
        if (payload && payload.lastBackup) {
            el.textContent = new Date(payload.lastBackup).toLocaleString();
        } else {
            // Load from backend asynchronously
            this._loadLastBackupFromBackend();
        }
    },

    async _loadLastBackupFromBackend() {
        const el = document.getElementById('last-backup-date');
        if (!el) return;
        try {
            const settings = await SettingsDataSource.getSettings();
            if (settings && settings.payload && settings.payload.lastBackup) {
                el.textContent = new Date(settings.payload.lastBackup).toLocaleString();
            } else {
                el.textContent = 'Never';
            }
        } catch (err) {
            console.warn('Could not load last backup date from backend:', err.message);
            el.textContent = 'N/A';
        }
    },

    // === Modal ===
    bindModal() {
        document.getElementById('modal-close').addEventListener('click', () => this.closeModal());
        document.getElementById('modal-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this.closeModal();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeModal();
        });
    },

    openModal() {
        const overlay = document.getElementById('modal-overlay');
        overlay.classList.remove('hidden');
        overlay.classList.add('active');
    },

    closeModal() {
        const overlay = document.getElementById('modal-overlay');
        overlay.classList.add('hidden');
        overlay.classList.remove('active');
        document.getElementById('modal-container').classList.remove('modal-wide');
        document.getElementById('modal-body').innerHTML = '';
    },

    // === Keyboard Shortcuts ===
    bindKeyboardShortcuts() {
        // Bind the shortcuts help button
        document.getElementById('shortcuts-toggle').addEventListener('click', () => this.showShortcutsModal());

        // Global keyboard listener
        document.addEventListener('keydown', (e) => {
            // Don't trigger shortcuts when typing in inputs (except special keys)
            const isInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName);

            // ? (Shift+/) opens shortcuts help - check BEFORE /
            if (e.key === '?' && !isInput) {
                e.preventDefault();
                this.showShortcutsModal();
                return;
            }

            // / focuses search bar
            if (e.key === '/' && !isInput) {
                e.preventDefault();
                document.getElementById('global-search').focus();
                return;
            }

            // Q opens quick-add FAB
            if (e.key.toLowerCase() === 'q' && !isInput && !e.ctrlKey && !e.metaKey) {
                e.preventDefault();
                this.toggleFAB();
                return;
            }

            // K toggles Kanban board view (only on leads page)
            if (e.key.toLowerCase() === 'k' && !isInput && !e.ctrlKey && !e.metaKey) {
                e.preventDefault();
                if (this.currentPage === 'leads') {
                    this.toggleKanbanView();
                }
                return;
            }

            // C toggles calendar view (only on activities page)
            if (e.key.toLowerCase() === 'c' && !isInput && !e.ctrlKey && !e.metaKey) {
                e.preventDefault();
                if (this.currentPage === 'activities') {
                    this.toggleCalendarView();
                }
                return;
            }

            // If user is typing in a text field, only handle Escape
            if (isInput) return;

            // Number keys for navigation (1-5)
            if (e.key >= '1' && e.key <= '5' && !e.ctrlKey && !e.metaKey) {
                const pages = ['dashboard', 'contacts', 'leads', 'activities', 'templates'];
                const idx = parseInt(e.key) - 1;
                if (idx < pages.length) {
                    e.preventDefault();
                    this.navigate(pages[idx]);
                }
                return;
            }

            // Ctrl/Cmd shortcuts
            if (e.ctrlKey || e.metaKey) {
                if (e.key.toLowerCase() === 'n') {
                    e.preventDefault();
                    this.showContactModal();
                } else if (e.key.toLowerCase() === 'l') {
                    e.preventDefault();
                    this.showLeadModal();
                } else if (e.key.toLowerCase() === 'e') {
                    e.preventDefault();
                    this.exportCurrentPageCSV();
                }
            }
        });
    },

    // === Quick-Add FAB ===
    bindFAB() {
        const fabButton = document.getElementById('fab-button');
        const fabChips = document.getElementById('fab-chips');

        if (!fabButton || !fabChips) return;

        fabButton.addEventListener('click', () => this.toggleFAB());

        fabChips.querySelectorAll('.fab-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const type = chip.dataset.type;
                this.collapseFAB();
                this.showActivityModal(null, type);
            });
        });

        // Close FAB when clicking outside
        document.addEventListener('click', (e) => {
            const container = document.getElementById('fab-container');
            if (container && !container.contains(e.target) && this._fabExpanded) {
                this.collapseFAB();
            }
        });
    },

    toggleFAB() {
        this._fabExpanded = !this._fabExpanded;
        const fabButton = document.getElementById('fab-button');
        const fabChips = document.getElementById('fab-chips');
        if (this._fabExpanded) {
            fabButton.classList.add('expanded');
            fabChips.classList.remove('hidden');
        } else {
            fabButton.classList.remove('expanded');
            fabChips.classList.add('hidden');
        }
    },

    collapseFAB() {
        if (!this._fabExpanded) return;
        this._fabExpanded = false;
        const fabButton = document.getElementById('fab-button');
        const fabChips = document.getElementById('fab-chips');
        fabButton.classList.remove('expanded');
        fabChips.classList.add('hidden');
    },

    // === Shortcuts Help ===
    showShortcutsModal() {
        document.getElementById('modal-title').textContent = 'Keyboard Shortcuts';
        document.getElementById('modal-body').innerHTML = `
            <div class="shortcuts-help">
                <div class="shortcut-section">
                    <h4>Navigation</h4>
                    <div class="shortcut-row"><kbd>1</kbd><span>Dashboard</span></div>
                    <div class="shortcut-row"><kbd>2</kbd><span>Contacts</span></div>
                    <div class="shortcut-row"><kbd>3</kbd><span>Leads</span></div>
                    <div class="shortcut-row"><kbd>4</kbd><span>Activities</span></div>
                    <div class="shortcut-row"><kbd>5</kbd><span>Templates</span></div>
                </div>
                <div class="shortcut-section">
                    <h4>Actions</h4>
                    <div class="shortcut-row"><kbd>/</kbd><span>Focus search bar</span></div>
                    <div class="shortcut-row"><kbd>Q</kbd><span>Quick-add activity</span></div>
                    <div class="shortcut-row"><kbd>C</kbd><span>Toggle calendar view (Activities)</span></div>
                    <div class="shortcut-row"><kbd>Ctrl</kbd>+<kbd>N</kbd><span>New Contact</span></div>
                    <div class="shortcut-row"><kbd>Ctrl</kbd>+<kbd>L</kbd><span>New Lead</span></div>
                    <div class="shortcut-row"><kbd>Ctrl</kbd>+<kbd>E</kbd><span>Export CSV</span></div>
                    <div class="shortcut-row"><kbd>Esc</kbd><span>Close modal</span></div>
                    <div class="shortcut-row"><kbd>?</kbd><span>Show this help</span></div>
                </div>
            </div>
        `;
        this.openModal();
    },

    exportCurrentPageCSV() {
        if (this.currentPage === 'contacts') {
            this.exportContactsCSV();
        } else if (this.currentPage === 'leads') {
            this.exportLeadsCSV();
        } else {
            this.showNotification('CSV export is available on Contacts and Leads pages.', 'info');
        }
    },

    // === Helpers ===
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    formatDate(dateStr) {
        const date = new Date(dateStr);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    },

    formatDateShort(dateStr) {
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    },

    toLocalDatetime(isoStr) {
        const d = new Date(isoStr);
        const offset = d.getTimezoneOffset();
        const local = new Date(d.getTime() - offset * 60000);
        return local.toISOString().slice(0, 16);
    },

    getActivityIcon(type) {
        const icons = {
            call: '📞',
            email: '📧',
            meeting: '🤝',
            note: '📝',
            task: '✅'
        };
        return icons[type] || '📋';
    },

    getActivityColor(type) {
        const colors = {
            call: '#3b82f6',
            email: '#22c55e',
            meeting: '#a855f7',
            note: '#f97316',
            task: '#ef4444'
        };
        return colors[type] || '#6b7280';
    },

    /**
     * Group activities into time buckets for the timeline view.
     * Returns array of { label, activities[] } sorted newest first.
     */
    _groupActivitiesByDate(activities) {
        if (!activities.length) return [];
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        const thisWeek = new Date(today);
        thisWeek.setDate(thisWeek.getDate() - thisWeek.getDay());
        const thisMonth = new Date(today.getFullYear(), today.getMonth(), 1);

        const groups = [];
        const groupMap = {};

        activities.forEach(a => {
            const date = new Date(a.date);
            const dateStart = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            let label;

            if (dateStart >= today) label = 'Today';
            else if (dateStart >= yesterday) label = 'Yesterday';
            else if (dateStart >= thisWeek) label = 'This Week';
            else if (dateStart >= thisMonth) label = 'This Month';
            else {
                const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                    'July', 'August', 'September', 'October', 'November', 'December'];
                label = monthNames[date.getMonth()] + ' ' + date.getFullYear();
            }

            if (!groupMap[label]) {
                groupMap[label] = { label, activities: [] };
                groups.push(groupMap[label]);
            }
            groupMap[label].activities.push(a);
        });

        return groups;
    },

    /**
     * Calculate time gaps between consecutive activities.
     * Returns array of { from, to, days } for gaps exceeding threshold.
     */
    _calculateTimeGaps(activities, thresholdDays = 14) {
        if (activities.length < 2) return [];
        const sorted = [...activities].sort((a, b) => new Date(a.date) - new Date(b.date));
        const gaps = [];

        for (let i = 1; i < sorted.length; i++) {
            const prev = new Date(sorted[i - 1].date);
            const curr = new Date(sorted[i].date);
            const diffMs = curr.getTime() - prev.getTime();
            const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));

            if (diffDays >= thresholdDays) {
                gaps.push({
                    from: sorted[i - 1].date,
                    to: sorted[i].date,
                    days: diffDays
                });
            }
        }

        // Check gap from last activity to now
        const now = new Date();
        const lastActivity = new Date(sorted[sorted.length - 1].date);
        const daysSinceLast = Math.round((now.getTime() - lastActivity.getTime()) / (1000 * 60 * 60 * 24));
        if (daysSinceLast >= thresholdDays) {
            gaps.push({
                from: sorted[sorted.length - 1].date,
                to: null,
                days: daysSinceLast
            });
        }

        return gaps;
    },

    /**
     * Generate activity summary text for a contact.
     * Returns string like "Last contacted 5 days ago via email. 12 total activities."
     */
    _generateActivitySummary(activities) {
        if (!activities.length) return 'No activities recorded yet.';

        const now = new Date();
        const sorted = [...activities].sort((a, b) => new Date(b.date) - new Date(a.date));
        const lastActivity = new Date(sorted[0].date);
        const daysSince = Math.round((now.getTime() - lastActivity.getTime()) / (1000 * 60 * 60 * 24));

        const timeAgo = daysSince === 0 ? 'today' : daysSince === 1 ? 'yesterday' : `${daysSince} days ago`;
        const lastType = sorted[0].type;
        const icon = this.getActivityIcon(lastType);

        // Count by type
        const typeCounts = {};
        activities.forEach(a => {
            typeCounts[a.type] = (typeCounts[a.type] || 0) + 1;
        });

        const typeSummary = Object.entries(typeCounts)
            .sort((a, b) => b[1] - a[1])
            .map(([type, count]) => `${this.getActivityIcon(type)} ${count}`)
            .join(', ');

        return `Last contacted ${timeAgo} via ${icon} ${lastType}. ${activities.length} total activities: ${typeSummary}`;
    },

    /**
     * Render the enhanced communication timeline HTML.
     */
    _renderTimelineView(activities) {
        if (!activities.length) {
            return '<div class="empty-state-card"><p>No activities recorded for this contact yet.</p></div>';
        }

        const groups = this._groupActivitiesByDate(activities);
        const gaps = this._calculateTimeGaps(activities);
        const summary = this._generateActivitySummary(activities);

        let html = `<div class="timeline-summary" title="${this.escapeHtml(summary)}">${this.escapeHtml(summary)}</div>`;

        groups.forEach(group => {
            html += `<div class="timeline-group"><div class="timeline-group-header">${this.escapeHtml(group.label)} (${group.activities.length})</div>`;

            group.activities.forEach(a => {
                const isCompleted = a.status === 'completed';
                const isOverdue = a.dueDate && !isCompleted && this.isOverdue(a.dueDate);
                const overdueClass = isOverdue ? ' activity-overdue' : '';
                const completedClass = isCompleted ? ' activity-completed' : '';
                const dotColor = this.getActivityColor(a.type);
                const dueDateHtml = a.dueDate ? `
                    <span class="activity-due-date ${isOverdue ? 'due-overdue' : ''}">
                        ${isOverdue ? '⚠️ ' : '📅 '}Due: ${this.formatDateShort(a.dueDate)}
                    </span>` : '';

                html += `
                    <div class="timeline-item${overdueClass}${completedClass}">
                        <div class="timeline-marker">
                            <div class="timeline-dot" style="background: ${dotColor}"></div>
                        </div>
                        <div class="timeline-content">
                            <div class="timeline-header">
                                <h4>${this.getActivityIcon(a.type)} ${this.escapeHtml(a.type.charAt(0).toUpperCase() + a.type.slice(1))}</h4>
                                <div class="card-actions">
                                    ${!isCompleted ? `<button class="card-action-btn btn-mark-complete" onclick="App.markActivityComplete('${a.id}')" title="Mark Complete">✅</button>` : ''}
                                </div>
                            </div>
                            <p>${this.escapeHtml(a.description)}</p>
                            <div class="activity-meta">
                                <span class="timeline-date">${this.formatDate(a.date)}</span>
                                ${dueDateHtml}
                            </div>
                        </div>
                    </div>
                `;
            });

            html += '</div>';
        });

        // Render time gap indicators
        gaps.forEach(gap => {
            const gapLabel = gap.to
                ? `No activity for ${gap.days} days`
                : `No activity for ${gap.days} days`;
            html += `
                <div class="timeline-gap" title="${gapLabel}">
                    <div class="timeline-gap-marker"></div>
                    <div class="timeline-gap-content">
                        <span class="timeline-gap-icon">⏰</span>
                        <span class="timeline-gap-text">${gapLabel}</span>
                    </div>
                </div>
            `;
        });

        return html;
    },

    formatCurrency(value) {
        return '$' + Number(value || 0).toLocaleString('en-US', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        });
    },

    // === Settings Page ===

    renderSettings() {
        // Bind settings export/import/reset buttons
        const exportBtn = document.getElementById('btn-create-backup');
        if (exportBtn) {
            exportBtn.onclick = async () => {
                try {
                    const settings = await ApiClient.getSettingsFromApi();
                    const blob = new Blob([JSON.stringify(settings, null, 2)], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `aicrm-settings-backup-${new Date().toISOString().slice(0, 10)}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                    this.showNotification('Settings exported', 'success');
                } catch (err) {
                    this.showNotification('Failed to export settings', 'error');
                }
            };
        }

        const importBtn = document.getElementById('btn-restore-backup');
        if (importBtn) {
            importBtn.onclick = () => {
                document.getElementById('backup-file-input').click();
            };
        }

        const fileInput = document.getElementById('backup-file-input');
        if (fileInput) {
            fileInput.onchange = async (e) => {
                const file = e.target.files[0];
                if (!file) return;
                try {
                    const text = await file.text();
                    const settings = JSON.parse(text);
                    await ApiClient.updateSettingsInApi(settings);
                    this.showNotification('Settings restored', 'success');
                    this.navigate('settings');
                } catch (err) {
                    this.showNotification('Failed to import settings', 'error');
                }
                fileInput.value = '';
            };
        }

        const clearBtn = document.getElementById('btn-clear-data');
        if (clearBtn) {
            clearBtn.onclick = async () => {
                if (!confirm('This will reset all settings to defaults. Continue?')) return;
                try {
                    await ApiClient.resetSettingsInApi();
                    this.showNotification('Settings reset', 'success');
                    this.navigate('settings');
                } catch (err) {
                    this.showNotification('Failed to reset settings', 'error');
                }
            };
        }
    },

    // === Win/Loss Reason Tracking ===

    /**
     * Prompt the user for a win/loss reason when a lead moves to won/lost.
     * Returns true if the user proceeded (with or without a reason), false if cancelled.
     */
    async _promptWinLossReason(leadId, leadName, outcome) {
        return new Promise((resolve) => {
            const label = outcome === 'won' ? 'Won' : 'Lost';
            document.getElementById('modal-title').textContent = `Record ${label} Reason — ${leadName}`;
            document.getElementById('modal-body').innerHTML = `
                <form id="winloss-reason-form">
                    <p class="winloss-intro">Why was this deal ${outcome}?</p>
                    <div class="form-group">
                        <label for="wl-reason-category">Reason Category</label>
                        <select id="wl-reason-category">
                            <option value="">— Skip (no reason recorded) —</option>
                            <option value="budget">Budget / Pricing</option>
                            <option value="competitor">Competitor</option>
                            <option value="feature-gap">Feature Gap</option>
                            <option value="timing">Timing</option>
                            <option value="decision-changed">Decision Changed</option>
                            <option value="internal-issues">Internal Issues</option>
                            <option value="other">Other</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="wl-reason-text">Details (optional)</label>
                        <textarea id="wl-reason-text" rows="3" placeholder="Add any additional context..."></textarea>
                    </div>
                    <div class="form-group" id="wl-competitor-group" style="display:none;">
                        <label for="wl-competitor-name">Competitor Name</label>
                        <input type="text" id="wl-competitor-name" placeholder="e.g. CompetitorCorp">
                    </div>
                    <div class="form-actions">
                        <button type="button" class="btn btn-secondary" id="wl-cancel-btn">Cancel</button>
                        <button type="submit" class="btn btn-primary">Confirm ${label}</button>
                    </div>
                </form>
            `;
            this.openModal();

            // Show/hide competitor field
            const categorySelect = document.getElementById('wl-reason-category');
            const competitorGroup = document.getElementById('wl-competitor-group');
            categorySelect.addEventListener('change', () => {
                competitorGroup.style.display = categorySelect.value === 'competitor' ? 'block' : 'none';
            });

            // Cancel
            document.getElementById('wl-cancel-btn').addEventListener('click', () => {
                this.closeModal();
                resolve(false);
            });

            // Submit
            document.getElementById('winloss-reason-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const reasonCategory = document.getElementById('wl-reason-category').value;
                const reasonText = document.getElementById('wl-reason-text').value.trim();
                const competitorName = document.getElementById('wl-competitor-name').value.trim() || null;

                if (reasonCategory) {
                    try {
                        await ApiClient.createDealOutcomeInApi({
                            lead_id: leadId,
                            outcome: outcome,
                            reason_category: reasonCategory,
                            reason_text: reasonText || null,
                            competitor_name: competitorName,
                        });
                    } catch (err) {
                        console.error('Failed to save deal outcome:', err);
                        this.showNotification('Failed to save reason — stage will still update', 'warning');
                    }
                }
                try {
                    this.closeModal();
                } catch (e) {
                    console.error('Failed to close modal:', e);
                }
                resolve(true);
            });
        });
    },

    /**
     * Render the Win/Loss Reasons page.
     */
    async renderWinLossPage() {
        let analytics = null;
        let outcomes = [];
        try {
            analytics = await ApiClient.getDealOutcomeAnalyticsFromApi();
        } catch (err) {
            console.error('Failed to load deal outcome analytics:', err);
        }
        try {
            outcomes = await ApiClient.getDealOutcomesFromApi();
        } catch (err) {
            console.error('Failed to load deal outcomes:', err);
        }

        // Stats overview
        const totalWon = analytics?.total_won || 0;
        const totalLost = analytics?.total_lost || 0;
        const winRate = analytics?.win_rate ?? 0;
        document.getElementById('winloss-stats').innerHTML = `
            <div class="analytics-overview">
                <div class="analytics-stat-card">
                    <div class="analytics-stat-label">Total Won</div>
                    <div class="analytics-stat-value metric-positive">${totalWon}</div>
                </div>
                <div class="analytics-stat-card">
                    <div class="analytics-stat-label">Total Lost</div>
                    <div class="analytics-stat-value metric-negative">${totalLost}</div>
                </div>
                <div class="analytics-stat-card">
                    <div class="analytics-stat-label">Win Rate</div>
                    <div class="analytics-stat-value ${winRate >= 50 ? 'metric-positive' : 'metric-negative'}">${winRate.toFixed(1)}%</div>
                </div>
            </div>
        `;

        // Win reasons chart
        const topWins = analytics?.top_win_reasons || [];
        const maxWinCount = Math.max(...topWins.map(r => r.count), 1);
        document.getElementById('win-reasons-chart').innerHTML = topWins.length ? topWins.map(r => `
            <div class="winloss-bar-row">
                <span class="winloss-bar-label">${this._formatReasonLabel(r.reason)}</span>
                <div class="winloss-bar-track">
                    <div class="winloss-bar-fill metric-positive" style="width:${(r.count / maxWinCount * 100).toFixed(0)}%"></div>
                </div>
                <span class="winloss-bar-count">${r.count}</span>
            </div>
        `).join('') : '<p class="empty-state">No win reasons recorded yet.</p>';

        // Loss reasons chart
        const topLosses = analytics?.top_loss_reasons || [];
        const maxLossCount = Math.max(...topLosses.map(r => r.count), 1);
        document.getElementById('loss-reasons-chart').innerHTML = topLosses.length ? topLosses.map(r => `
            <div class="winloss-bar-row">
                <span class="winloss-bar-label">${this._formatReasonLabel(r.reason)}</span>
                <div class="winloss-bar-track">
                    <div class="winloss-bar-fill metric-negative" style="width:${(r.count / maxLossCount * 100).toFixed(0)}%"></div>
                </div>
                <span class="winloss-bar-count">${r.count}</span>
            </div>
        `).join('') : '<p class="empty-state">No loss reasons recorded yet.</p>';

        // Competitor mentions
        const competitors = analytics?.competitor_mentions || [];
        document.getElementById('competitor-chart').innerHTML = competitors.length ? competitors.map(c => `
            <div class="winloss-bar-row">
                <span class="winloss-bar-label">${c.competitor}</span>
                <div class="winloss-bar-track">
                    <div class="winloss-bar-fill accent-text" style="width:${(c.count / Math.max(...competitors.map(x => x.count), 1) * 100).toFixed(0)}%"></div>
                </div>
                <span class="winloss-bar-count">${c.count}</span>
            </div>
        `).join('') : '<p class="empty-state">No competitor mentions yet.</p>';

        // Outcomes table
        const sortedOutcomes = [...outcomes].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        document.getElementById('winloss-table').innerHTML = sortedOutcomes.length ? `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Lead</th>
                        <th>Outcome</th>
                        <th>Reason</th>
                        <th>Details</th>
                        <th>Competitor</th>
                        <th>Date</th>
                    </tr>
                </thead>
                <tbody>
                    ${sortedOutcomes.map(o => `
                        <tr>
                            <td class="winloss-lead-name">${o.lead_name || o.lead_id}</td>
                            <td><span class="outcome-badge outcome-${o.outcome}">${o.outcome === 'won' ? 'Won' : 'Lost'}</span></td>
                            <td>${this._formatReasonLabel(o.reason_category)}</td>
                            <td class="winloss-detail">${o.reason_text || '—'}</td>
                            <td>${o.competitor_name || '—'}</td>
                            <td>${this.formatDateTime(o.created_at)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        ` : '<p class="empty-state">No outcomes recorded yet. Move leads to Won/Lost to track reasons.</p>';
    },

    _formatReasonLabel(reason) {
        const labels = {
            'budget': 'Budget / Pricing',
            'competitor': 'Competitor',
            'feature-gap': 'Feature Gap',
            'timing': 'Timing',
            'decision-changed': 'Decision Changed',
            'internal-issues': 'Internal Issues',
            'other': 'Other',
        };
        return labels[reason] || reason || '—';
    },

    formatDateTime(isoString) {
        if (!isoString) return '—';
        const d = new Date(isoString);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) + ' ' +
               d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    },

    // ── Sales Goals ──────────────────────────────────────────────────

    async renderSalesGoals() {
        const goals = await SalesGoalsDataSource.getGoals();
        const progress = await SalesGoalsDataSource.getProgress();
        this.renderSalesGoalsList(goals, progress);
        this.renderSalesGoalsSummary(goals, progress);
        this.bindSalesGoalsEvents();
    },

    renderSalesGoalsList(goals, progress) {
        const container = document.getElementById('goals-list');
        if (!container) return;

        if (!goals || goals.length === 0) {
            container.innerHTML = '<p class="empty-state">No sales goals defined yet. Click "Add Goal" to get started.</p>';
            return;
        }

        // Build a lookup from the progress goals array (backend computes current_value + progress_percent)
        const progressMap = {};
        (progress.goals || []).forEach(g => { progressMap[g.id] = g; });

        const sorted = [...goals].sort((a, b) => new Date(a.startDate) - new Date(b.startDate));

        container.innerHTML = sorted.map(goal => {
            const pg = progressMap[goal.id] || {};
            const currentValue = pg.currentValue || goal.currentValue || 0;
            const pct = goal.targetValue > 0 ? Math.min(100, Math.round((currentValue / goal.targetValue) * 100)) : 0;
            const isCompleted = pct >= 100;
            const daysLeft = goal.endDate ? Math.max(0, Math.ceil((new Date(goal.endDate) - new Date()) / 86400000)) : '—';

            return `
                <div class="goal-card" data-id="${goal.id}">
                    <div class="goal-card-header">
                        <div class="goal-card-title">
                            <span class="goal-type-badge ${goal.type}">${this._goalTypeLabel(goal.type)}</span>
                            <span class="goal-name">${this._esc(goal.name)}</span>
                            ${isCompleted ? '<span class="goal-completed-badge">✅ Completed</span>' : ''}
                        </div>
                        <div class="goal-card-actions">
                            <button class="btn-icon btn-edit-goal" title="Edit" data-id="${goal.id}">✏️</button>
                            <button class="btn-icon btn-delete-goal" title="Delete" data-id="${goal.id}">🗑️</button>
                        </div>
                    </div>
                    <div class="goal-card-body">
                        <div class="goal-progress-section">
                            <div class="goal-progress-label">
                                <span>Progress</span>
                                <span class="goal-progress-pct">${pct}%</span>
                            </div>
                            <div class="goal-progress-bar">
                                <div class="goal-progress-fill ${isCompleted ? 'completed' : ''}" style="width: ${pct}%"></div>
                            </div>
                            <div class="goal-progress-values">
                                <span>${this._goalValueLabel(currentValue, goal.type)} / ${this._goalValueLabel(goal.targetValue, goal.type)}</span>
                            </div>
                        </div>
                        <div class="goal-meta">
                            <span class="goal-meta-item">📅 ${this._fmtPeriod(goal.period)}</span>
                            <span class="goal-meta-item">🗓️ ${this._fmtDate(goal.startDate)} → ${this._fmtDate(goal.endDate)}</span>
                            <span class="goal-meta-item">⏰ ${daysLeft} days left</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    },

    renderSalesGoalsSummary(goals, progress) {
        // Active = end_date is in the future
        const now = new Date();
        const activeGoals = goals.filter(g => new Date(g.endDate) >= now);
        const completedGoals = goals.filter(g => {
            return g.targetValue > 0 && (g.progressPercent || 0) >= 100;
        });

        const totalTarget = activeGoals.reduce((s, g) => s + g.targetValue, 0);
        const totalCurrent = activeGoals.reduce((s, g) => s + (g.currentValue || 0), 0);
        const overallPct = totalTarget > 0 ? Math.round((totalCurrent / totalTarget) * 100) : 0;

        const el = (id) => document.getElementById(id);
        if (el('goal-overall-progress')) el('goal-overall-progress').textContent = overallPct + '%';
        if (el('goal-active-count')) el('goal-active-count').textContent = activeGoals.length;
        if (el('goal-completed-count')) el('goal-completed-count').textContent = completedGoals.length;
    },

    bindSalesGoalsEvents() {
        const addBtn = document.getElementById('btn-add-goal');
        const recalcBtn = document.getElementById('btn-recalculate-goals');

        if (addBtn) {
            addBtn.onclick = () => this.showGoalModal();
        }
        if (recalcBtn) {
            recalcBtn.onclick = () => this.recalculateGoals();
        }

        const container = document.getElementById('goals-list');
        if (!container) return;

        container.querySelectorAll('.btn-edit-goal').forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                this.showGoalModal(btn.dataset.id);
            };
        });

        container.querySelectorAll('.btn-delete-goal').forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                this.deleteGoal(btn.dataset.id);
            };
        });
    },

    async showGoalModal(goalId) {
        const isEdit = !!goalId;
        let goal = { name: '', type: 'revenue', targetValue: 0, period: 'quarterly', startDate: new Date().toISOString().slice(0, 10), endDate: '' };

        if (isEdit) {
            goal = await SalesGoalsDataSource.getGoal(goalId);
            // Data is already normalized to camelCase by SalesGoalsDataSource
            goal.targetValue = goal.targetValue || 0;
            goal.startDate = (goal.startDate || '').slice(0, 10);
            goal.endDate = (goal.endDate || '').slice(0, 10);
        }

        const modal = document.getElementById('modal-container');
        const title = document.getElementById('modal-title');
        title.textContent = isEdit ? 'Edit Sales Goal' : 'Add Sales Goal';

        modal.innerHTML = `
            <div class="modal-header">
                <h3 id="modal-title">${isEdit ? 'Edit Sales Goal' : 'Add Sales Goal'}</h3>
                <button id="modal-close" class="modal-close-btn" aria-label="Close modal">&times;</button>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label for="goal-name">Goal Name</label>
                    <input type="text" id="goal-name" class="form-control" value="${this._esc(goal.name)}" placeholder="e.g. Q1 Revenue Target">
                </div>
                <div class="form-group">
                    <label for="goal-type">Type</label>
                    <select id="goal-type" class="form-control">
                        <option value="revenue" ${goal.type === 'revenue' ? 'selected' : ''}>Revenue</option>
                        <option value="deals" ${goal.type === 'deals' ? 'selected' : ''}>Deals Closed</option>
                        <option value="contacts" ${goal.type === 'contacts' ? 'selected' : ''}>New Contacts</option>
                        <option value="activities" ${goal.type === 'activities' ? 'selected' : ''}>Activities</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="goal-target">Target Value</label>
                    <input type="number" id="goal-target" class="form-control" value="${goal.targetValue}" min="0" step="1">
                </div>
                <div class="form-group">
                    <label for="goal-period">Period</label>
                    <select id="goal-period" class="form-control">
                        <option value="monthly" ${goal.period === 'monthly' ? 'selected' : ''}>Monthly</option>
                        <option value="quarterly" ${goal.period === 'quarterly' ? 'selected' : ''}>Quarterly</option>
                        <option value="yearly" ${goal.period === 'yearly' ? 'selected' : ''}>Yearly</option>
                    </select>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label for="goal-start">Start Date</label>
                        <input type="date" id="goal-start" class="form-control" value="${goal.startDate}">
                    </div>
                    <div class="form-group">
                        <label for="goal-end">End Date</label>
                        <input type="date" id="goal-end" class="form-control" value="${goal.endDate}">
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button id="btn-cancel-goal" class="btn btn-secondary">Cancel</button>
                <button id="btn-save-goal" class="btn btn-primary">${isEdit ? 'Update' : 'Create'} Goal</button>
            </div>
        `;

        this.showModal();

        document.getElementById('modal-close').onclick = () => this.hideModal();
        document.getElementById('btn-cancel-goal').onclick = () => this.hideModal();
        document.getElementById('btn-save-goal').onclick = () => this.saveGoal(goalId);
    },

    async saveGoal(goalId) {
        const name = document.getElementById('goal-name').value.trim();
        const type = document.getElementById('goal-type').value;
        const targetValue = parseFloat(document.getElementById('goal-target').value) || 0;
        const period = document.getElementById('goal-period').value;
        const startDate = document.getElementById('goal-start').value;
        const endDate = document.getElementById('goal-end').value;

        if (!name) { this.showToast('Please enter a goal name.', 'warning'); return; }
        if (targetValue <= 0) { this.showToast('Target value must be greater than 0.', 'warning'); return; }
        if (!startDate || !endDate) { this.showToast('Please select start and end dates.', 'warning'); return; }
        if (endDate <= startDate) { this.showToast('End date must be after start date.', 'warning'); return; }

        try {
            const payload = { name, type, targetValue, period, startDate, endDate };
            if (goalId) {
                await SalesGoalsDataSource.updateGoal(goalId, payload);
                this.showToast('Goal updated successfully.', 'success');
            } else {
                await SalesGoalsDataSource.createGoal(payload);
                this.showToast('Goal created successfully.', 'success');
            }
            this.hideModal();
            await this.renderSalesGoals();
        } catch (e) {
            this.showToast('Failed to save goal: ' + e.message, 'error');
        }
    },

    async deleteGoal(goalId) {
        if (!confirm('Are you sure you want to delete this sales goal?')) return;
        try {
            await SalesGoalsDataSource.deleteGoal(goalId);
            this.showToast('Goal deleted.', 'success');
            await this.renderSalesGoals();
        } catch (e) {
            this.showToast('Failed to delete goal: ' + e.message, 'error');
        }
    },

    async recalculateGoals() {
        try {
            const btn = document.getElementById('btn-recalculate-goals');
            if (btn) { btn.disabled = true; btn.textContent = '⏳ Calculating...'; }
            await SalesGoalsDataSource.recalculateValues();
            this.showToast('Goals recalculated.', 'success');
            await this.renderSalesGoals();
            if (btn) { btn.disabled = false; btn.textContent = '🔄 Recalculate'; }
        } catch (e) {
            this.showToast('Recalculation failed: ' + e.message, 'error');
        }
    },

    // ── Sales Goals Helpers ──────────────────────────────────────────

    _goalTypeLabel(type) {
        const labels = { revenue: '💰 Revenue', deals: '🤝 Deals', contacts: '👤 Contacts', activities: '📋 Activities' };
        return labels[type] || type;
    },

    _fmtPeriod(p) {
        return p ? p.charAt(0).toUpperCase() + p.slice(1) : '—';
    },

    _fmtDate(d) {
        if (!d) return '—';
        return new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    },

    _fmtNum(n) {
        return (n || 0).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    },

    _goalValueLabel(value, type) {
        const v = Math.round(value || 0);
        if (type === 'revenue') return '$' + v.toLocaleString('en-US');
        return v.toLocaleString('en-US');
    },

    _esc(s) {
        const d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    },
};

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => App.init());

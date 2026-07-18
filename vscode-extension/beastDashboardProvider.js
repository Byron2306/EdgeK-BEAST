const vscode = require('vscode');

class BeastDashboardProvider {
    constructor() {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
        this.data = null;
        this.error = null;
        this.refreshInterval = null;
        this.startRefreshInterval();
    }

    startRefreshInterval() {
        // Refresh every 30 seconds
        this.refreshInterval = setInterval(() => {
            this.refresh();
        }, 30000);
    }

    stopRefreshInterval() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    async refresh() {
        try {
            const baseUrl = vscode.workspace.getConfiguration().get('edgekBeast.proxyUrl', 'http://127.0.0.1:8000');
            // We'll fetch data for each section. We'll do them in parallel.
            const [
                contextBudget,
                qualityCascade,
                activeRoute,
                activeWorkflow,
                riskPolicy,
                providerHealth,
                chronicleOutput,
                skillPromotion
            ] = await Promise.all([
                this.fetchJson(`${baseUrl}/context/budget`),
                this.fetchJson(`${baseUrl}/quality/cascade`),
                this.fetchJson(`${baseUrl}/route/active`),
                this.fetchJson(`${baseUrl}/workflow/active`),
                this.fetchJson(`${baseUrl}/policy/risk`),
                this.fetchJson(`${baseUrl}/providers/health`),
                this.fetchJson(`${baseUrl}/chronicle/output`),
                this.fetchJson(`${baseUrl}/skills/promotion`)
            ]);

            this.data = {
                contextBudget,
                qualityCascade,
                activeRoute,
                activeWorkflow,
                riskPolicy,
                providerHealth,
                chronicleOutput,
                skillPromotion
            };
            this.error = null;
        } catch (err) {
            console.error('Failed to refresh BEAST dashboard data:', err);
            this.data = null;
            this.error = err.toString();
        }
        this._onDidChangeTreeData.fire();
    }

    async fetchJson(url) {
        try {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return await response.json();
        } catch (err) {
            // If the gateway is not running, we might get a fetch error.
            // We'll return a special object indicating the gateway is down.
            return { error: `Gateway unavailable: ${err.message}` };
        }
    }

    getTreeItem(element) {
        return element;
    }

    getChildren(element) {
        if (!element) {
            // Root: return the top-level sections
            const sections = [
                { type: 'section', id: 'contextBudget', label: 'Context Budget' },
                { type: 'section', id: 'qualityCascade', label: 'Quality Cascade' },
                { type: 'section', id: 'activeRoute', label: 'Active Route Card' },
                { type: 'section', id: 'activeWorkflow', label: 'Active Workflow Card' },
                { type: 'section', id: 'riskPolicy', label: 'Risk Policy' },
                { type: 'section', id: 'providerHealth', label: 'Provider Health' },
                { type: 'section', id: 'chronicleOutput', label: 'Chronicle Output' },
                { type: 'section', id: 'skillPromotion', label: 'Skill Promotion Candidates' }
            ];
            return Promise.resolve(sections);
        }

        if (element.type === 'section') {
            // Return the children for the section based on its id
            switch (element.id) {
                case 'contextBudget':
                    return this.getContextBudgetChildren();
                case 'qualityCascade':
                    return this.getQualityCascadeChildren();
                case 'activeRoute':
                    return this.getActiveRouteChildren();
                case 'activeWorkflow':
                    return this.getActiveWorkflowChildren();
                case 'riskPolicy':
                    return this.getRiskPolicyChildren();
                case 'providerHealth':
                    return this.getProviderHealthChildren();
                case 'chronicleOutput':
                    return this.getChronicleOutputChildren();
                case 'skillPromotion':
                    return this.getSkillPromotionChildren();
                default:
                    return Promise.resolve([]);
            }
        }

        // For leaf items, return no children
        return Promise.resolve([]);
    }

    // Helper to create a tree item from a key-value pair
    createItem(label, value, collapsible = vscode.TreeItemCollapsibleState.None) {
        const item = new vscode.TreeItem(label, collapsible);
        item.tooltip = typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
        item.description = typeof value === 'string' && value.length > 50 ? value.substring(0, 50) + '...' : value;
        return item;
    }

    // Section-specific children getters
    async getContextBudgetChildren() {
        if (!this.data) {
            return [this.createItem('Loading...', null, vscode.TreeItemCollapsibleState.None)];
        }
        if (this.error) {
            return [this.createItem('Error', this.error, vscode.TreeItemCollapsibleState.None)];
        }
        const budget = this.data.contextBudget;
        if (budget.error) {
            return [this.createItem('Gateway Error', budget.error, vscode.TreeItemCollapsibleState.None)];
        }
        // Assume budget is an object with properties like maxTokens, usedTokens, etc.
        const items = [];
        for (const [key, value] of Object.entries(budget)) {
            items.push(this.createItem(key, value));
        }
        return items;
    }

    async getQualityCascadeChildren() {
        if (!this.data) {
            return [this.createItem('Loading...', null, vscode.TreeItemCollapsibleState.None)];
        }
        if (this.error) {
            return [this.createItem('Error', this.error, vscode.TreeItemCollapsibleState.None)];
        }
        const cascade = this.data.qualityCascade;
        if (cascade.error) {
            return [this.createItem('Gateway Error', cascade.error, vscode.TreeItemCollapsibleState.None)];
        }
        const items = [];
        for (const [key, value] of Object.entries(cascade)) {
            items.push(this.createItem(key, value));
        }
        return items;
    }

    async getActiveRouteChildren() {
        if (!this.data) {
            return [this.createItem('Loading...', null, vscode.TreeItemCollapsibleState.None)];
        }
        if (this.error) {
            return [this.createItem('Error', this.error, vscode.TreeItemCollapsibleState.None)];
        }
        const route = this.data.activeRoute;
        if (route.error) {
            return [this.createItem('Gateway Error', route.error, vscode.TreeItemCollapsibleState.None)];
        }
        const items = [];
        for (const [key, value] of Object.entries(route)) {
            items.push(this.createItem(key, value));
        }
        return items;
    }

    async getActiveWorkflowChildren() {
        if (!this.data) {
            return [this.createItem('Loading...', null, vscode.TreeItemCollapsibleState.None)];
        }
        if (this.error) {
            return [this.createItem('Error', this.error, vscode.TreeItemCollapsibleState.None)];
        }
        const workflow = this.data.activeWorkflow;
        if (workflow.error) {
            return [this.createItem('Gateway Error', workflow.error, vscode.TreeItemCollapsibleState.None)];
        }
        const items = [];
        for (const [key, value] of Object.entries(workflow)) {
            items.push(this.createItem(key, value));
        }
        return items;
    }

    async getRiskPolicyChildren() {
        if (!this.data) {
            return [this.createItem('Loading...', null, vscode.TreeItemCollapsibleState.None)];
        }
        if (this.error) {
            return [this.createItem('Error', this.error, vscode.TreeItemCollapsibleState.None)];
        }
        const policy = this.data.riskPolicy;
        if (policy.error) {
            return [this.createItem('Gateway Error', policy.error, vscode.TreeItemCollapsibleState.None)];
        }
        const items = [];
        for (const [key, value] of Object.entries(policy)) {
            items.push(this.createItem(key, value));
        }
        return items;
    }

    async getProviderHealthChildren() {
        if (!this.data) {
            return [this.createItem('Loading...', null, vscode.TreeItemCollapsibleState.None)];
        }
        if (this.error) {
            return [this.createItem('Error', this.error, vscode.TreeItemCollapsibleState.None)];
        }
        const health = this.data.providerHealth;
        if (health.error) {
            return [this.createItem('Gateway Error', health.error, vscode.TreeItemCollapsibleState.None)];
        }
        // Assume health is an object where each key is a provider name and value is its status
        const items = [];
        for (const [provider, status] of Object.entries(health)) {
            items.push(this.createItem(provider, status));
        }
        return items;
    }

    async getChronicleOutputChildren() {
        if (!this.data) {
            return [this.createItem('Loading...', null, vscode.TreeItemCollapsibleState.None)];
        }
        if (this.error) {
            return [this.createItem('Error', this.error, vscode.TreeItemCollapsibleState.None)];
        }
        const output = this.data.chronicleOutput;
        if (output.error) {
            return [this.createItem('Gateway Error', output.error, vscode.TreeItemCollapsibleState.None)];
        }
        // Assume output is a string or an object; we'll just show it as a single item for now
        return [this.createItem('Chronicle Output', output, vscode.TreeItemCollapsibleState.None)];
    }

    async getSkillPromotionChildren() {
        if (!this.data) {
            return [this.createItem('Loading...', null, vscode.TreeItemCollapsibleState.None)];
        }
        if (this.error) {
            return [this.createItem('Error', this.error, vscode.TreeItemCollapsibleState.None)];
        }
        const promotion = this.data.skillPromotion;
        if (promotion.error) {
            return [this.createItem('Gateway Error', promotion.error, vscode.TreeItemCollapsibleState.None)];
        }
        // Assume promotion is an array of skill names or objects
        const items = [];
        if (Array.isArray(promotion)) {
            promotion.forEach((skill, index) => {
                items.push(this.createItem(`Skill ${index + 1}`, skill));
            });
        } else {
            for (const [key, value] of Object.entries(promotion)) {
                items.push(this.createItem(key, value));
            }
        }
        return items;
    }

    dispose() {
        this.stopRefreshInterval();
    }
}

module.exports = {
    BeastDashboardProvider
};

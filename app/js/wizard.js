const Wizard = {
  _selectedDefinitionId: null,
  _generatedXml: null,
  _generatedSvg: null,
  _processKey: null,

  _esc(str) {
    if (str == null) return '';
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(String(str)));
    return div.innerHTML;
  },

  _notice(msg) {
    const el = document.getElementById('wizard-notice');
    if (!el) return;
    el.textContent = msg;
    el.style.display = 'block';
    setTimeout(() => { el.style.display = 'none'; }, 3000);
  },

  _toast(msg, isError = false) {
    const el = document.getElementById('wizard-toast');
    if (!el) return;
    el.textContent = msg;
    el.className = isError ? 'toast-error' : 'toast-success';
    el.style.display = 'block';
    setTimeout(() => { el.style.display = 'none'; }, 3000);
  },

  async init() {
    const container = document.getElementById('wizard-definitions');
    if (!container) return;
    this._bindEvents();
    await this.loadDefinitions();
  },

  _bindEvents() {
    document.getElementById('wizard-create-def-btn')?.addEventListener('click', () => this.createDefinition());
    document.getElementById('wizard-create-step-btn')?.addEventListener('click', () => this.createStep());
    document.getElementById('wizard-create-flow-btn')?.addEventListener('click', () => this.createFlow());
    document.getElementById('wizard-generate')?.addEventListener('click', () => this.generate());
    document.getElementById('wizard-download-xml')?.addEventListener('click', () => this.downloadXml());
    document.getElementById('wizard-download-svg')?.addEventListener('click', () => this.downloadSvg());
  },

  async refresh() {
    if (this._selectedDefinitionId) {
      await this.loadSteps();
      await this.loadFlows();
    } else {
      await this.loadDefinitions();
    }
  },

  _renderDefinitionCard(def) {
    return `
      <div class="wizard-card" data-id="${this._esc(def.id)}">
        <h3>${this._esc(def.name)}</h3>
        <p><strong>Key:</strong> ${this._esc(def.process_key)}</p>
        <p><strong>Version:</strong> ${this._esc(def.version)}</p>
        <p><strong>Status:</strong> ${this._esc(def.status)}</p>
      </div>
    `;
  },

  async loadDefinitions() {
    const res = await ApiClient.get('/process-definitions');
    if (!res.ok) return;
    const container = document.getElementById('wizard-definitions');
    if (!container) return;
    let html = '';
    for (const def of res.data) {
      html += this._renderDefinitionCard(def);
    }
    container.innerHTML = html;
    container.querySelectorAll('.wizard-card').forEach((card) => {
      card.addEventListener('click', () => this.selectDefinition(card.dataset.id));
    });
  },

  async createDefinition() {
    const nameEl = document.getElementById('wizard-def-name');
    const keyEl = document.getElementById('wizard-def-key');
    const name = nameEl.value.trim();
    const processKey = keyEl ? keyEl.value.trim() : null;
    if (!name) return this._toast('Name is required', true);

    const res = await ApiClient.post('/process-definitions', { name, process_key: processKey });
    if (res.ok) {
      nameEl.value = '';
      if (keyEl) keyEl.value = '';
      this._notice('Definition created');
      await this.loadDefinitions();
    } else {
      this._toast(res.detail || 'Failed to create definition', true);
    }
  },

  selectDefinition(id) {
    this._selectedDefinitionId = id;
    document.querySelectorAll('.wizard-card').forEach((card) => {
      card.classList.toggle('selected', card.dataset.id === id);
    });
    this.refresh();
  },

  _renderStepRow(step) {
    return `
      <div class="wizard-row" data-id="${this._esc(step.id)}">
        <span>${this._esc(step.ordinal)}</span>
        <span>${this._esc(step.name)}</span>
        <span>${this._esc(step.step_key)}</span>
        <span>${this._esc(step.step_type)}</span>
        <button class="delete-step-btn" data-id="${step.id}">Delete</button>
      </div>
    `;
  },

  async loadSteps() {
    const res = await ApiClient.get('/process-steps');
    if (!res.ok) return;
    const container = document.getElementById('wizard-steps');
    if (!container) return;
    const steps = res.data.filter(s => s.process_definition_id === this._selectedDefinitionId);
    let html = '';
    for (const step of steps) {
      html += this._renderStepRow(step);
    }
    container.innerHTML = html;
    container.querySelectorAll('.delete-step-btn').forEach((btn) => {
      btn.addEventListener('click', () => this.deleteStep(btn.dataset.id));
    });
    this._refreshFlowSelects(steps);
  },

  _refreshFlowSelects(steps) {
    const sourceEl = document.getElementById('wizard-flow-source');
    const targetEl = document.getElementById('wizard-flow-target');
    if (!sourceEl || !targetEl) return;
    const options = steps.map(s => `<option value="${this._esc(s.step_key)}">${this._esc(s.step_key)}</option>`).join('');
    sourceEl.innerHTML = '<option value="">Select source</option>' + options;
    targetEl.innerHTML = '<option value="">Select target</option>' + options;
  },

  async createStep() {
    const name = document.getElementById('wizard-step-name').value.trim();
    const stepKey = document.getElementById('wizard-step-key').value.trim();
    const ordinalInput = document.getElementById('wizard-step-ordinal').value;
    const stepType = document.getElementById('wizard-step-type').value;
    const serviceImpl = document.getElementById('wizard-step-service-impl')?.value.trim() || null;
    const groups = document.getElementById('wizard-step-groups')?.value.trim() || null;
    const formKey = document.getElementById('wizard-step-form-key')?.value.trim() || null;

    if (!name || !stepKey) return this._toast('Name and key are required', true);

    const payload = {
      process_definition_id: this._selectedDefinitionId,
      name,
      step_key: stepKey,
      ordinal: Number(ordinalInput),
      step_type: stepType,
      service_impl: serviceImpl,
      candidate_groups: groups,
      form_key: formKey,
    };

    const res = await ApiClient.post('/process-steps', payload);
    if (res.ok) {
      document.getElementById('wizard-step-name').value = '';
      document.getElementById('wizard-step-key').value = '';
      document.getElementById('wizard-step-ordinal').value = '';
      this._notice('Step created');
      await this.loadSteps();
    } else {
      this._toast(res.detail || 'Failed to create step', true);
    }
  },

  async deleteStep(id) {
    const res = await ApiClient.delete(`/process-steps/${id}`);
    if (res.ok) {
      this._notice('Step deleted');
      await this.loadSteps();
    } else {
      this._toast(res.detail || 'Failed to delete step', true);
    }
  },

  _renderFlowRow(flow) {
    const defaultMarker = flow.is_default ? ' [DEFAULT]' : '';
    return `
      <div class="wizard-row" data-id="${this._esc(flow.id)}">
        <span>${this._esc(flow.name)}</span>
        <span>${this._esc(flow.flow_key)}</span>
        <span>${this._esc(flow.source_step)} → ${this._esc(flow.target_step)}</span>
        <span>${defaultMarker}</span>
        <button class="delete-flow-btn" data-id="${flow.id}">Delete</button>
      </div>
    `;
  },

  async loadFlows() {
    const res = await ApiClient.get('/sequence-flows');
    if (!res.ok) return;
    const container = document.getElementById('wizard-flows');
    if (!container) return;
    const flows = res.data.filter(f => f.process_definition_id === this._selectedDefinitionId);
    let html = '';
    for (const flow of flows) {
      html += this._renderFlowRow(flow);
    }
    container.innerHTML = html;
    container.querySelectorAll('.delete-flow-btn').forEach((btn) => {
      btn.addEventListener('click', () => this.deleteFlow(btn.dataset.id));
    });
  },

  async createFlow() {
    const name = document.getElementById('wizard-flow-name').value.trim();
    const flowKey = document.getElementById('wizard-flow-key').value.trim();
    const sourceStep = document.getElementById('wizard-flow-source').value;
    const targetStep = document.getElementById('wizard-flow-target').value;
    const conditionExpression = document.getElementById('wizard-flow-condition')?.value.trim() || null;
    const isDefault = document.getElementById('wizard-flow-default')?.checked || false;

    if (!name || !flowKey) return this._toast('Name and key are required', true);

    const payload = {
      process_definition_id: this._selectedDefinitionId,
      name,
      flow_key: flowKey,
      source_step: sourceStep,
      target_step: targetStep,
      condition_expression: conditionExpression,
      is_default: isDefault,
    };

    const res = await ApiClient.post('/sequence-flows', payload);
    if (res.ok) {
      document.getElementById('wizard-flow-name').value = '';
      document.getElementById('wizard-flow-key').value = '';
      this._notice('Flow created');
      await this.loadFlows();
    } else {
      this._toast(res.detail || 'Failed to create flow', true);
    }
  },

  async deleteFlow(id) {
    const res = await ApiClient.delete(`/sequence-flows/${id}`);
    if (res.ok) {
      this._notice('Flow deleted');
      await this.loadFlows();
    } else {
      this._toast(res.detail || 'Failed to delete flow', true);
    }
  },

  async generate() {
    const res = await ApiClient.post(`/process-definitions/${this._selectedDefinitionId}/generate`);
    if (res.ok) {
      this._generatedXml = res.data.bpmn_xml;
      this._generatedSvg = res.data.svg;
      this._processKey = res.data.process_key;
      document.getElementById('wizard-svg').innerHTML = this._generatedSvg;
      const xmlBtn = document.getElementById('wizard-download-xml');
      const svgBtn = document.getElementById('wizard-download-svg');
      if (xmlBtn) xmlBtn.disabled = false;
      if (svgBtn) svgBtn.disabled = false;
    } else {
      this._toast(res.detail || 'Generation failed', true);
    }
  },

  downloadXml() {
    if (!this._generatedXml || !this._processKey) return;
    const blob = new Blob([this._generatedXml], { type: 'application/xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${this._processKey}.bpmn`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  downloadSvg() {
    if (!this._generatedSvg || !this._processKey) return;
    const blob = new Blob([this._generatedSvg], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${this._processKey}.svg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  _stepTypeOptions() {
    return `
      <option value="start">Start</option>
      <option value="end">End</option>
      <option value="user">User</option>
      <option value="service">Service</option>
      <option value="gateway">Gateway</option>
    `;
  }
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Wizard };
}

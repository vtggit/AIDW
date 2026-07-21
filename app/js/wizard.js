/* eslint-disable no-unused-vars */
'use strict';

const Wizard = (() => {
    /* ------------------------------------------------------------------ */
    /*  Internal state                                                    */
    /* ------------------------------------------------------------------ */
    let _selectedDefinitionId = null;
    let _stagedXml = null;
    let _stagedSvg = null;
    let _processKey = null;

    const STEP_TYPE_OPTIONS = `<option value="start">Start</option>
<option value="end">End</option>
<option value="user">User</option>
<option value="service">Service</option>
<option value="gateway">Gateway</option>`;

    /* ------------------------------------------------------------------ */
    /*  Helpers                                                           */
    /* ------------------------------------------------------------------ */
    function _esc(str) {
        if (str == null) return '';
        const s = String(str);
        return s.replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
    }

    function _notice(message) {
        const el = document.getElementById('wizard-notice');
        if (el) {
            el.textContent = message;
            el.style.display = 'block';
            setTimeout(() => { el.style.display = 'none'; }, 4000);
        }
    }

    function _toast(message, isError) {
        const container = document.getElementById('wizard-toast-container') || document.body;
        const toast = document.createElement('div');
        toast.className = `wizard-toast wizard-toast-${isError ? 'error' : 'info'}`;
        toast.textContent = message;
        toast.style.position = 'fixed';
        toast.style.top = '1rem';
        toast.style.right = '1rem';
        toast.style.padding = '0.75rem 1.25rem';
        toast.style.borderRadius = '4px';
        toast.style.color = '#fff';
        toast.style.background = isError ? '#dc3545' : '#28a745';
        toast.style.zIndex = '9999';
        container.appendChild(toast);
        setTimeout(() => { toast.remove(); }, 5000);
    }

    /* ------------------------------------------------------------------ */
    /*  Render helpers                                                    */
    /* ------------------------------------------------------------------ */
    function _renderDefinitionCard(def) {
        return `
            <div class="wizard-def-card" data-id="${_esc(def.id)}">
                <h4>${_esc(def.name)}</h4>
                <p><strong>Key:</strong> ${_esc(def.process_key)}</p>
                <p><strong>Version:</strong> ${_esc(def.version)}</p>
                <p><strong>Status:</strong> ${_esc(def.status)}</p>
            </div>`;
    }

    function _renderStepRow(step) {
        return `
            <tr data-id="${_esc(step.id)}">
                <td>${_esc(step.ordinal)}</td>
                <td>${_esc(step.name)}</td>
                <td>${_esc(step.step_key)}</td>
                <td>${_esc(step.step_type)}</td>
                <td><button class="wizard-delete-step" data-id="${_esc(step.id)}">Delete</button></td>
            </tr>`;
    }

    function _renderFlowRow(flow) {
        const defaultMarker = flow.is_default ? ' ★' : '';
        return `
            <tr data-id="${_esc(flow.id)}">
                <td>${_esc(flow.name)}</td>
                <td>${_esc(flow.flow_key)}</td>
                <td>${_esc(flow.source_step_key)} → ${_esc(flow.target_step_key)}${defaultMarker}</td>
                <td><button class="wizard-delete-flow" data-id="${_esc(flow.id)}">Delete</button></td>
            </tr>`;
    }

    /* ------------------------------------------------------------------ */
    /*  Public API                                                        */
    /* ------------------------------------------------------------------ */
    function init() {
        const container = document.getElementById('wizard-definitions');
        if (!container) return;

        loadDefinitions().catch(err => _toast(String(err), true));

        const createBtn = document.getElementById('wizard-create-definition');
        if (createBtn) {
            createBtn.addEventListener('click', () => {
                createDefinition().catch(err => _toast(String(err), true));
            });
        }

        const generateBtn = document.getElementById('wizard-generate');
        if (generateBtn) {
            generateBtn.addEventListener('click', () => {
                generate().catch(err => _toast(String(err), true));
            });
        }

        const downloadXmlBtn = document.getElementById('wizard-download-xml');
        if (downloadXmlBtn) {
            downloadXmlBtn.addEventListener('click', () => { downloadXml(); });
        }

        const downloadSvgBtn = document.getElementById('wizard-download-svg');
        if (downloadSvgBtn) {
            downloadSvgBtn.addEventListener('click', () => { downloadSvg(); });
        }
    }

    function refresh() {
        if (_selectedDefinitionId != null) {
            loadSteps().catch(err => _toast(String(err), true));
            loadFlows().catch(err => _toast(String(err), true));
        } else {
            loadDefinitions().catch(err => _toast(String(err), true));
        }
    }

    async function loadDefinitions() {
        const defs = await ApiClient.get('/process-definitions');
        const container = document.getElementById('wizard-definitions');
        if (!container) return;

        let html = '';
        for (const def of defs) {
            html += _renderDefinitionCard(def);
        }
        container.innerHTML = html;

        container.querySelectorAll('.wizard-def-card').forEach(card => {
            card.addEventListener('click', () => {
                const id = parseInt(card.dataset.id, 10);
                selectDefinition(id).catch(err => _toast(String(err), true));
            });
        });

        _notice(`Loaded ${defs.length} process definitions`);
    }

    async function createDefinition() {
        const nameEl = document.getElementById('wizard-def-name');
        const keyEl = document.getElementById('wizard-def-key');
        const name = nameEl ? nameEl.value.trim() : '';
        const processKey = keyEl ? keyEl.value.trim() : null;

        if (!name) {
            _toast('Definition name is required', true);
            return;
        }

        const body = { name };
        if (processKey) body.process_key = processKey;

        await ApiClient.post('/process-definitions', body);

        if (nameEl) nameEl.value = '';
        if (keyEl) keyEl.value = '';

        _notice('Process definition created');
        return loadDefinitions();
    }

    async function selectDefinition(id) {
        _selectedDefinitionId = id;

        document.querySelectorAll('.wizard-def-card').forEach(card => {
            if (parseInt(card.dataset.id, 10) === id) {
                card.classList.add('selected');
            } else {
                card.classList.remove('selected');
            }
        });

        _notice(`Selected definition ${id}`);
        return refresh();
    }

    async function loadSteps() {
        const steps = await ApiClient.get('/process-steps');
        const container = document.getElementById('wizard-steps');
        if (!container) return;

        const filtered = Array.isArray(steps) ? steps.filter(s => s.process_definition_id === _selectedDefinitionId) : [];

        let html = '<tbody>';
        for (const step of filtered) {
            html += _renderStepRow(step);
        }
        html += '</tbody>';
        container.innerHTML = html;

        container.querySelectorAll('.wizard-delete-step').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id, 10);
                deleteStep(id).catch(err => _toast(String(err), true));
            });
        });

        rebuildFlowSelects(filtered);
        _notice(`Loaded ${filtered.length} steps`);
    }

    function rebuildFlowSelects(steps) {
        const sourceEl = document.getElementById('wizard-flow-source');
        const targetEl = document.getElementById('wizard-flow-target');
        if (!sourceEl || !targetEl) return;

        const options = steps.map(s => `<option value="${_esc(s.step_key)}">${_esc(s.step_key)}</option>`).join('');

        sourceEl.innerHTML = '<option value="">— select —</option>' + options;
        targetEl.innerHTML = '<option value="">— select —</option>' + options;
    }

    async function createStep() {
        const nameEl = document.getElementById('wizard-step-name');
        const keyEl = document.getElementById('wizard-step-key');
        const ordinalEl = document.getElementById('wizard-step-ordinal');
        const typeEl = document.getElementById('wizard-step-type');
        const serviceImplEl = document.getElementById('wizard-step-service-impl');
        const groupsEl = document.getElementById('wizard-step-groups');
        const formKeyEl = document.getElementById('wizard-step-form-key');

        const name = nameEl ? nameEl.value.trim() : '';
        if (!name) {
            _toast('Step name is required', true);
            return;
        }

        const body = {
            process_definition_id: _selectedDefinitionId,
            name,
            step_key: keyEl ? keyEl.value.trim() : null,
            ordinal: ordinalEl ? parseInt(ordinalEl.value, 10) || 0 : 0,
            step_type: typeEl ? typeEl.value : 'start',
        };

        if (serviceImplEl && serviceImplEl.value.trim()) body.service_impl = serviceImplEl.value.trim();
        if (groupsEl && groupsEl.value.trim()) body.groups = groupsEl.value.trim();
        if (formKeyEl && formKeyEl.value.trim()) body.form_key = formKeyEl.value.trim();

        await ApiClient.post('/process-steps', body);

        if (nameEl) nameEl.value = '';
        if (keyEl) keyEl.value = '';
        if (ordinalEl) ordinalEl.value = '';
        if (typeEl) typeEl.selectedIndex = 0;
        if (serviceImplEl) serviceImplEl.value = '';
        if (groupsEl) groupsEl.value = '';
        if (formKeyEl) formKeyEl.value = '';

        _notice('Step created');
        return loadSteps();
    }

    async function deleteStep(id) {
        await ApiClient.delete(`/process-steps/${id}`);
        _notice('Step deleted');
        return loadSteps();
    }

    async function loadFlows() {
        const flows = await ApiClient.get('/sequence-flows');
        const container = document.getElementById('wizard-flows');
        if (!container) return;

        const filtered = Array.isArray(flows) ? flows.filter(f => f.process_definition_id === _selectedDefinitionId) : [];

        let html = '<tbody>';
        for (const flow of filtered) {
            html += _renderFlowRow(flow);
        }
        html += '</tbody>';
        container.innerHTML = html;

        container.querySelectorAll('.wizard-delete-flow').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id, 10);
                deleteFlow(id).catch(err => _toast(String(err), true));
            });
        });

        _notice(`Loaded ${filtered.length} flows`);
    }

    async function createFlow() {
        const nameEl = document.getElementById('wizard-flow-name');
        const keyEl = document.getElementById('wizard-flow-key');
        const sourceEl = document.getElementById('wizard-flow-source');
        const targetEl = document.getElementById('wizard-flow-target');
        const conditionEl = document.getElementById('wizard-flow-condition');
        const defaultCheckbox = document.getElementById('wizard-flow-default');

        const name = nameEl ? nameEl.value.trim() : '';
        if (!name) {
            _toast('Flow name is required', true);
            return;
        }

        const body = {
            process_definition_id: _selectedDefinitionId,
            name,
            flow_key: keyEl ? keyEl.value.trim() : null,
            source_step_key: sourceEl ? sourceEl.value : '',
            target_step_key: targetEl ? targetEl.value : '',
        };

        if (conditionEl && conditionEl.value.trim()) body.condition = conditionEl.value.trim();
        if (defaultCheckbox) body.is_default = defaultCheckbox.checked;

        await ApiClient.post('/sequence-flows', body);

        if (nameEl) nameEl.value = '';
        if (keyEl) keyEl.value = '';
        if (sourceEl) sourceEl.selectedIndex = 0;
        if (targetEl) targetEl.selectedIndex = 0;
        if (conditionEl) conditionEl.value = '';
        if (defaultCheckbox) defaultCheckbox.checked = false;

        _notice('Flow created');
        return loadFlows();
    }

    async function deleteFlow(id) {
        await ApiClient.delete(`/sequence-flows/${id}`);
        _notice('Flow deleted');
        return loadFlows();
    }

    async function generate() {
        if (_selectedDefinitionId == null) {
            _toast('No definition selected', true);
            return;
        }

        const result = await ApiClient.post(`/process-definitions/${_selectedDefinitionId}/generate`);

        const svgContainer = document.getElementById('wizard-svg');
        if (svgContainer && result.svg) {
            svgContainer.innerHTML = result.svg;
        }

        _stagedXml = result.bpmn_xml || null;
        _processKey = result.process_key || 'process';
        _stagedSvg = result.svg || null;

        const xmlBtn = document.getElementById('wizard-download-xml');
        const svgBtn = document.getElementById('wizard-download-svg');
        if (xmlBtn) xmlBtn.disabled = false;
        if (svgBtn) svgBtn.disabled = false;

        _notice('Diagram generated successfully');
    }

    function downloadXml() {
        if (!_stagedXml || !_processKey) return;
        const blob = new Blob([_stagedXml], { type: 'application/xml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${_processKey}.bpmn`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function downloadSvg() {
        if (!_stagedSvg || !_processKey) return;
        const blob = new Blob([_stagedSvg], { type: 'image/svg+xml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${_processKey}.svg`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    /* ------------------------------------------------------------------ */
    /*  Return public interface                                           */
    /* ------------------------------------------------------------------ */
    return {
        init,
        refresh,
        loadDefinitions,
        createDefinition,
        selectDefinition,
        loadSteps,
        createStep,
        deleteStep,
        loadFlows,
        createFlow,
        deleteFlow,
        generate,
        downloadXml,
        downloadSvg,
        _esc,
        _notice,
        _toast,
    };
})();

if (typeof module !== 'undefined' && module.exports) { module.exports = { Wizard }; }

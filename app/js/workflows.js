/**
 * Workflows UI — BPMN authoring canvas (bpmn.io / bpmn-js, vendored).
 *
 * Per the ratified adoption ADR (AIDW#189): process authoring is bpmn-js embedded in
 * AIDW's OWN UI, producing standard BPMN 2.0 XML that the Flowable OSS engine executes —
 * never the Flowable/Camunda enterprise modeler. This slice is AUTHORING ONLY: new /
 * open a .bpmn file / export XML+SVG. Deploying an authored definition to the engine is a
 * separate, GOVERNED seam (arbitrary BPMN can carry script tasks / service classes /
 * external URLs — a materially larger trust surface than the opaque-reference allowlist)
 * and lands later through CodeAgent + a trust-surface ratification.
 *
 * VTG-ADOPT-001 attribution: the bpmn.io watermark bpmn-js renders (bottom-right, links
 * to bpmn.io) MUST stay fully visible and unaltered. workflows.css keeps the toolbar clear of it
 * AND carries an explicit rule restoring the mark's intrinsic 53x21, because the canvas fill rule
 * is a descendant selector that also matches the mark's own <svg>. workflows.spec.js pins the
 * rendered size against that intrinsic size so a stretch/clip regression is caught rather than
 * shipping silently. See app/vendor/bpmn-js/LICENSE.
 *
 * House conventions (mirrors sources.js / warehouse.js): pure helpers, everything
 * escaped, toast feedback, module.exports guard for Playwright.
 */
const Workflows = {
    _modeler: null,

    // A minimal, valid BPMN 2.0 diagram (with DI) so the editor opens on something.
    STARTER_BPMN:
        '<?xml version="1.0" encoding="UTF-8"?>\n' +
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" ' +
        'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" ' +
        'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" ' +
        'id="Definitions_aidw" targetNamespace="http://aidw/bpmn">\n' +
        '  <bpmn:process id="aidwProcess" name="New AIDW process" isExecutable="true">\n' +
        '    <bpmn:startEvent id="StartEvent_1" name="Start" />\n' +
        '  </bpmn:process>\n' +
        '  <bpmndi:BPMNDiagram id="BPMNDiagram_1">\n' +
        '    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="aidwProcess">\n' +
        '      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">\n' +
        '        <dc:Bounds x="160" y="120" width="36" height="36" />\n' +
        '      </bpmndi:BPMNShape>\n' +
        '    </bpmndi:BPMNPlane>\n' +
        '  </bpmndi:BPMNDiagram>\n' +
        '</bpmn:definitions>\n',

    async init() {
        const canvas = document.getElementById('bpmn-canvas');
        if (!canvas) return;
        if (typeof BpmnJS === 'undefined') {
            canvas.innerHTML = this._notice(
                'The BPMN editor bundle failed to load (vendor/bpmn-js).', true);
            return;
        }
        this._modeler = new BpmnJS({ container: canvas });
        this._wire('bpmn-new', 'click', () => this.newDiagram());
        this._wire('bpmn-download', 'click', () => this.downloadXml());
        this._wire('bpmn-download-svg', 'click', () => this.downloadSvg());
        const opener = document.getElementById('bpmn-open');
        if (opener) opener.addEventListener('change', (e) => this._openFile(e));
        await this.newDiagram();
    },

    _wire(id, evt, fn) {
        const el = document.getElementById(id);
        if (el) el.addEventListener(evt, fn);
    },

    async newDiagram() {
        try {
            await this._modeler.importXML(this.STARTER_BPMN);
            this._fit();
        } catch (e) {
            this._toast('Could not initialise the editor.', true);
        }
    },

    async _openFile(e) {
        const file = e.target.files && e.target.files[0];
        e.target.value = '';                       // allow re-opening the same file
        if (!file) return;
        let xml;
        try { xml = await file.text(); } catch (_) { return this._toast('Could not read the file.', true); }
        try {
            await this._modeler.importXML(xml);
            this._fit();
            this._toast('Imported ' + this._esc(file.name));
        } catch (err) {
            this._toast('Import failed — not valid BPMN 2.0 XML.', true);
        }
    },

    async downloadXml() {
        if (!this._modeler) return;
        try {
            const out = await this._modeler.saveXML({ format: true });
            this._download(out.xml, 'process.bpmn', 'application/xml');
            this._toast('Downloaded process.bpmn');
        } catch (e) {
            this._toast('Export failed.', true);
        }
    },

    async downloadSvg() {
        if (!this._modeler) return;
        try {
            const out = await this._modeler.saveSVG();
            this._download(out.svg, 'process.svg', 'image/svg+xml');
            this._toast('Downloaded process.svg');
        } catch (e) {
            this._toast('SVG export failed.', true);
        }
    },

    _fit() {
        try { this._modeler.get('canvas').zoom('fit-viewport'); } catch (_) { /* noop */ }
    },

    _download(text, name, mime) {
        const blob = new Blob([text], { type: mime });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    },

    _notice(text, isError) {
        return `<p class="wh-sub" style="${isError ? 'color:#e05555;' : ''}">${this._esc(text)}</p>`;
    },

    _esc(s) {
        return String(s)
            .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
    },

    _toast(msg, isError) {
        const el = document.getElementById('toast');
        if (!el) return;
        el.textContent = msg;
        el.hidden = false;
        el.classList.toggle('wh-err', !!isError);
        clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
    },
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Workflows };
}

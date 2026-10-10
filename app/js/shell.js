/**
 * AIDW application shell — the fixed-height two-column layout from
 * docs/design/design-system.md ("The application shell").
 *
 *   • a 100vh shell of two columns: the dark sidebar (--sidebar-width,
 *     232 px) and the main area
 *   • the sidebar, top to bottom: the AIDW mark and name, the primary
 *     navigation (Dashboards, then one item per Studio tool), and at the
 *     bottom the page's existing #auth-status element
 *   • the main area: the page title ("Dashboards" or "Studio · <tool
 *     name>") with a one-line subtitle, then the scrollable content (the
 *     existing main.wh-main) — at desktop width the document never
 *     scrolls, only this content region does, and only when the shown
 *     tool is taller than it
 *   • at 900 px and below the sidebar becomes a top bar (css/shell.css)
 *
 * The sidebar markup is defined ONCE in _sidebarHtml() and rendered into
 * both Dashboards (index.html) and Studio (studio.html) — the pages carry
 * no duplicated navigation HTML.  The legacy top header (the old
 * "Configure" / "← Dashboard" links) is replaced by this sidebar and
 * removed from the live DOM on boot; #auth-status is kept and moved to
 * the bottom of the sidebar.
 *
 * Studio shows one tool at a time (issue #769): the main area renders
 * the tool named by the ?panel= query — or Data sources when the param
 * is absent, unknown, or names a tool the user's role hides.  Every
 * other usable tool's section(s) carry the `hidden` attribute; the
 * shell owns this visibility of the .wh-panel sections and enforces it
 * after boot: a MutationObserver re-applies the hidden state whenever a
 * module drifts it, and it re-resolves the shown tool (falling back to
 * Data sources) when a module removes the shown tool's section from the
 * DOM.  css/shell.css keeps an inactive section invisible even when a
 * panel's own CSS sets an explicit display value.  While a section is
 * not the shown tool it also declares data-panel-empty-ok, so the
 * liveness check reads its (unrendered) blankness as intended, not as a
 * defect; the marker is removed the moment the tool is shown.  Load
 * sequences is one tool over two sections (Load sequences + Run
 * history).  A tool the user's role hides keeps its own fail-closed
 * rendering (its module removes or downgrades the section); the shell
 * never re-shows it.
 *
 * Switching tools is in place: a sidebar click rewrites ?panel= via
 * pushState WITHOUT a page load, moves aria-current="page" to the tool's
 * item, resets the main region's scroll to the top and updates the title
 * to "Studio · <tool name>"; Back/forward (popstate) restore the tool
 * the URL names.  Hidden tools keep their DOM and state — ids,
 * data-testid, data-panel and data-action hooks, loaded data and form
 * input — so switching back shows them exactly as they were.
 *
 * On the Dashboards page the Studio items keep their hrefs and do a
 * genuine page load to studio.html?panel=<name>; on index.html the
 * Dashboards item carries aria-current="page".
 *
 * Role-gated items (data-requires-role) follow the app's existing
 * fail-closed convention for admin-only controls: the element leaves the
 * DOM until the signed-in user holds the required role, so no element
 * carrying data-requires-role="admin" survives for a non-admin.
 */
(function () {
  "use strict";

  var PAGES = {
    dashboards: {
      title: "Dashboards",
      subtitle: "Accepted suggestions land here as dashboard items. Click a card to open the data behind it."
    },
    studio: {
      title: "Studio",
      subtitle: "Configure data sources, suggestions, PII triage, processes, loads, retention and ingestion."
    }
  };

  // One Studio tool per nav item, in sidebar order — the single source
  // of truth for which panel names the deep link and the popstate
  // handler know.  Each tool names the panel section(s) it owns (a tool
  // may span several, as Load sequences does) and, for role-restricted
  // tools, the role that may use it.
  var STUDIO_PANELS = [
    { name: "sources", label: "Data sources", sections: ["sources"] },
    { name: "suggestions", label: "Suggestions", sections: ["suggestions"] },
    { name: "pii", label: "PII flags", sections: ["pii"] },
    { name: "wizard", label: "Process wizard", sections: ["wizard"] },
    { name: "sequences", label: "Load sequences", sections: ["sequences", "sequence-runs"] },
    { name: "retention", label: "Data retention", sections: ["retention"] },
    { name: "ingestion", label: "Ingestion", sections: ["ingestion"] },
    { name: "feedkeys", label: "Feed keys", sections: ["feedkeys"], requiresRole: "admin" },
    { name: "audit", label: "Audit history", sections: ["audit"], requiresRole: "admin" }
  ];

  var Shell = {
    _built: false,
    _page: "dashboards",
    _activeTool: null,
    _gatedItem: null,
    _gatedRole: null,
    _gatedNext: null,

    /**
     * Render the shell around the page's existing content.  `page` is
     * "dashboards" (index.html) or "studio" (studio.html); when omitted
     * it is read from <body data-aidw-page>.
     */
    init: function (page) {
      if (this._built) return;
      this._built = true;
      if (!page) {
        page = document.body ? document.body.getAttribute("data-aidw-page") : null;
      }
      this._page = PAGES[page] ? page : "dashboards";
      var conf = PAGES[this._page];

      var shell = document.createElement("div");
      shell.className = "aidw-shell";

      var sidebar = document.createElement("aside");
      sidebar.className = "aidw-sidebar";
      sidebar.setAttribute("data-testid", "sidebar");
      sidebar.innerHTML = this._sidebarHtml();
      this._moveAuthStatus(sidebar);
      this._detachGatedItem(sidebar); // fail-closed until the user is known

      var main = document.createElement("div");
      main.className = "aidw-main";
      main.innerHTML =
        '<header class="aidw-main-header">' +
        '<h1 class="aidw-page-title">' + this._esc(conf.title) + "</h1>" +
        '<p class="aidw-page-subtitle">' + this._esc(conf.subtitle) + "</p>" +
        "</header>" +
        '<div class="aidw-scroll" data-testid="main-content"></div>';
      this._moveContent(main);

      shell.appendChild(sidebar);
      shell.appendChild(main);
      document.body.insertBefore(shell, document.body.firstChild);

      this._removeLegacyHeader();
      this._bindNav();
      this._gateNavItems(); // put the gated item back when already entitled
      this._watchAuth();
      if (this._page === "studio") {
        // One tool at a time: show the tool the URL names (fail-closed
        // to Data sources until the role is known), then keep
        // ownership of the sections' visibility.
        this._setTool(this._resolveTool(this._panelFromUrl()));
        this._watchSections();
      } else {
        this._setActive(null);
      }
    },

    /**
     * Re-apply the role gating to the sidebar's role-gated nav item and
     * re-resolve the shown tool (the role may have settled since boot).
     * Called by the page boot scripts once auth has settled (and watched
     * by _watchAuth as a backstop).
     */
    roleGate: function () {
      this._gateNavItems();
      if (this._page === "studio") {
        this._setTool(this._resolveTool(this._panelFromUrl()));
      }
    },

    /**
     * The tool a candidate panel name resolves to: the named tool when
     * it is known, the user's role may use it, and at least one of its
     * sections is still in the DOM (a restricted tool's module may
     * have removed its section); otherwise the first such usable tool
     * in sidebar order (Data sources).  While the role is still unknown
     * the restricted tools fail closed.
     */
    _resolveTool: function (candidate) {
      for (var i = 0; i < STUDIO_PANELS.length; i++) {
        var tool = STUDIO_PANELS[i];
        if (
          tool.name === candidate &&
          this._toolUsable(tool) &&
          this._sectionsFor(tool).length > 0
        ) {
          return tool;
        }
      }
      for (var j = 0; j < STUDIO_PANELS.length; j++) {
        if (
          this._toolUsable(STUDIO_PANELS[j]) &&
          this._sectionsFor(STUDIO_PANELS[j]).length > 0
        ) {
          return STUDIO_PANELS[j];
        }
      }
      return STUDIO_PANELS[0];
    },

    _toolUsable: function (tool) {
      return !tool.requiresRole || this._hasRole(tool.requiresRole);
    },

    /** The ?panel= value in the current URL (null when absent). */
    _panelFromUrl: function () {
      return new URLSearchParams(window.location.search).get("panel");
    },

    /**
     * The section.wh-panel elements a tool's panels live in.  A panel's
     * data-panel marker may sit on the section itself or on an inner
     * element; the section is the closest enclosing one.
     */
    _sectionsFor: function (tool) {
      var sections = [];
      for (var i = 0; i < tool.sections.length; i++) {
        var el = document.querySelector('main.wh-main [data-panel="' + tool.sections[i] + '"]');
        var section = el ? el.closest("section.wh-panel") : null;
        if (section && sections.indexOf(section) === -1) sections.push(section);
      }
      return sections;
    },

    /**
     * Apply the shell's intended visibility to every Studio section:
     * the shown tool's section(s) lose the `hidden` attribute and any
     * data-panel-empty-ok marker; every other USABLE tool's sections
     * carry the `hidden` attribute (and css/shell.css keeps them
     * invisible even against an explicit panel display value) and
     * declare data-panel-empty-ok while they are not the shown tool,
     * so the liveness check reads their unrendered blankness as
     * intended, not as a defect.  A tool the user's role hides is left
     * to its own fail-closed rendering — its module removes or
     * downgrades the section and the shell never touches it.
     */
    _applyIntendedVisibility: function () {
      var i, k, s;
      var active = this._activeTool;
      for (i = 0; i < STUDIO_PANELS.length; i++) {
        var candidate = STUDIO_PANELS[i];
        if (candidate.name === active || !this._toolUsable(candidate)) continue;
        var sections = this._sectionsFor(candidate);
        for (s = 0; s < sections.length; s++) {
          if (!sections[s].hasAttribute("hidden")) sections[s].setAttribute("hidden", "");
          this._markEmptyOk(sections[s]);
        }
      }
      var tool = null;
      for (k = 0; k < STUDIO_PANELS.length; k++) {
        if (STUDIO_PANELS[k].name === active) {
          tool = STUDIO_PANELS[k];
          break;
        }
      }
      if (tool) {
        var shown = this._sectionsFor(tool);
        for (s = 0; s < shown.length; s++) {
          if (shown[s].hasAttribute("hidden")) shown[s].removeAttribute("hidden");
          this._clearEmptyOk(shown[s]);
        }
      }
    },

    /** Declare data-panel-empty-ok on a hidden section and its inner [data-panel] marker(s). */
    _markEmptyOk: function (section) {
      if (!section.hasAttribute("data-panel-empty-ok")) {
        section.setAttribute("data-panel-empty-ok", "");
      }
      var markers = section.querySelectorAll("[data-panel]");
      for (var i = 0; i < markers.length; i++) {
        if (!markers[i].hasAttribute("data-panel-empty-ok")) {
          markers[i].setAttribute("data-panel-empty-ok", "");
        }
      }
    },

    /** Remove the data-panel-empty-ok markers _markEmptyOk() declared. */
    _clearEmptyOk: function (section) {
      if (section.hasAttribute("data-panel-empty-ok")) {
        section.removeAttribute("data-panel-empty-ok");
      }
      var markers = section.querySelectorAll("[data-panel]");
      for (var i = 0; i < markers.length; i++) {
        if (markers[i].hasAttribute("data-panel-empty-ok")) {
          markers[i].removeAttribute("data-panel-empty-ok");
        }
      }
    },

    /**
     * Show one tool: its section(s) become the only visible ones.  The
     * shell owns this visibility — _applyIntendedVisibility, enforced
     * by _watchSections against later mutations; a tool the user's role
     * hides is left to its own fail-closed rendering.  The title
     * becomes "Studio · <tool name>", aria-current="page" moves to the
     * tool's nav item, and the region's scroll resets to the top when
     * the shown tool changes.
     */
    _setTool: function (tool) {
      var changed = this._activeTool !== tool.name;
      this._activeTool = tool.name;
      this._applyIntendedVisibility();
      var title = document.querySelector(".aidw-page-title");
      if (title) title.textContent = "Studio · " + tool.label;
      this._setActive(tool.name);
      if (changed) {
        var region = document.querySelector(".aidw-scroll");
        if (region) region.scrollTop = 0;
      }
    },

    /**
     * Keep the shell's ownership of the sections' visibility after
     * boot.  A Studio module may remove a section from the DOM (Feed
     * keys leaves the DOM for a non-admin or a throwing Auth.isAdmin())
     * or re-assert its own visibility on an inactive section; either
     * way the shell must stay in control:
     *
     *   • when the SHOWN tool's sections leave the DOM, the shown tool
     *     falls back to the first usable tool that still has a section
     *     in the DOM (Data sources);
     *   • whenever a section's hidden attribute drifts from the
     *     intended state it is re-applied, so an inactive panel stays
     *     hidden even when a module unhides it (and css/shell.css keeps
     *     it invisible against an explicit panel display value).
     */
    _watchSections: function () {
      var main = document.querySelector("main.wh-main");
      if (!main || typeof MutationObserver === "undefined") return;
      var self = this;
      var pending = false;
      var observer = new MutationObserver(function () {
        if (pending) return;
        pending = true;
        setTimeout(function () {
          pending = false;
          self._enforceSections();
        }, 0);
      });
      observer.observe(main, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["hidden"]
      });
      this._sectionObserver = observer;
    },

    /** Re-assert the shell's intended shown tool and visibility state. */
    _enforceSections: function () {
      if (this._page !== "studio" || !this._activeTool) return;
      var active = null;
      for (var i = 0; i < STUDIO_PANELS.length; i++) {
        if (STUDIO_PANELS[i].name === this._activeTool) {
          active = STUDIO_PANELS[i];
          break;
        }
      }
      if (active && this._sectionsFor(active).length === 0) {
        // The shown tool's sections were removed from the DOM: fall
        // back to the first usable tool that still has a section.
        this._setTool(this._resolveTool(this._panelFromUrl()));
        return;
      }
      this._applyIntendedVisibility();
    },

    /**
     * The sidebar's markup, defined ONCE for both pages: the brand
     * (mark + name), the primary navigation — "Dashboards" linking to
     * index.html, then one item per Studio panel in sidebar order, the
     * Feed keys item role-gated for admins — and the footer that
     * receives the page's existing #auth-status element.
     */
    _sidebarHtml: function () {
      return (
        '<div class="aidw-brand" data-testid="sidebar-brand">' +
        '<span class="aidw-mark" aria-hidden="true"></span>' +
        '<span class="aidw-name">AIDW</span>' +
        "</div>" +
        '<nav class="aidw-nav" aria-label="Primary" data-testid="sidebar-nav">' +
        '<a class="aidw-nav-item" href="index.html" data-nav="dashboards" data-testid="nav-dashboards">Dashboards</a>' +
        '<a class="aidw-nav-item" href="studio.html?panel=sources" data-nav-panel="sources" data-testid="nav-sources">Data sources</a>' +
        '<a class="aidw-nav-item" href="studio.html?panel=suggestions" data-nav-panel="suggestions" data-testid="nav-suggestions">Suggestions</a>' +
        '<a class="aidw-nav-item" href="studio.html?panel=pii" data-nav-panel="pii" data-testid="nav-pii">PII flags</a>' +
        '<a class="aidw-nav-item" href="studio.html?panel=wizard" data-nav-panel="wizard" data-testid="nav-wizard">Process wizard</a>' +
        '<a class="aidw-nav-item" href="studio.html?panel=sequences" data-nav-panel="sequences" data-testid="nav-sequences">Load sequences</a>' +
        '<a class="aidw-nav-item" href="studio.html?panel=retention" data-nav-panel="retention" data-testid="nav-retention">Data retention</a>' +
        '<a class="aidw-nav-item" href="studio.html?panel=ingestion" data-nav-panel="ingestion" data-testid="nav-ingestion">Ingestion</a>' +
        '<a class="aidw-nav-item" href="studio.html?panel=feedkeys" data-nav-panel="feedkeys" data-testid="nav-feedkeys" data-requires-role="admin">Feed keys</a>' +
        '<a class="aidw-nav-item" href="studio.html?panel=audit" data-nav-panel="audit" data-testid="nav-audit">Audit history</a>' +
        "</nav>" +
        '<div class="aidw-sidebar-foot" data-testid="sidebar-foot"></div>'
      );
    },

    /** Move the page's existing #auth-status element to the sidebar bottom. */
    _moveAuthStatus: function (sidebar) {
      var el = document.getElementById("auth-status");
      var foot = sidebar.querySelector(".aidw-sidebar-foot");
      if (el && foot) foot.appendChild(el);
    },

    /** Move the page's existing main content into the scrollable region. */
    _moveContent: function (main) {
      var content = document.querySelector("main.wh-main");
      var region = main.querySelector(".aidw-scroll");
      if (content && region) region.appendChild(content);
    },

    _removeLegacyHeader: function () {
      var header = document.querySelector("header.wh-header");
      if (header) header.remove();
    },

    _bindNav: function () {
      var nav = document.querySelector(".aidw-nav");
      if (!nav) return;
      var self = this;
      nav.addEventListener("click", function (e) {
        var link = e.target && e.target.closest ? e.target.closest("a.aidw-nav-item") : null;
        var panel = link ? link.getAttribute("data-nav-panel") : null;
        if (!panel) return; // "Dashboards": a genuine page load
        if (self._page === "dashboards") {
          // Not on Studio: the item's own href
          // (studio.html?panel=<name>) does a genuine page load; the
          // deep link shows that tool once Studio boots.
          return;
        }
        e.preventDefault();
        self._setPanelInUrl(panel);
        self._setTool(self._resolveTool(panel));
      });
      // Back/forward restore the tool the URL names, without a reload.
      window.addEventListener("popstate", function () {
        if (self._page === "studio") {
          self._setTool(self._resolveTool(self._panelFromUrl()));
        }
      });
    },

    _knownPanel: function (panel) {
      for (var i = 0; i < STUDIO_PANELS.length; i++) {
        if (STUDIO_PANELS[i].name === panel) return true;
      }
      return false;
    },

    /** Keep ?panel=<name> in the URL (reload honours it via deeplink.js) without a page load. */
    _setPanelInUrl: function (panel) {
      var url = new URL(window.location.href);
      url.searchParams.set("panel", panel);
      history.pushState(null, "", url.pathname + url.search + url.hash);
    },

    /**
     * aria-current="page": on Dashboards the Dashboards item; on Studio
     * the shown tool's item (or the first tool's when the item is not in
     * the DOM, as for a role-gated item).
     */
    _setActive: function (panel) {
      var items = document.querySelectorAll(".aidw-nav-item");
      for (var i = 0; i < items.length; i++) items[i].removeAttribute("aria-current");
      var name = null;
      var key = null;
      if (this._page === "dashboards") {
        name = "dashboards";
        key = "data-nav";
      } else if (panel && this._knownPanel(panel)) {
        name = panel;
        key = "data-nav-panel";
      }
      var target = null;
      if (name) {
        target = document.querySelector(".aidw-nav-item[" + key + '="' + name + '"]');
      }
      if (!target) {
        // First tool (or a gated item that is out of the DOM).
        target = document.querySelector(".aidw-nav-item[data-nav-panel='" + STUDIO_PANELS[0].name + "']");
      }
      if (target) target.setAttribute("aria-current", "page");
    },

    /**
     * Fail-closed role gate for the sidebar's role-gated item (the
     * "Feed keys" nav item, data-requires-role="admin"): the item leaves
     * the DOM until the signed-in user holds the required role — the
     * same convention as the app's other admin-only controls, so no
     * element carrying data-requires-role="admin" survives for a
     * non-admin.
     */
    _detachGatedItem: function (sidebar) {
      var item = sidebar.querySelector(".aidw-nav-item[data-requires-role]");
      if (!item) return;
      this._gatedItem = item;
      this._gatedRole = item.getAttribute("data-requires-role");
      this._gatedNext = item.nextElementSibling; // remember the sidebar order
      item.remove();
    },

    /**
     * Re-apply the role gate: once the signed-in user holds the required
     * role the gated item is put back in its sidebar position (aria-
     * current follows from the shown tool); a missing/throwing Auth
     * degrades to the item staying out of the DOM.
     */
    _gateNavItems: function () {
      if (
        this._gatedItem &&
        !this._gatedItem.parentNode &&
        this._hasRole(this._gatedRole)
      ) {
        var nav = document.querySelector(".aidw-nav");
        if (!nav) return;
        if (this._gatedNext && this._gatedNext.parentNode === nav) {
          nav.insertBefore(this._gatedItem, this._gatedNext);
        } else {
          nav.appendChild(this._gatedItem);
        }
      }
    },

    _hasRole: function (role) {
      try {
        // Auth is a top-level const, not a window property - test the
        // global lexical binding, never window.Auth.
        if (typeof Auth === "undefined" || typeof Auth.hasRole !== "function") return false;
        return Auth.hasRole(role) === true;
      } catch (e) {
        return false;
      }
    },

    /** Auth settles asynchronously; re-apply the gate until it does. */
    _watchAuth: function () {
      var self = this;
      var ticks = 0;
      var timer = setInterval(function () {
        ticks += 1;
        self._gateNavItems();
        if (self._page === "studio") {
          // The role may have settled since boot: re-resolve the shown
          // tool (idempotent while it stays the same).
          self._setTool(self._resolveTool(self._panelFromUrl()));
        }
        var user = null;
        try {
          user =
            typeof Auth !== "undefined" && Auth.getCurrentUser
              ? Auth.getCurrentUser()
              : null;
        } catch (e) {
          user = null;
        }
        if (user || ticks >= 200) clearInterval(timer);
      }, 100);
      this._authTimer = timer;
    },

    _esc(s) {
      return String(s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }
  };

  window.Shell = Shell;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { Shell.init(); });
  } else {
    Shell.init();
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { Shell };
  }
})();

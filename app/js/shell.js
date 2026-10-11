/**
 * AIDW application shell — the fixed-height two-column layout from
 * docs/design/design-system.md ("The application shell").
 *
 *   • a 100vh shell of two columns: the dark sidebar (--sidebar-width,
 *     232 px) and the main area
 *   • the sidebar, top to bottom: the AIDW mark and name, the primary
 *     navigation (Dashboards, then one item per Studio tool), and at
 *     the bottom the page's existing #auth-status element
 *   • the main area: the page title ("Dashboards" or "Studio · <tool>")
 *     with a one-line subtitle, then the scrollable content (the
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
 * Studio tools: the main area shows exactly ONE tool at a time — the
 * panel named by the ?panel= query (the same deep link js/deeplink.js
 * honours on load), or Data sources when ?panel= is absent, unknown, or
 * names a tool the user's role hides.  A tool is one or more
 * section.wh-panel containers (Load sequences is one tool with two
 * sections: its list and its run history); every other tool's sections
 * carry the `hidden` attribute while the tool is out.  The shell owns
 * that visibility (css/shell.css + the inline display pin in
 * _showSection): an inactive tool's header, layout and inner
 * [data-panel] content are not visible no matter what display value the
 * panel's own CSS sets.  A panel controller may still touch its own
 * section's hidden attribute (Feed keys does section.hidden = false for
 * an admin); a mutation observer on the tool containers re-asserts the
 * shell's decision for any such change, so the shell's visibility call
 * always wins.  Hiding never touches a section's children — ids,
 * data-testid/data-panel/data-requires-role/data-action hooks, loaded
 * data and form input all stay, so switching back shows the tool as it
 * was.
 *
 * Switching tools from the sidebar rewrites ?panel= WITHOUT a page
 * load (history.pushState), moves aria-current="page" to the item and
 * puts the main region's scroll back to the top; Back and forward
 * restore the previous tool from the URL (popstate, no reload).
 * On the Dashboards page the Studio items keep their hrefs and do a
 * genuine page load to studio.html?panel=<name>; Studio then arrives
 * on that tool via the deep link.  On index.html the Dashboards item
 * carries aria-current="page".
 *
 * Role-gated items (data-requires-role) follow the app's existing
 * fail-closed convention for admin-only controls: the element leaves the
 * DOM until the signed-in user holds the required role, so no element
 * carrying data-requires-role="admin" survives for a non-admin.  A
 * ?panel= deep link to a role-hidden tool resolves to Data sources.
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
  // handler know, and for which section.wh-panel containers belong to
  // which tool.
  //
  // `panels` lists the data-panel values of the tool's content; each
  // value's enclosing section.wh-panel is the full panel container the
  // visibility controller shows or hides (the section itself when the
  // value sits on it).  "Load sequences" is ONE tool with two sections
  // — the sequence list and its run history.  `requiresRole` marks the
  // role-gated tool: a user without the role never sees it (its deep
  // link falls back to Data sources, its nav item leaves the DOM).
  var STUDIO_PANELS = [
    { name: "sources", label: "Data sources", panels: ["sources"] },
    { name: "suggestions", label: "Suggestions", panels: ["suggestions"] },
    { name: "pii", label: "PII flags", panels: ["pii"] },
    { name: "wizard", label: "Process wizard", panels: ["wizard"] },
    { name: "sequences", label: "Load sequences", panels: ["sequences", "sequence-runs"] },
    { name: "retention", label: "Data retention", panels: ["retention"] },
    { name: "ingestion", label: "Ingestion", panels: ["ingestion"] },
    { name: "feedkeys", label: "Feed keys", panels: ["feedkeys"], requiresRole: "admin" },
    { name: "audit", label: "Audit history", panels: ["audit"] }
  ];

  var Shell = {
    _built: false,
    _page: "dashboards",
    _tool: null,
    _sectionObserver: null,
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
      this._initialFocus();
      this._watchSectionVisibility();
    },

    /**
     * Re-apply the role gating to the sidebar's role-gated nav item and
     * re-resolve the shown tool now that the user may be known.  Called
     * by the page boot scripts once auth has settled (and watched by
     * _watchAuth as a backstop).
     */
    roleGate: function () {
      this._gateNavItems();
      this._syncTool();
    },

    /**
     * Show the tool `panel` names (or Data sources when the name is
     * unknown or the user's role hides it).  Used by the sidebar, the
     * popstate handler and the initial deep link.
     */
    focusPanel: function (panel) {
      var tool = this._panelTool(panel);
      if (!tool || !this._toolAllowed(tool)) tool = this._panelTool("sources");
      this._setTool(tool);
    },

    _panelTool: function (panel) {
      for (var i = 0; i < STUDIO_PANELS.length; i++) {
        if (STUDIO_PANELS[i].name === panel) return STUDIO_PANELS[i];
      }
      return null;
    },

    /** True when the signed-in user holds the tool's required role. */
    _toolAllowed: function (tool) {
      if (!tool || !tool.requiresRole) return true;
      return this._hasRole(tool.requiresRole);
    },

    /**
     * The tool the URL names: ?panel= when it is a known tool the
     * user's role may see, Data sources otherwise (absent, unknown or
     * role-hidden all fall back).
     */
    _toolForUrl: function () {
      var params = new URLSearchParams(window.location.search);
      var tool = this._panelTool(params.get("panel"));
      if (tool && this._toolAllowed(tool)) return tool;
      return this._panelTool("sources");
    },

    /**
     * The tool's full panel containers: each of its data-panel values
     * maps to the enclosing section.wh-panel (the section itself when
     * the value sits on it).  Containers that left the DOM (the
     * fail-closed role removal) are skipped.
     */
    _toolSections: function (tool) {
      var sections = [];
      for (var i = 0; i < tool.panels.length; i++) {
        var el = document.querySelector('[data-panel="' + tool.panels[i] + '"]');
        if (!el) continue;
        var section = el.closest ? el.closest("section.wh-panel") : el;
        if (!section) section = el;
        if (sections.indexOf(section) === -1) sections.push(section);
      }
      return sections;
    },

    /**
     * The shell owns .wh-panel visibility: hiding a container sets its
     * `hidden` attribute plus an inline display pin that beats any
     * display value the panel's own CSS sets (css/shell.css carries the
     * declarative half, .wh-panel[hidden]); showing it again clears
     * both.  Children are never touched — ids, data-* hooks, loaded
     * data and form input survive the switch.
     */
    _showSection: function (section, show) {
      section.hidden = !show;
      if (show) {
        section.style.removeProperty("display");
      } else {
        section.style.setProperty("display", "none", "important");
      }
    },

    /**
     * The shell owns .wh-panel visibility: a panel controller may still
     * try to un-hide its own section (Feed keys does section.hidden =
     * false for an admin).  A mutation observer on the tool containers
     * re-asserts the shell's decision for any such change: an inactive
     * tool's container goes back to hidden + display pin, an active one
     * stays shown.  Containers the shell does not own (the Dashboards
     * page's drilldown panels) are left alone.
     */
    _watchSectionVisibility: function () {
      if (typeof MutationObserver === "undefined") return;
      var sections = document.querySelectorAll("section.wh-panel");
      if (!sections.length) return;
      var self = this;
      this._sectionObserver = new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i++) {
          self._assertSectionPinned(mutations[i].target);
        }
      });
      for (var i = 0; i < sections.length; i++) {
        this._sectionObserver.observe(sections[i], {
          attributes: true,
          attributeFilter: ["hidden"]
        });
      }
    },

    /** Re-assert the shell's visibility decision for one changed container. */
    _assertSectionPinned: function (section) {
      if (this._page !== "studio" || !this._tool) return;
      var owner = null;
      for (var i = 0; i < STUDIO_PANELS.length; i++) {
        if (this._toolSections(STUDIO_PANELS[i]).indexOf(section) !== -1) {
          owner = STUDIO_PANELS[i];
          break;
        }
      }
      if (!owner) return; // not a Studio tool container (or gone from the DOM)
      var shouldShow = owner === this._tool;
      if (section.hasAttribute("hidden") === !shouldShow) return; // consistent
      this._showSection(section, shouldShow);
    },

    /**
     * Show exactly one tool: every other tool's containers hide, the
     * main header reads "Studio · <tool name>", aria-current="page"
     * moves to the tool's nav item and the main region goes back to
     * the top (it scrolls only when the shown tool is taller than it).
     */
    _setTool: function (tool) {
      tool = tool || this._panelTool("sources");
      this._tool = tool;
      var i, j, sections, on;
      for (i = 0; i < STUDIO_PANELS.length; i++) {
        on = STUDIO_PANELS[i] === tool;
        sections = this._toolSections(STUDIO_PANELS[i]);
        for (j = 0; j < sections.length; j++) this._showSection(sections[j], on);
      }
      var title = document.querySelector(".aidw-page-title");
      if (title) title.textContent = PAGES.studio.title + " \u00b7 " + tool.label;
      this._setActive(tool.name);
      var region = document.querySelector(".aidw-scroll");
      if (region) region.scrollTop = 0;
    },

    /**
     * Re-resolve the tool once the user is known: a deep link to a
     * tool the user's role hides (or that resolved before auth
     * settled) now lands on the tool — and a role-hidden one has
     * already fallen back to Data sources.
     */
    _syncTool: function () {
      if (this._page !== "studio" || !this._tool) return;
      var tool = this._toolForUrl();
      if (tool && tool !== this._tool) this._setTool(tool);
    },

    /**
     * On Studio, show the tool the URL names (deep link honoured on
     * load); on Dashboards, mark the Dashboards item current.
     */
    _initialFocus: function () {
      if (this._page !== "studio") {
        this._setActive(null);
        return;
      }
      this._setTool(this._toolForUrl());
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
     * role the gated item is put back in its sidebar position; a
     * missing/throwing Auth degrades to the item staying out of the DOM.
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
        // A deep link to the gated panel ran while the item was still
        // out of the DOM: move aria-current to it now.
        if (this._page === "studio") {
          var panelName = this._gatedItem.getAttribute("data-nav-panel");
          var params = new URLSearchParams(window.location.search);
          if (params.get("panel") === panelName) {
            this._setActive(panelName);
          }
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
        self._syncTool();
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

    /**
     * The sidebar's markup, defined ONCE for both pages: the brand
     * (mark + name), the primary navigation — "Dashboards" linking to
     * index.html, then one item per Studio tool in sidebar order, the
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
          // deep link shows the tool once Studio boots.
          return;
        }
        e.preventDefault();
        self._setPanelInUrl(panel);
        self.focusPanel(panel);
      });
      // Back/forward restore the previous tool from ?panel= without a
      // reload.
      window.addEventListener("popstate", function () {
        var params = new URLSearchParams(window.location.search);
        self.focusPanel(params.get("panel"));
      });
    },

    /** Keep ?panel=<name> in the URL (reload honours it via deeplink.js) without a page load. */
    _setPanelInUrl: function (panel) {
      var url = new URL(window.location.href);
      url.searchParams.set("panel", panel);
      history.pushState(null, "", url.pathname + url.search + url.hash);
    },

    /**
     * aria-current="page": on Dashboards the Dashboards item; on Studio
     * the tool last shown (or deep-linked), or the first tool when
     * there is none.
     */
    _setActive: function (panel) {
      var items = document.querySelectorAll(".aidw-nav-item");
      for (var i = 0; i < items.length; i++) items[i].removeAttribute("aria-current");
      var name = null;
      var key = null;
      if (this._page === "dashboards") {
        name = "dashboards";
        key = "data-nav";
      } else if (panel && this._panelTool(panel)) {
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

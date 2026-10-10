/**
 * AIDW application shell — the fixed-height two-column layout from
 * docs/design/design-system.md ("The application shell").
 *
 *   • a 100vh shell of two columns: the dark sidebar (--sidebar-width,
 *     232 px) and the main area
 *   • the sidebar, top to bottom: the AIDW mark and name, the primary
 *     navigation (Dashboards, then one item per Studio panel), and at
 *     the bottom the page's existing #auth-status element
 *   • the main area: the page title ("Dashboards" or "Studio") with a
 *     one-line subtitle, then the scrollable content (the existing
 *     main.wh-main) — at desktop width the document never scrolls, only
 *     this content region does
 *   • at 900 px and below the sidebar becomes a top bar (css/shell.css)
 *
 * The sidebar markup is defined ONCE in _sidebarHtml() and rendered into
 * both Dashboards (index.html) and Studio (studio.html) — the pages carry
 * no duplicated navigation HTML.  The legacy top header (the old
 * "Configure" / "← Dashboard" links) is replaced by this sidebar and
 * removed from the live DOM on boot; #auth-status is kept and moved to
 * the bottom of the sidebar.
 *
 * Studio navigation: on Studio a nav item rewrites the URL's ?panel=
 * query (the same deep link js/deeplink.js honours on load) WITHOUT a
 * page load, scrolls the main content region to the panel and moves
 * aria-current="page" to the item (the panel last navigated to; the
 * first panel when none).  On the Dashboards page the Studio items
 * keep their hrefs and do a genuine page load to
 * studio.html?panel=<name>; Studio then arrives focused on that panel
 * via the deep link.  On index.html the Dashboards item carries
 * aria-current="page".
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

  // One Studio panel per nav item, in sidebar order — the single source
  // of truth for which panel names the deep link and the popstate
  // handler know.
  var STUDIO_PANELS = [
    { name: "sources", label: "Data sources" },
    { name: "suggestions", label: "Suggestions" },
    { name: "pii", label: "PII flags" },
    { name: "wizard", label: "Process wizard" },
    { name: "sequences", label: "Load sequences" },
    { name: "retention", label: "Data retention" },
    { name: "ingestion", label: "Ingestion" },
    { name: "feedkeys", label: "Feed keys" },
    { name: "audit", label: "Audit history" }
  ];

  var Shell = {
    _built: false,
    _page: "dashboards",
    _guardTimer: null,
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
    },

    /**
     * Re-apply the role gating to the sidebar's role-gated nav item.
     * Called by the page boot scripts once auth has settled (and
     * watched by _watchAuth as a backstop).
     */
    roleGate: function () {
      this._gateNavItems();
    },

    /**
     * Focus a Studio panel: scroll the main content region to it (the
     * same behaviour as the ?panel= deep link on load) and mark the
     * matching nav item as current.
     *
     * The panel's neighbours keep rendering (tables, run lists) after
     * the first scroll; while they settle, a short-lived guard keeps
     * the target inside the region's view.  The guard only ever
     * compensates for layout drift — the content moving while the
     * region's scroll position holds.  A scroll position it did not
     * set itself is the user taking over, and it steps aside without
     * re-scrolling.
     */
    focusPanel: function (panel) {
      this._setActive(panel);
      var el = document.querySelector('[data-panel="' + panel + '"]');
      if (!el) return;
      this._scrollRegionTo(el);
      var prevOutline = el.style.outline;
      el.style.outline = "2px solid #1f6feb";
      el.style.outlineOffset = "2px";
      var self = this;
      setTimeout(function () {
        el.style.outline = prevOutline;
        el.style.outlineOffset = "";
      }, 1600);

      if (this._guardTimer) clearTimeout(this._guardTimer);
      var deadline = Date.now() + 2500;
      (function guard() {
        if (Date.now() > deadline) {
          self._guardTimer = null;
          return;
        }
        if (self._panelOutOfView(el)) {
          if (self._regionScrolledByUser()) {
            // The user scrolled the region away: they own the view now.
            self._guardTimer = null;
            return;
          }
          // Neighbours shifted the layout under a held scroll position:
          // put the target back in view.
          self._scrollRegionTo(el);
        }
        self._guardTimer = setTimeout(guard, 100);
      })();
    },

    /**
     * Scroll the main content region to the panel.  Instant, so the new
     * position is in place before the next task runs — and remembered:
     * it is the position "we" set, the reference the guard compares
     * against to tell layout drift from a user scroll.
     */
    _scrollRegionTo: function (el) {
      el.scrollIntoView({ behavior: "auto", block: "start" });
      var region = document.querySelector(".aidw-scroll");
      this._regionScroll = region ? region.scrollTop : 0;
    },

    /** True when the region's scroll position is no longer one we set. */
    _regionScrolledByUser: function () {
      var region = document.querySelector(".aidw-scroll");
      if (!region) return true;
      return Math.abs(region.scrollTop - (this._regionScroll || 0)) > 1;
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
          // deep link focuses the panel once Studio boots.
          return;
        }
        e.preventDefault();
        self._setPanelInUrl(panel);
        self.focusPanel(panel);
      });
      // Back/forward restore the ?panel= deep link without a reload.
      window.addEventListener("popstate", function () {
        var params = new URLSearchParams(window.location.search);
        var panel = params.get("panel");
        if (panel && Shell._knownPanel(panel)) {
          self.focusPanel(panel);
        } else {
          self._setActive(null);
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
     * the panel last navigated to (or deep-linked), or the first panel
     * when there is none.
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
        // First panel (or a gated item that is out of the DOM).
        target = document.querySelector(".aidw-nav-item[data-nav-panel='" + STUDIO_PANELS[0].name + "']");
      }
      if (target) target.setAttribute("aria-current", "page");
    },

    /** On a ?panel= deep link, focus that panel; otherwise no scroll. */
    _initialFocus: function () {
      if (this._page !== "studio") {
        this._setActive(null);
        return;
      }
      var params = new URLSearchParams(window.location.search);
      var panel = params.get("panel");
      if (panel && this._knownPanel(panel)) {
        this.focusPanel(panel);
      } else {
        this._setActive(null); // first panel, no scroll
      }
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

    _panelOutOfView: function (el) {
      var region = document.querySelector(".aidw-scroll");
      if (!region) return false;
      var r = el.getBoundingClientRect();
      var rr = region.getBoundingClientRect();
      return r.bottom <= rr.top || r.top >= rr.bottom;
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

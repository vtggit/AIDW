/**
 * Deep-link handler — focus a screen from the URL on load.
 *
 *   index.html?item=<id>       -> open that dashboard item's drilldown
 *   studio.html?panel=<name>   -> scroll to that Studio section (sources|suggestions|pii|wizard)
 *
 * Powers the assistant's "open X" links and makes those views shareable by URL.
 * Purely additive and read-only; no effect when the params are absent.
 */
(function () {
  "use strict";

  function openItem(item) {
    if (typeof Drilldown === "undefined" || !Drilldown.open) return;
    Drilldown.open(item);
    var dd = document.getElementById("drilldown");
    if (dd) dd.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function focusFromUrl() {
    var params = new URLSearchParams(window.location.search);

    var item = params.get("item");
    if (item) {
      // The app stores its auth token asynchronously on load; opening the drilldown
      // immediately would fire its fetch before the token exists and 401 on a cold
      // (shared/bookmarked) link. Poll briefly for auth, then open regardless so
      // auth-disabled deployments still work.
      var tries = 0;
      (function waitForAuth() {
        var authed = window.Auth && Auth.getAuthorizationHeader && Auth.getAuthorizationHeader();
        if (authed || tries >= 20) { openItem(item); return; }
        tries++;
        setTimeout(waitForAuth, 100);
      })();
      return;
    }

    var panel = params.get("panel");
    if (panel) {
      var safe = panel.replace(/[^a-z]/gi, ""); // sanitize before use in a selector
      var el = document.querySelector('[data-panel="' + safe + '"]');
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        var prev = el.style.outline;
        el.style.outline = "2px solid #1f6feb";
        el.style.outlineOffset = "2px";
        setTimeout(function () {
          el.style.outline = prev;
          el.style.outlineOffset = "";
        }, 1600);
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", focusFromUrl);
  } else {
    focusFromUrl();
  }
})();

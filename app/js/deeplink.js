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

  function focusFromUrl() {
    var params = new URLSearchParams(window.location.search);

    var item = params.get("item");
    if (item && typeof Drilldown !== "undefined" && Drilldown.open) {
      Drilldown.open(item);
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

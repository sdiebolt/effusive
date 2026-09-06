// Lightbox-style zoom for rendered Mermaid SVGs.
//
// Zensical renders Mermaid diagrams inside closed Shadow DOM, so regular
// querySelector(".mermaid svg") returns nothing. We patch attachShadow once
// to capture every shadow root as it is created, then look up the root on
// click. The patch and the global map survive instant-navigation page swaps.

(function () {
  // One global WeakMap so re-executions on instant-nav don't create orphaned
  // closures. The attachShadow patch is also set up only once.
  if (!window._mermaidShadowRoots) {
    window._mermaidShadowRoots = new WeakMap();
    const _attachShadow = Element.prototype.attachShadow;
    Element.prototype.attachShadow = function (init) {
      const shadow = _attachShadow.call(this, init);
      window._mermaidShadowRoots.set(this, shadow);
      return shadow;
    };
  }

  function openModal(svg) {
    const clone = svg.cloneNode(true);
    clone.removeAttribute("width");
    clone.removeAttribute("height");
    clone.style.cssText =
      "display:block;max-width:90vw;max-height:90vh;width:auto;height:auto;" +
      "background:var(--md-default-bg-color,#fff);border-radius:4px;padding:1.5rem;";

    const overlay = document.createElement("div");
    overlay.style.cssText =
      "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;" +
      "justify-content:center;background:rgba(0,0,0,0.82);cursor:zoom-out;padding:2rem;";
    overlay.appendChild(clone);

    function close() {
      overlay.remove();
      document.removeEventListener("keydown", onKey);
    }
    function onKey(e) {
      if (e.key === "Escape") close();
    }
    overlay.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    document.body.appendChild(overlay);
  }

  // Install the click handler only once — it references the global map, so
  // it keeps working after instant-navigation replaces the page DOM.
  if (!window._mermaidZoomInstalled) {
    window._mermaidZoomInstalled = true;
    document.addEventListener("click", function (e) {
      const container = e.target.closest(".mermaid");
      if (!container) return;
      const shadow = window._mermaidShadowRoots.get(container);
      if (!shadow) return;
      const svg = shadow.querySelector("svg");
      if (svg) {
        e.preventDefault();
        openModal(svg);
      }
    });
  }
})();

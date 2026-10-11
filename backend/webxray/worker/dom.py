"""JavaScript probes evaluated inside the page.

Probes only *read* the DOM. They never change application state, and their
output is treated as untrusted data (it is redacted and size-limited before
storage, and it never alters policy).
"""

from __future__ import annotations

# Shared helpers injected into each probe.
_HELPERS = r"""
const __wx = (() => {
  const clip = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const accName = (el) => {
    if (!el) return '';
    const aria = el.getAttribute && el.getAttribute('aria-label');
    if (aria) return clip(aria, 120);
    const lb = el.getAttribute && el.getAttribute('aria-labelledby');
    if (lb) return clip(lb.split(/\s+/).map(id => (document.getElementById(id) || {}).textContent || '').join(' '), 120);
    if (el.tagName === 'INPUT' && ['submit', 'button'].includes(el.type)) return clip(el.value, 120);
    return clip(el.innerText || el.textContent || el.title || '', 120);
  };
  const labelFor = (el) => {
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) return clip(l.innerText || l.textContent, 120);
    }
    const wrap = el.closest('label');
    if (wrap) return clip(wrap.innerText || wrap.textContent, 120);
    return clip(el.getAttribute('aria-label') || el.getAttribute('placeholder') || '', 120);
  };
  const cssPath = (el) => {
    if (!el || el.nodeType !== 1) return '';
    if (el.id) return `#${CSS.escape(el.id)}`;
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 5) {
      let part = cur.tagName.toLowerCase();
      if (cur.id) { parts.unshift(`#${CSS.escape(cur.id)}`); break; }
      const cls = [...cur.classList].slice(0, 2).map(c => '.' + CSS.escape(c)).join('');
      part += cls;
      const parent = cur.parentElement;
      if (parent) {
        const same = [...parent.children].filter(c => c.tagName === cur.tagName);
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(cur) + 1})`;
      }
      parts.unshift(part);
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  };
  const rect = (el) => {
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.left), y: Math.round(r.top), width: Math.round(r.width), height: Math.round(r.height) };
  };
  const STYLE_PROPS = ['display', 'visibility', 'opacity', 'position', 'z-index', 'top', 'right', 'bottom', 'left',
    'width', 'height', 'pointer-events', 'overflow', 'transform', 'margin-bottom', 'padding-bottom'];
  const styles = (el) => {
    const cs = getComputedStyle(el);
    const out = {};
    for (const p of STYLE_PROPS) out[p] = cs.getPropertyValue(p);
    return out;
  };
  const describe = (el) => {
    if (!el || el.nodeType !== 1) return null;
    return {
      tag: el.tagName.toLowerCase(),
      id: el.id || null,
      classes: [...el.classList].slice(0, 6),
      role: el.getAttribute('role'),
      ariaLabel: el.getAttribute('aria-label'),
      name: accName(el),
      selector: cssPath(el),
      rect: rect(el),
    };
  };
  // Nearest ancestor (or self) that establishes an overlay: fixed/sticky/absolute positioning.
  const overlayRoot = (el) => {
    let cur = el;
    while (cur && cur.nodeType === 1 && cur !== document.body) {
      const pos = getComputedStyle(cur).position;
      if (pos === 'fixed' || pos === 'sticky' || pos === 'absolute') return cur;
      cur = cur.parentElement;
    }
    return el;
  };
  const sanitizedHTML = (el, limit) => {
    const clone = el.cloneNode(true);
    const all = [clone, ...clone.querySelectorAll('*')];
    for (const n of all) {
      if (n.tagName === 'SCRIPT' || n.tagName === 'STYLE') { n.remove(); continue; }
      for (const a of [...n.attributes]) {
        if (a.name === 'value' || a.name.startsWith('on') || a.name === 'srcdoc') n.removeAttribute(a.name);
      }
    }
    return clone.outerHTML.slice(0, limit);
  };
  return { clip, accName, labelFor, cssPath, rect, styles, describe, overlayRoot, sanitizedHTML };
})();
"""

INVENTORY_JS = (
    "() => {"
    + _HELPERS
    + r"""
  const { clip, accName, labelFor, cssPath } = __wx;
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const links = [...document.querySelectorAll('a[href]')].slice(0, 400).map(a => ({
    href: a.href, text: accName(a), rel: a.getAttribute('rel') || '', visible: visible(a),
    inNav: !!a.closest('nav, header, [role=navigation]'),
  }));
  const fieldInfo = (f) => ({
    // The .type property normalizes a missing/unknown type attribute to "text" (like the browser does).
    tag: f.tagName.toLowerCase(), type: (f.tagName === 'INPUT' ? f.type : f.tagName).toLowerCase(),
    name: f.getAttribute('name') || '', id: f.id || '', label: labelFor(f),
    required: f.required || f.getAttribute('aria-required') === 'true',
    autocomplete: f.getAttribute('autocomplete') || '', placeholder: clip(f.getAttribute('placeholder'), 80),
    inputmode: f.getAttribute('inputmode') || '',
    hasValue: f.type === 'checkbox' || f.type === 'radio' ? f.checked : !!f.value,
    options: f.tagName === 'SELECT' ? [...f.options].slice(0, 30).map(o => ({ value: o.value, text: clip(o.text, 60) })) : undefined,
    visible: visible(f), selector: cssPath(f),
  });
  const forms = [...document.querySelectorAll('form')].slice(0, 20).map((form, i) => ({
    index: i, id: form.id || '', action: form.action || '', method: (form.method || 'get').toLowerCase(),
    selector: cssPath(form),
    fields: [...form.querySelectorAll('input, select, textarea')]
      .filter(f => !['hidden', 'submit', 'button', 'image', 'reset'].includes((f.type || '').toLowerCase()))
      .slice(0, 60).map(fieldInfo),
    submits: [...form.querySelectorAll('button:not([type]), button[type=submit], input[type=submit]')]
      .slice(0, 5).map(b => ({ text: accName(b), selector: cssPath(b) })),
  }));
  const buttons = [...document.querySelectorAll('button, [role=button], input[type=submit], input[type=button]')]
    .slice(0, 200).map(b => ({ text: accName(b), type: b.getAttribute('type') || '', disabled: !!b.disabled,
      visible: visible(b), selector: cssPath(b), inForm: !!b.closest('form') }));
  const captcha = !!document.querySelector(
    'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="turnstile"], iframe[src*="challenges.cloudflare"], ' +
    '.g-recaptcha, .h-captcha, .cf-turnstile, [data-sitekey]');
  const text = clip(document.body ? document.body.innerText : '', 4000);
  const doc = document.documentElement;
  return {
    title: document.title || '',
    h1: [...document.querySelectorAll('h1')].slice(0, 3).map(h => clip(h.innerText, 160)),
    headings: [...document.querySelectorAll('h2, h3')].slice(0, 20).map(h => clip(h.innerText, 120)),
    links, forms, buttons, captcha,
    passwordFields: document.querySelectorAll('input[type=password]').length,
    oneTimeCode: !!document.querySelector('input[autocomplete="one-time-code"]'),
    alerts: [...document.querySelectorAll('[role=alert], .error, .errors, [aria-invalid=true]')]
      .slice(0, 10).map(a => clip(a.innerText || a.getAttribute('aria-label') || '', 300)).filter(Boolean),
    landmarks: {
      nav: document.querySelectorAll('nav, [role=navigation]').length,
      main: document.querySelectorAll('main, [role=main]').length,
      dialog: document.querySelectorAll('dialog[open], [role=dialog]').length,
    },
    overflowX: Math.max(doc.scrollWidth, document.body ? document.body.scrollWidth : 0) - window.innerWidth,
    viewport: { width: window.innerWidth, height: window.innerHeight },
    text,
  };
}"""
)

# Geometry of an element as rendered, in both layout and visual-viewport coordinates.
#
# getBoundingClientRect/elementFromPoint use *layout* viewport coordinates, but
# real input (and Playwright's mouse/touchscreen) uses *visual* viewport
# coordinates. They differ whenever the layout viewport is larger than the
# screen (e.g. horizontal overflow on mobile) or the page is zoomed, so every
# point is reported in both systems. elementFromPoint is supporting evidence
# only; reachability is decided by a real probe tap (PROBE_* below).
HIT_TEST_JS = (
    "(el) => {"
    + _HELPERS
    + r"""
  const { describe, styles, overlayRoot, sanitizedHTML, rect } = __wx;
  const r = el.getBoundingClientRect();
  const lw = window.innerWidth, lh = window.innerHeight;
  const vv = window.visualViewport || { offsetLeft: 0, offsetTop: 0, width: lw, height: lh, scale: 1 };
  const toVisual = (x, y) => ({ vx: Math.round((x - vv.offsetLeft) * vv.scale), vy: Math.round((y - vv.offsetTop) * vv.scale) });
  const vW = vv.width * vv.scale, vH = vv.height * vv.scale;
  const pts = [[0.5, 0.5], [0.2, 0.5], [0.8, 0.5], [0.5, 0.25], [0.5, 0.75]];
  const points = pts.map(([fx, fy]) => {
    const x = r.left + r.width * fx, y = r.top + r.height * fy;
    const { vx, vy } = toVisual(x, y);
    const onScreen = vx >= 0 && vy >= 0 && vx < vW && vy < vH;
    const inLayout = x >= 0 && y >= 0 && x < lw && y < lh;
    const top = inLayout ? document.elementFromPoint(x, y) : null;
    const hit = !!top && (top === el || el.contains(top));
    return { fx, fy, x: Math.round(x), y: Math.round(y), vx, vy, onScreen, inViewport: onScreen, hit, top: hit ? null : describe(top) };
  });
  const center = points[0];
  let interceptor = null;
  const firstMiss = points.find(p => p.top && !p.hit);
  if (firstMiss) {
    const topEl = document.elementFromPoint(firstMiss.x, firstMiss.y);
    if (topEl) {
      const root = overlayRoot(topEl);
      const rr = root.getBoundingClientRect();
      const overlap = {
        width: Math.max(0, Math.min(r.right, rr.right) - Math.max(r.left, rr.left)),
        height: Math.max(0, Math.min(r.bottom, rr.bottom) - Math.max(r.top, rr.top)),
      };
      interceptor = {
        element: describe(topEl), overlayRoot: describe(root), overlayStyles: styles(root),
        overlap: { ...overlap, areaRatio: r.width * r.height ? +(overlap.width * overlap.height / (r.width * r.height)).toFixed(3) : 0 },
        html: sanitizedHTML(root, 2000),
      };
    }
  }
  const cs = getComputedStyle(el);
  const doc = document.documentElement;
  return {
    target: describe(el), targetStyles: styles(el), targetHtml: sanitizedHTML(el, 1000),
    disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
    visible: r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && +cs.opacity > 0,
    rect: rect(el),
    viewport: { width: lw, height: lh },
    visualViewport: { offsetLeft: Math.round(vv.offsetLeft), offsetTop: Math.round(vv.offsetTop),
                      width: Math.round(vv.width), height: Math.round(vv.height), scale: +vv.scale.toFixed(3) },
    documentWidth: Math.max(doc.scrollWidth, document.body ? document.body.scrollWidth : 0),
    scroll: { x: Math.round(window.scrollX), y: Math.round(window.scrollY), maxY: Math.max(0, Math.round(doc.scrollHeight - lh)) },
    centerOnScreen: center.onScreen,
    centerHit: center.hit, centerInViewport: center.onScreen,
    points, interceptor,
  };
}"""
)

# Probe tap: capture-phase listeners on window record which element the real
# input pipeline delivers a tap/click to, and cancel it (preventDefault +
# stopImmediatePropagation) so the probe has no side effects on the app.
PROBE_INSTALL_JS = r"""(el) => {
  const events = [];
  const types = ['pointerdown', 'mousedown', 'touchstart', 'pointerup', 'mouseup', 'touchend', 'click'];
  const handler = (e) => {
    events.push({ type: e.type, target: e.target });
    e.preventDefault();
    e.stopImmediatePropagation();
  };
  for (const t of types) window.addEventListener(t, handler, { capture: true, passive: false });
  window.__wxProbe = { el, events, types, handler };
  return true;
}"""

PROBE_READ_JS = (
    "() => {"
    + _HELPERS
    + r"""
  const { describe, styles, overlayRoot, sanitizedHTML } = __wx;
  const p = window.__wxProbe;
  if (!p) return { installed: false, events: [] };
  for (const t of p.types) window.removeEventListener(t, p.handler, { capture: true });
  delete window.__wxProbe;
  const el = p.el;
  const first = p.events.find(e => e.target && e.target.nodeType === 1) || null;
  const out = {
    installed: true,
    events: p.events.map(e => ({ type: e.type, target: describe(e.target && e.target.nodeType === 1 ? e.target : null) })),
    received: false, receivedBy: null, interceptor: null,
  };
  if (!first) return out;
  const t = first.target;
  out.received = t === el || el.contains(t);
  out.receivedBy = describe(t);
  if (!out.received) {
    const root = overlayRoot(t);
    const r = el.getBoundingClientRect(), rr = root.getBoundingClientRect();
    const overlap = {
      width: Math.max(0, Math.min(r.right, rr.right) - Math.max(r.left, rr.left)),
      height: Math.max(0, Math.min(r.bottom, rr.bottom) - Math.max(r.top, rr.top)),
    };
    out.interceptor = {
      element: describe(t), overlayRoot: describe(root), overlayStyles: styles(root), html: sanitizedHTML(root, 2000),
      overlapLayout: { ...overlap, areaRatio: r.width * r.height ? +(overlap.width * overlap.height / (r.width * r.height)).toFixed(3) : 0 },
    };
  }
  return out;
}"""
)

# Elements extending beyond the device width (horizontal overflow culprits).
OVERFLOW_JS = (
    "(deviceWidth) => {"
    + _HELPERS
    + r"""
  const { describe, styles } = __wx;
  const doc = document.documentElement;
  const docWidth = Math.max(doc.scrollWidth, document.body ? document.body.scrollWidth : 0);
  if (docWidth <= deviceWidth + 1) return { overflowPx: 0, documentWidth: docWidth, culprits: [] };
  const all = [...document.body.querySelectorAll('*')];
  const over = all.filter(n => {
    const r = n.getBoundingClientRect();
    return r.width > 0 && r.right + window.scrollX > deviceWidth + 1;
  });
  // Keep the deepest elements: those with no overflowing descendants.
  const deepest = over.filter(n => !over.some(o => o !== n && n.contains(o))).slice(0, 8);
  return {
    overflowPx: docWidth - deviceWidth, documentWidth: docWidth,
    culprits: deepest.map(n => ({ element: describe(n), right: Math.round(n.getBoundingClientRect().right + window.scrollX),
      styles: (({ width, 'min-width': minWidth, display, position }) => ({ width, minWidth, display, position }))(
        Object.assign({}, styles(n), { 'min-width': getComputedStyle(n).minWidth })) })),
  };
}"""
)

SCROLL_TO_BOTTOM_JS = "() => { window.scrollTo(0, document.documentElement.scrollHeight); return Math.round(window.scrollY); }"

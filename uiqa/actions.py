"""Index every action a user could take on a page.

`index_actions(page)` returns one descriptor per interactive element — links,
buttons, inputs, selects, checkboxes, tabs, and the app's data-attribute
widgets — each with a human label and a *stable* selector the scenario runner
can replay. This is what satisfies "index all the actions that can be taken":
the deterministic crawler records the full set per route, and explorer agents
read it to decide what to try (and in what combinations).

Each descriptor is also classified so callers know what's safe to fire
automatically vs. what has real-world side effects (launches the integrated
apply browser, kicks off a pipeline run) or leaves the app (external links).
"""

from __future__ import annotations

from typing import Any

# Endpoints / widgets that do something heavy or irreversible: launch a second
# real browser, spawn the pipeline subprocess, hit the network. The deterministic
# crawler skips these; agents may exercise them deliberately and with care.
_SIDE_EFFECTING_MARKERS = (
    "data-apply-btn", "data-refill-btn", "apply-all-btn", "prepare-top-btn",
    "run-pipeline", "/apply", "/refill", "/run", "/api/apply-all",
    "/api/prepare-top", "/emails/connect", "/emails/sync", "/referrals/discover",
)

# The JS runs in-page and returns plain descriptors; selector synthesis lives
# here so it's identical for every element (id → name → data-attr → nth path).
_INDEX_JS = r"""
() => {
  const SEL = (el) => {
    if (el.id) return '#' + CSS.escape(el.id);
    const name = el.getAttribute('name');
    if (name) return el.tagName.toLowerCase() + '[name="' + name + '"]';
    for (const a of ['data-apply-btn','data-refill-btn','data-company-jump',
                     'data-copy-target','data-cluster-legend','id']) {
      if (el.hasAttribute(a)) {
        const v = el.getAttribute(a);
        return el.tagName.toLowerCase() + '[' + a + (v ? '="' + v + '"' : '') + ']';
      }
    }
    // Fall back to an nth-of-type path from the nearest id'd ancestor.
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 6) {
      let part = node.tagName.toLowerCase();
      if (node.id) { parts.unshift('#' + CSS.escape(node.id)); break; }
      const parent = node.parentElement;
      if (parent) {
        const sibs = [...parent.children].filter(c => c.tagName === node.tagName);
        if (sibs.length > 1) part += ':nth-of-type(' + (sibs.indexOf(node) + 1) + ')';
      }
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(' > ');
  };
  const LABEL = (el) => {
    const t = (el.getAttribute('aria-label') || el.innerText || el.value ||
               el.getAttribute('placeholder') || el.getAttribute('title') ||
               el.getAttribute('name') || '').trim().replace(/\s+/g, ' ');
    return t.slice(0, 80);
  };
  const out = [];
  const seen = new Set();
  const push = (el, role) => {
    if (seen.has(el)) return; seen.add(el);
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return;
    const a = {
      role, tag: el.tagName.toLowerCase(), selector: SEL(el), label: LABEL(el),
      name: el.getAttribute('name') || '', id: el.id || '',
      type: (el.getAttribute('type') || '').toLowerCase(),
      href: el.tagName === 'A' ? (el.getAttribute('href') || '') : '',
      target: el.getAttribute('target') || '',
      disabled: !!el.disabled,
    };
    if (el.tagName === 'SELECT')
      a.options = [...el.options].map(o => o.value).filter(v => v !== '');
    out.push(a);
  };
  document.querySelectorAll('a[href]').forEach(e => push(e, 'link'));
  document.querySelectorAll('button, [role=button]').forEach(e => push(e, 'button'));
  document.querySelectorAll('input').forEach(e => {
    const t = (e.type || 'text').toLowerCase();
    push(e, t === 'checkbox' ? 'checkbox' : t === 'radio' ? 'radio'
         : t === 'file' ? 'file' : t === 'submit' ? 'submit' : 'input');
  });
  document.querySelectorAll('select').forEach(e => push(e, 'select'));
  document.querySelectorAll('textarea').forEach(e => push(e, 'textarea'));
  document.querySelectorAll('[role=tab]').forEach(e => push(e, 'tab'));
  document.querySelectorAll('[data-apply-btn],[data-refill-btn],[data-company-jump],[data-copy-target]')
    .forEach(e => push(e, 'widget'));
  // The forms themselves, so the crawler knows what a submit will POST/GET.
  document.querySelectorAll('form').forEach(f => out.push({
    role: 'form', tag: 'form', selector: SEL(f), label: '',
    method: (f.getAttribute('method') || 'get').toLowerCase(),
    action: f.getAttribute('action') || location.pathname,
  }));
  return out;
}
"""


def index_actions(page) -> list[dict[str, Any]]:
    """All interactive elements on the current page, each classified."""
    try:
        raw = page.evaluate(_INDEX_JS)
    except Exception:  # noqa: BLE001 — a navigating page can race the eval
        return []
    page_origin = _origin(page.url)
    for a in raw:
        _classify(a, page_origin)
    return raw


def _classify(a: dict[str, Any], page_origin: str) -> None:
    href = a.get("href", "")
    action = a.get("action", "")
    blob = " ".join(str(a.get(k, "")) for k in ("id", "selector", "href", "action", "label"))
    a["side_effecting"] = any(m in blob for m in _SIDE_EFFECTING_MARKERS)
    a["external"] = False
    a["navigates"] = a.get("role") in ("link",) and bool(href)
    if href:
        if href.startswith(("mailto:", "tel:")):
            a["external"] = True
        elif href.startswith("http"):
            a["external"] = _origin(href) != page_origin
        a["navigates"] = not href.startswith("#")
    if a.get("target") == "_blank":
        a["external"] = True


def _origin(url: str) -> str:
    from urllib.parse import urlsplit
    s = urlsplit(url)
    return f"{s.scheme}://{s.netloc}"

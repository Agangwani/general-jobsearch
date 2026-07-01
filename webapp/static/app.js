// Copy-to-clipboard for profile fields and resume blocks.
function flash(el, ok = true) {
  const cls = ok ? "copied" : "copy-failed";
  el.classList.add(cls);
  setTimeout(() => el.classList.remove(cls), 700);
}

// Last-resort copy for when the async Clipboard API is unavailable or denied
// (non-secure context, missing permission). A throwaway <textarea> + the legacy
// execCommand path covers those cases without any dependency.
function legacyCopy(text) {
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch (err) {
    return false;
  }
}

// Copy `text`, then flash `el` to show success or failure. A denied/unavailable
// Clipboard API must never surface as an uncaught page error — every rejection
// is caught and we fall back to the legacy path before reporting back.
function copyText(text, el) {
  const fallback = () => flash(el, legacyCopy(text));
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => flash(el, true)).catch(fallback);
  } else {
    fallback();
  }
}

document.addEventListener("click", (e) => {
  const row = e.target.closest("[data-copy]");
  if (row && !e.target.closest("a")) {
    copyText(row.dataset.copy, row);
    return;
  }
  const btn = e.target.closest("[data-copy-target]");
  if (btn) {
    const src = document.getElementById(btn.dataset.copyTarget);
    if (src) copyText(src.dataset.copy || src.textContent, btn);
  }
});

// Auto-fill apply flow. Works from the job page button and the per-row ⚡
// buttons — each click opens its own tab in the shared integrated browser,
// auto-fills the form, and reports progress. Submission stays manual.
async function startApply(btn, action = "apply") {
  const box = document.getElementById("apply-state"); // job page only
  const compact = !!btn.dataset.compact;
  const original = btn.textContent;
  const refill = action === "refill";
  const show = (msg, ok) => {
    if (box) { box.hidden = false; box.textContent = msg; box.classList.toggle("ok", !!ok); }
    btn.title = msg;
  };
  const short = (t) => { if (compact) btn.textContent = t; };

  btn.disabled = true;
  short(refill ? "Re-filling…" : "Opening…");
  show(refill ? "Re-running auto-fill on the open tab…"
              : "Opening a tab in the integrated browser…");
  const res = await fetch(`/jobs/${btn.dataset.jobId}/${action}`, { method: "POST" });
  if (!res.ok) {
    show("Could not launch — is the job URL missing?"); short("⚡ error");
    btn.disabled = false; return;
  }
  const appId = btn.dataset.applicationId;
  const poll = setInterval(async () => {
    const s = await (await fetch(`/api/apply-status/${appId}`)).json();
    const filled = s.fill && s.fill.filled;
    if (s.state === "open" || s.state === "starting") {
      if (filled) {
        const left = s.fill.skipped ? `, ${s.fill.skipped} left for you` : "";
        show(`Tab open — auto-filled ${filled} field${filled > 1 ? "s" : ""} (${(s.fill.fields || []).join(", ")})${left}. Review everything, then hit submit yourself.`, true);
        short(`✓ ${filled} filled`);
      } else {
        show("Tab open — looking for the application form…");
        short("Tab open…");
      }
    } else if (s.state === "applied" || s.application_status === "applied") {
      show("✓ Submission detected — status set to applied.", true); short("✓ applied");
      clearInterval(poll); setTimeout(() => location.reload(), 1200);
    } else if (s.state === "closed") {
      show("Tab closed without a detected confirmation — set the status manually if you submitted.");
      short(original); clearInterval(poll); btn.disabled = false;
    } else if (s.state === "error") {
      show(`Browser error: ${s.detail}`); short("⚡ error");
      clearInterval(poll); btn.disabled = false;
    }
  }, 1500);
}
document.addEventListener("click", (e) => {
  const applyBtn = e.target.closest("[data-apply-btn]");
  if (applyBtn) { e.preventDefault(); startApply(applyBtn, "apply"); return; }
  const refillBtn = e.target.closest("[data-refill-btn]");
  if (refillBtn) { e.preventDefault(); startApply(refillBtn, "refill"); }
});


// "Fill all open tabs" — adopt every job tab already open in the integrated
// browser and auto-fill it in one go. Submission stays manual, as always.
// Shared by "Fill all open tabs" and "Prepare top 5": after launching tabs,
// poll /api/apply-all-status and show per-tab progress until everything settles.
const applyAllSummary = document.getElementById("apply-all-summary");
const applyAllList = document.getElementById("apply-all-list");
let applyAllPoll = null;
function _tabLabel(s) {
  try {
    const u = new URL(s.url);
    return u.hostname.replace(/^(www|job-boards|boards)\./, "") + u.pathname.slice(0, 22);
  } catch { return s.url || `tab ${s.application_id}`; }
}
function _renderTabs(rows) {
  if (!applyAllList) return;
  applyAllList.hidden = rows.length === 0;
  applyAllList.innerHTML = rows.map((s) => {
    const f = s.fill || {};
    const detail = f.filled ? `${f.filled} filled${f.skipped ? `, ${f.skipped} left` : ""}`
                            : (s.detail || "working…");
    const state = s.state === "applied" ? "submitted" : s.state;
    return `<li><span class="muted">${_tabLabel(s)}</span> — ${state} (${detail})</li>`;
  }).join("");
}
function pollApplySessions(btn, prefix) {
  if (applyAllPoll) clearInterval(applyAllPoll);
  // Filled tabs intentionally stay state="open" for the user's manual submit, so
  // we can't wait for them to close. "Settled" = no tab still opening and the
  // total filled count has stopped growing — i.e. auto-fill is done.
  let idleTicks = 0, lastFilled = -1;
  applyAllPoll = setInterval(async () => {
    const data = (await (await fetch("/api/apply-all-status")).json()).sessions || [];
    _renderTabs(data);
    const filled = data.reduce((n, s) => n + ((s.fill && s.fill.filled) || 0), 0);
    const opening = data.filter((s) => s.state === "starting").length;
    const settled = opening === 0 && filled === lastFilled;
    lastFilled = filled;
    if (applyAllSummary)
      applyAllSummary.textContent = `${prefix}${data.length} tab(s), ${filled} field(s) filled`
        + (settled ? "" : " — filling…");
    idleTicks = settled ? idleTicks + 1 : 0;
    if (idleTicks >= 2) {  // stable for two ticks → done; tabs stay open for review
      clearInterval(applyAllPoll); applyAllPoll = null;
      if (btn) btn.disabled = false;
      if (applyAllSummary && data.length)
        applyAllSummary.textContent += " — done. Review each tab, then submit yourself.";
    }
  }, 1500);
}

// POST helper that distinguishes a real server response from a failed request
// (e.g. a 404 because the running server predates a new route → needs a restart).
const STALE_MSG = "Couldn't reach this action on the server — it's likely running older "
  + "code. Restart the web app to load the latest changes, then retry.";
async function _postJson(url) {
  const r = await fetch(url, { method: "POST" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

const applyAllBtn = document.getElementById("apply-all-btn");
if (applyAllBtn) {
  applyAllBtn.addEventListener("click", async () => {
    applyAllBtn.disabled = true;
    if (applyAllSummary) applyAllSummary.textContent = "Scanning open tabs…";
    let res;
    try { res = await _postJson("/api/apply-all"); }
    catch { if (applyAllSummary) applyAllSummary.textContent = STALE_MSG; applyAllBtn.disabled = false; return; }
    if (!res.requested) {
      if (applyAllSummary) applyAllSummary.textContent = res.detail || "Nothing to fill.";
      applyAllBtn.disabled = false; return;
    }
    pollApplySessions(applyAllBtn, "");
  });
}

const prepareTopBtn = document.getElementById("prepare-top-btn");
if (prepareTopBtn) {
  prepareTopBtn.addEventListener("click", async () => {
    prepareTopBtn.disabled = true;
    if (applyAllSummary) applyAllSummary.textContent = "Picking the best-fit jobs and opening tabs…";
    let res;
    try { res = await _postJson("/api/prepare-top"); }
    catch { if (applyAllSummary) applyAllSummary.textContent = STALE_MSG; prepareTopBtn.disabled = false; return; }
    if (!res.count) {
      if (applyAllSummary) applyAllSummary.textContent = "No applyable jobs found — ingest a run first.";
      prepareTopBtn.disabled = false; return;
    }
    pollApplySessions(prepareTopBtn, `Opened ${res.count} · `);
  });
}

// Bulk-select: checkboxes + "Mark selected as applied" (a plain form post to
// /applications/bulk-status). JS just manages the bar, the count, and select-all.
const bulkForm = document.getElementById("bulk-form");
if (bulkForm) {
  const bar = document.getElementById("bulk-bar");
  const count = document.getElementById("bulk-count");
  const selectAll = document.getElementById("select-all");
  const rowChecks = () => Array.from(bulkForm.querySelectorAll(".row-check"));
  const refresh = () => {
    const boxes = rowChecks();
    const n = boxes.filter((c) => c.checked).length;
    if (bar) bar.style.display = n ? "flex" : "none";  // inline display, so toggle it (not [hidden])
    if (count) count.textContent = `${n} selected`;
    if (selectAll) selectAll.checked = n > 0 && n === boxes.length;
  };
  bulkForm.addEventListener("change", (e) => {
    if (e.target === selectAll) rowChecks().forEach((c) => { c.checked = selectAll.checked; });
    refresh();
  });
  refresh();
}

// Per-row status change on the dashboard: POST to /applications/{id}/status and
// reload so the row moves into the To apply / In progress / Applied tab. The
// <select> has no name, so it never participates in the bulk-apply form submit.
document.addEventListener("change", async (e) => {
  const sel = e.target.closest(".row-status");
  if (!sel) return;
  sel.disabled = true;
  try {
    await fetch(`/applications/${sel.dataset.applicationId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ status: sel.value }),
      redirect: "manual",
    });
  } catch { /* ignore — the reload reflects server truth */ }
  location.reload();
});


// Company LeetCode quick-jump <select> on the prep page: navigate to the
// chosen company's questions page. The <select> has no name, so it never
// participates in any surrounding form submit.
document.addEventListener("change", (e) => {
  const sel = e.target.closest("[data-company-jump]");
  if (sel && sel.value) window.location.href = sel.value;
});


// Run-pipeline button: kick off a run and stream its log into the panel.
// The log is the pipeline's own stderr — per-company fetch counts included.
// Track-aware: the main "Run pipeline" button drives the "main" track; the
// Startups page drives "startups". Both share the one run panel + ingest.
(function runPanel() {
  const panel = document.getElementById("run-panel");
  const logEl = document.getElementById("run-log");
  const status = document.getElementById("run-status");
  const runBtn = document.getElementById("run-pipeline");
  if (!panel) return;
  let cursor = 0;
  const hideBtn = document.getElementById("run-hide");
  if (hideBtn) hideBtn.addEventListener("click", () => panel.hidden = true);

  const label = (t) => t === "startups" ? "startup pipeline" : "pipeline";

  async function poll(track) {
    const snap = await (await fetch(`/run/log?since=${cursor}&track=${track}`)).json();
    if (snap.lines.length) {
      logEl.textContent += snap.lines.join("\n") + "\n";
      logEl.scrollTop = logEl.scrollHeight;
    }
    cursor = snap.next;
    if (snap.running) {
      setTimeout(() => poll(track), 1000);
    } else if (snap.exit_code !== null) {
      const ok = snap.exit_code === 0;
      status.textContent = ok ? `✓ ${label(track)} finished — results ingested`
                              : `✗ ${label(track)} failed (exit ${snap.exit_code})`;
      if (runBtn) { runBtn.disabled = false; runBtn.textContent = "▶ Run pipeline"; }
    }
  }

  // Exposed so any page (e.g. the Startups page) can launch a tracked run.
  window.startRunPolling = async function (track) {
    track = track || "main";
    const resp = await fetch(`/run?track=${track}`, { method: "POST" });
    panel.hidden = false;
    status.textContent = resp.status === 409
      ? `A ${label(track)} run is already in progress — attaching to its log…`
      : `Running ${label(track)}…`;
    if (resp.status !== 409) { logEl.textContent = ""; cursor = 0; }
    poll(track);
  };

  if (runBtn) {
    runBtn.addEventListener("click", () => {
      runBtn.disabled = true;
      runBtn.textContent = "Running…";
      window.startRunPolling("main");
    });
  }
})();


// ===========================================================================
// Aurora UI enhancements — all progressive, none required for functionality.
// ===========================================================================

// Theme toggle (light / dark), persisted in localStorage. Until the user makes
// an explicit choice, the theme follows the OS (prefers-color-scheme).
const themeToggle = document.getElementById("theme-toggle");
if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const root = document.documentElement;
    const explicit = root.getAttribute("data-theme");
    const systemDark = window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    const currentlyDark = explicit ? explicit === "dark" : systemDark;
    const next = currentlyDark ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) { /* private mode */ }
  });
}

// Count-up for the dashboard stat numbers. The final value is already rendered
// server-side, so this only animates from 0 → value when motion is welcome.
(function countUp() {
  const reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const nums = document.querySelectorAll(".stat-num[data-count]");
  if (!nums.length || reduce) return;
  nums.forEach((el) => {
    const target = parseInt(el.dataset.count, 10) || 0;
    if (target <= 0) return;
    const dur = 700, start = performance.now();
    el.textContent = "0";
    const tick = (now) => {
      const p = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
      el.textContent = Math.round(target * eased);
      if (p < 1) requestAnimationFrame(tick);
      else el.textContent = String(target);
    };
    requestAnimationFrame(tick);
  });
})();

// Strengthen the nav hairline + shadow once the page is scrolled.
(function navShadow() {
  const nav = document.getElementById("topnav");
  if (!nav) return;
  const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 4);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });
})();


// ===========================================================================
// Cluster fit map (/clusters and /clusters/job/{id}). Renders the 2-D TF-IDF
// projection emitted by the pipeline (reports/clustering.json) as an SVG
// scatter: postings coloured by K-means cluster, the resume as a ★, cluster
// centres as rings. On the per-job page one posting is focused (highlight).
// Pure progressive enhancement — the page is fully useful without it.
// ===========================================================================
(function clusterMap() {
  const host = document.getElementById("cluster-map");
  const dataEl = document.getElementById("cluster-map-data");
  if (!host || !dataEl) return;
  let data;
  try { data = JSON.parse(dataEl.textContent); } catch { return; }
  const points = data.points || [];
  const clusters = data.clusters || [];
  const SVGNS = "http://www.w3.org/2000/svg";

  // Distinct, theme-agnostic hue per cluster (golden-angle spacing). The same
  // function colours the legend swatches in the page, keeping them in sync.
  const colorFor = (id) => `hsl(${(((id * 137.508) % 360) + 360) % 360}, 66%, 52%)`;
  document.querySelectorAll("[data-cluster-swatch]").forEach((sw) => {
    sw.style.background = colorFor(parseInt(sw.dataset.clusterSwatch, 10) || 0);
  });
  if (!points.length) return;

  const css = (name, fallback) =>
    (getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback);
  const accent = css("--accent", "#0a84ff");
  const inkMuted = css("--muted", "#8e8e93");

  const W = 1000, H = 600, PAD = 46;
  const centroids = clusters.filter((c) => c.centroid).map((c) => ({ id: c.id, ...c.centroid }));
  const resume = (data.resume && data.resume.x != null) ? data.resume : null;
  const all = points.concat(centroids, resume ? [resume] : []);
  const xs = all.map((p) => p.x), ys = all.map((p) => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = (maxX - minX) || 1, spanY = (maxY - minY) || 1;
  const scale = Math.min((W - 2 * PAD) / spanX, (H - 2 * PAD) / spanY);
  const offX = PAD + (W - 2 * PAD - spanX * scale) / 2;
  const offY = PAD + (H - 2 * PAD - spanY * scale) / 2;
  const sx = (x) => offX + (x - minX) * scale;
  const sy = (y) => H - (offY + (y - minY) * scale);  // flip: data-up → screen-up

  const el = (tag, attrs) => {
    const n = document.createElementNS(SVGNS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  };
  const star = (cx, cy, r) => {
    let d = "";
    for (let i = 0; i < 10; i++) {
      const rad = (i % 2 ? r * 0.45 : r), a = (Math.PI / 5) * i - Math.PI / 2;
      d += (i ? "L" : "M") + (cx + rad * Math.cos(a)).toFixed(1) + "," + (cy + rad * Math.sin(a)).toFixed(1);
    }
    return d + "Z";
  };

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "cluster-svg",
                          preserveAspectRatio: "xMidYMid meet", role: "img",
                          "aria-label": "Scatter map of job postings clustered by resume fit" });
  const focusKey = data.highlight || null;
  const focusPoint = focusKey ? points.find((p) => p.key === focusKey) : null;
  const focusCluster = focusPoint ? focusPoint.cluster : null;

  // --- postings ------------------------------------------------------------
  const dots = [];
  points.forEach((p) => {
    const dimmed = focusPoint && p.cluster !== focusCluster;
    const c = colorFor(p.cluster);
    const node = el("circle", {
      cx: sx(p.x).toFixed(1), cy: sy(p.y).toFixed(1),
      r: 5, class: "cmap-dot" + (p.near_miss ? " is-near" : "") + (dimmed ? " is-dim" : ""),
      fill: p.near_miss ? "transparent" : c, stroke: c,
    });
    if (p.id) node.classList.add("is-link");
    node.__p = p;
    svg.appendChild(node);
    dots.push(node);
  });

  // --- cluster centres -----------------------------------------------------
  centroids.forEach((c) => {
    svg.appendChild(el("circle", { cx: sx(c.x).toFixed(1), cy: sy(c.y).toFixed(1),
      r: 13, class: "cmap-centroid", stroke: colorFor(c.id), fill: "none" }));
    const lbl = el("text", { x: sx(c.x).toFixed(1), y: (sy(c.y) + 4).toFixed(1),
      class: "cmap-centroid-num", fill: colorFor(c.id), "text-anchor": "middle" });
    lbl.textContent = c.id;
    svg.appendChild(lbl);
  });

  // --- resume marker (+ optional link to the focused posting) --------------
  if (resume) {
    if (focusPoint) {
      svg.appendChild(el("line", { x1: sx(resume.x).toFixed(1), y1: sy(resume.y).toFixed(1),
        x2: sx(focusPoint.x).toFixed(1), y2: sy(focusPoint.y).toFixed(1), class: "cmap-link" }));
    }
    // stroke comes from CSS (.cmap-resume) — var() can't resolve as an SVG attr.
    svg.appendChild(el("path", { d: star(sx(resume.x), sy(resume.y), 13),
      class: "cmap-resume", fill: accent }));
    const you = el("text", { x: (sx(resume.x) + 16).toFixed(1), y: (sy(resume.y) + 4).toFixed(1),
      class: "cmap-you", fill: accent });
    you.textContent = "your resume";
    svg.appendChild(you);
  }

  // --- focused posting (drawn last, on top) --------------------------------
  if (focusPoint) {
    // stroke comes from CSS (.cmap-focus).
    svg.appendChild(el("circle", { cx: sx(focusPoint.x).toFixed(1), cy: sy(focusPoint.y).toFixed(1),
      r: 9, class: "cmap-focus", fill: colorFor(focusPoint.cluster) }));
  }
  host.appendChild(svg);

  // --- tooltip -------------------------------------------------------------
  const tip = document.createElement("div");
  tip.className = "cluster-tip";
  tip.hidden = true;
  host.appendChild(tip);
  const showTip = (p, evt) => {
    tip.innerHTML = `<strong>${p.company}</strong><br>${p.title}` +
      `<br><span class="muted">fit ${Math.round(p.fit)} · cluster ${p.cluster}` +
      `${p.near_miss ? " · near-miss" : ""}</span>` +
      (p.id ? `<br><span class="tip-cta">click for the breakdown →</span>` : "");
    tip.hidden = false;
    const r = host.getBoundingClientRect();
    let x = evt.clientX - r.left + 14, y = evt.clientY - r.top + 14;
    x = Math.min(x, r.width - tip.offsetWidth - 8);
    tip.style.left = Math.max(4, x) + "px";
    tip.style.top = Math.max(4, y) + "px";
  };
  dots.forEach((node) => {
    node.addEventListener("mouseenter", (e) => showTip(node.__p, e));
    node.addEventListener("mousemove", (e) => showTip(node.__p, e));
    node.addEventListener("mouseleave", () => { tip.hidden = true; });
    if (node.__p.id) node.addEventListener("click", () => {
      window.location.href = `/clusters/job/${node.__p.id}`;
    });
  });

  // --- legend hover emphasis (cluster cards highlight their points) --------
  document.querySelectorAll("[data-cluster-legend]").forEach((card) => {
    const id = parseInt(card.dataset.clusterLegend, 10);
    const setEmphasis = (on) => dots.forEach((d) => {
      d.classList.toggle("is-dim", on && d.__p.cluster !== id);
      d.classList.toggle("is-hot", on && d.__p.cluster === id);
    });
    card.addEventListener("mouseenter", () => setEmphasis(true));
    card.addEventListener("mouseleave", () => setEmphasis(false));
  });
})();

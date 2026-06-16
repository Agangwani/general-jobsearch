// Copy-to-clipboard for profile fields and resume blocks.
function flash(el) {
  el.classList.add("copied");
  setTimeout(() => el.classList.remove("copied"), 700);
}
document.addEventListener("click", (e) => {
  const row = e.target.closest("[data-copy]");
  if (row && !e.target.closest("a")) {
    navigator.clipboard.writeText(row.dataset.copy).then(() => flash(row));
    return;
  }
  const btn = e.target.closest("[data-copy-target]");
  if (btn) {
    const src = document.getElementById(btn.dataset.copyTarget);
    if (src) navigator.clipboard.writeText(src.dataset.copy || src.textContent).then(() => flash(btn));
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


// Run-pipeline button: kick off a run and stream its log into the panel.
// The log is the pipeline's own stderr — per-company fetch counts included.
const runBtn = document.getElementById("run-pipeline");
if (runBtn) {
  const panel = document.getElementById("run-panel");
  const logEl = document.getElementById("run-log");
  const status = document.getElementById("run-status");
  let cursor = 0;
  document.getElementById("run-hide").addEventListener("click", () => panel.hidden = true);

  async function poll() {
    const snap = await (await fetch(`/run/log?since=${cursor}`)).json();
    if (snap.lines.length) {
      logEl.textContent += snap.lines.join("\n") + "\n";
      logEl.scrollTop = logEl.scrollHeight;
    }
    cursor = snap.next;
    if (snap.running) {
      setTimeout(poll, 1000);
    } else if (snap.exit_code !== null) {
      const ok = snap.exit_code === 0;
      status.textContent = ok ? "✓ Run finished — results ingested" : `✗ Run failed (exit ${snap.exit_code})`;
      runBtn.disabled = false;
      runBtn.textContent = "▶ Run pipeline";
    }
  }

  runBtn.addEventListener("click", async () => {
    const resp = await fetch("/run", { method: "POST" });
    panel.hidden = false;
    status.textContent = resp.status === 409 ? "A run is already in progress — attaching to its log…" : "Running pipeline…";
    if (resp.status !== 409) { logEl.textContent = ""; cursor = 0; }
    runBtn.disabled = true;
    runBtn.textContent = "Running…";
    poll();
  });
}

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
async function startApply(btn) {
  const box = document.getElementById("apply-state"); // job page only
  const compact = !!btn.dataset.compact;
  const original = btn.textContent;
  const show = (msg, ok) => {
    if (box) { box.hidden = false; box.textContent = msg; box.classList.toggle("ok", !!ok); }
    btn.title = msg;
  };
  const short = (t) => { if (compact) btn.textContent = t; };

  btn.disabled = true;
  short("Opening…");
  show("Opening a tab in the integrated browser…");
  const res = await fetch(`/jobs/${btn.dataset.jobId}/apply`, { method: "POST" });
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
  const btn = e.target.closest("[data-apply-btn]");
  if (btn) { e.preventDefault(); startApply(btn); }
});

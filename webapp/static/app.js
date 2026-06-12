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

// Apply flow: launch the integrated browser, then poll until it reports back.
const applyBtn = document.getElementById("apply-btn");
if (applyBtn) {
  const stateBox = document.getElementById("apply-state");
  const show = (msg, ok) => {
    stateBox.hidden = false;
    stateBox.textContent = msg;
    stateBox.classList.toggle("ok", !!ok);
  };
  applyBtn.addEventListener("click", async () => {
    applyBtn.disabled = true;
    show("Launching integrated browser…");
    const res = await fetch(`/jobs/${applyBtn.dataset.jobId}/apply`, { method: "POST" });
    if (!res.ok) { show("Could not launch — is the job URL missing?"); applyBtn.disabled = false; return; }
    const appId = applyBtn.dataset.applicationId;
    const poll = setInterval(async () => {
      const s = await (await fetch(`/api/apply-status/${appId}`)).json();
      if (s.state === "open") {
        show("Browser open — complete the application in the window. Submission is detected automatically.");
      } else if (s.state === "applied" || s.application_status === "applied") {
        show("✓ Application submission detected — status set to applied.", true);
        clearInterval(poll); setTimeout(() => location.reload(), 1200);
      } else if (s.state === "closed") {
        show("Window closed without a detected confirmation — set the status manually if you submitted.");
        clearInterval(poll); applyBtn.disabled = false;
      } else if (s.state === "error") {
        show(`Browser error: ${s.detail}`);
        clearInterval(poll); applyBtn.disabled = false;
      }
    }, 1500);
  });
}

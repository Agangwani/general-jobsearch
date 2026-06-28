/* Portfolio renderer — loads hand-curated content.json + auto-generated activity.json
   and builds the page. No framework, no build step. */

const ICONS = {
  github: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5Z"/></svg>',
  external: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>',
  mail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/></svg>',
  download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
  linkedin: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.63-1.85 3.36-1.85 3.6 0 4.27 2.37 4.27 5.45v6.29ZM5.34 7.43a2.06 2.06 0 1 1 0-4.13 2.06 2.06 0 0 1 0 4.13ZM7.12 20.45H3.56V9h3.56v11.45ZM22.22 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.73V1.73C24 .77 23.2 0 22.22 0Z"/></svg>'
};

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));

function timeAgo(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const days = Math.floor((Date.now() - then) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

async function getJSON(path) {
  try {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) return null;
    return await r.json();
  } catch (_) {
    return null;
  }
}

function repoUrl(repo) {
  return repo ? `https://github.com/${repo}` : null;
}

function renderHero(profile) {
  const name = profile.name || "Agangwani";
  document.title = `${name} — Projects & Resume`;
  $("#heroName").textContent = name;
  $("#heroTagline").textContent = profile.tagline || "";
  document.querySelectorAll('[data-bind="brand"]').forEach((n) => (n.textContent = name));

  const links = profile.links || {};
  const actions = [];
  if (links.github) actions.push(btn(links.github, ICONS.github, "GitHub", true));
  if (links.linkedin) actions.push(btn(links.linkedin, ICONS.linkedin, "LinkedIn", true));
  if (links.email) actions.push(btn(`mailto:${links.email}`, ICONS.mail, "Email"));
  $("#heroActions").innerHTML = actions.join("");

  // Contact section mirrors the same links.
  $("#contactActions").innerHTML = actions.join("") ||
    '<p class="muted">Add links in <code>data/content.json</code>.</p>';
}

function btn(href, icon, label, external) {
  const ext = external ? ' target="_blank" rel="noopener"' : "";
  return `<a class="btn" href="${esc(href)}"${ext}><span class="ic">${icon}</span>${esc(label)}</a>`;
}

function renderProjects(projects, activity) {
  const grid = $("#projectGrid");
  if (!projects || !projects.length) {
    grid.innerHTML = '<div class="loading">No projects configured.</div>';
    return;
  }
  grid.innerHTML = projects.map((p) => projectCard(p, activity)).join("");
}

function projectCard(p, activity) {
  const link = repoUrl(p.repo) || p.url || "#";
  const isRepo = !!p.repo;
  const a = (activity && activity.repos && p.repo) ? activity.repos[p.repo] : null;

  const cardLinks = [];
  if (p.live) {
    cardLinks.push(`<a class="icon-link" href="${esc(p.live)}" target="_blank" rel="noopener" title="Live site">${ICONS.external}</a>`);
  }
  cardLinks.push(`<a class="icon-link" href="${esc(link)}" target="_blank" rel="noopener" title="${isRepo ? "Repository" : "Link"}">${ICONS.github}</a>`);

  const highlights = (p.highlights && p.highlights.length)
    ? `<ul class="highlights">${p.highlights.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>`
    : "";

  const tags = (p.tags && p.tags.length)
    ? `<div class="tags">${p.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>`
    : "";

  return `
    <article class="card${p.placeholder ? " placeholder" : ""}">
      <div class="card-head">
        <div class="card-title">
          <span class="card-emoji">${esc(p.emoji || "📦")}</span>
          <h3>${esc(p.name)}</h3>
        </div>
        <div class="card-links">${cardLinks.join("")}</div>
      </div>
      <p class="card-blurb">${esc(p.blurb || "")}</p>
      ${highlights}
      ${tags}
      ${activityBlock(p, a)}
    </article>`;
}

function activityBlock(p, a) {
  if (!p.repo) {
    return `<div class="activity"><div class="activity-empty">Set this project's <code>repo</code> to show live activity.</div></div>`;
  }
  if (!a || a.error) {
    return `<div class="activity"><div class="activity-empty">Activity will appear after the daily updater runs.</div></div>`;
  }
  const stats = [];
  if (a.pushed_at) stats.push(`<span class="stat live-dot">●</span><span class="stat">Updated <b>${timeAgo(a.pushed_at)}</b></span>`);
  if (typeof a.commits_30d === "number") stats.push(`<span class="stat"><b>${a.commits_30d}</b> commits / 30d</span>`);
  if (typeof a.stars === "number" && a.stars > 0) stats.push(`<span class="stat">★ <b>${a.stars}</b></span>`);

  const commits = (a.recent_commits || []).slice(0, 3).map((c) => `
    <div class="commit">
      <span class="msg"><a href="${esc(c.url || "#")}" target="_blank" rel="noopener">${esc(c.message)}</a></span>
      <span class="when">${esc(timeAgo(c.date))}</span>
    </div>`).join("");

  const commitsBlock = commits
    ? `<div class="commits"><span class="commits-label">Recent changes</span>${commits}</div>`
    : "";

  return `<div class="activity">
    <div class="activity-stats">${stats.join("")}</div>
    ${commitsBlock}
  </div>`;
}

async function renderResume(resume) {
  const card = $("#resumeCard");
  if (!resume || resume.enabled === false) {
    card.style.display = "none";
    return;
  }
  $("#resumeBlurb").textContent = resume.blurb || "";
  const file = resume.file || "resume.pdf";
  let available = false;
  try {
    const r = await fetch(`./${file}`, { method: "HEAD", cache: "no-store" });
    available = r.ok;
  } catch (_) { available = false; }

  $("#resumeAction").innerHTML = available
    ? `<a class="btn btn-primary" href="./${esc(file)}" target="_blank" rel="noopener"><span class="ic">${ICONS.download}</span>Download PDF</a>`
    : `<span class="btn btn-disabled" title="Add portfolio/${esc(file)} to this repo and it goes live."><span class="ic">${ICONS.download}</span>Resume coming soon</span>`;
}

function renderFreshness(activity) {
  if (activity && activity.generated_at) {
    const ago = timeAgo(activity.generated_at);
    if (ago) $("#freshWhen").textContent = ` · refreshed ${ago}`;
  }
}

async function main() {
  const [content, activity] = await Promise.all([
    getJSON("./data/content.json"),
    getJSON("./data/activity.json"),
  ]);

  if (!content) {
    $("#projectGrid").innerHTML = '<div class="loading">Could not load content.json.</div>';
    return;
  }
  renderHero(content.profile || {});
  renderProjects(content.projects || [], activity);
  renderResume(content.resume);
  renderFreshness(activity);
}

main();

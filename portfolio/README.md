# Portfolio site

A single static landing page that showcases the projects and links to each
repo, with a résumé download and a "what's new" feed per project that
**refreshes automatically every day**.

**Live URL (after setup):** https://agangwani.github.io/general-jobsearch/

```
portfolio/
  index.html            # page shell
  assets/style.css      # dark, gradient design system
  assets/main.js        # renders the page from the two JSON files below
  data/content.json     # ← YOU edit this: profile, project blurbs, links
  data/activity.json    # ← AUTO-generated daily (latest commits, etc.) — don't edit
  update.py             # regenerates activity.json from the GitHub API
  resume.pdf            # ← drop your résumé here (optional, see below)
```

## Going live (one-time)

1. **Merge the PR** into `main`.
2. The `Portfolio site` GitHub Action (`.github/workflows/portfolio.yml`) runs
   and deploys the page. It tries to enable Pages automatically; if your repo
   settings block that, go to **Settings → Pages → Build and deployment →
   Source: GitHub Actions** once, then re-run the workflow from the **Actions**
   tab.
3. Your page is live at **https://agangwani.github.io/general-jobsearch/**.

After that it redeploys on every push to `portfolio/**` and once a day on a
schedule, so the per-project activity stays current with no effort.

## Everyday edits

All hand-edited content lives in **`data/content.json`**:

- **Your name / tagline / links** — `profile` block. Set your real display
  name and (optionally) a LinkedIn URL; remove the email line if you'd rather
  not publish it.
- **Résumé** — drop your file at **`portfolio/resume.pdf`** and the "Download
  PDF" button goes live automatically. No file = the button shows a "coming
  soon" state. (Want a different filename or an external link? Change
  `resume.file`.)
- **Marketing project** — set its `repo` to `"Agangwani/<your-marketing-repo>"`.
  That both links the card and makes it auto-update with that repo's commits,
  just like the others. Until then the card links to your repos page.
- **Add a project** — copy any object in the `projects` array, fill in
  `name`, `blurb`, `repo`, `tags`, `highlights`, and (optional) `live`.

You never edit `data/activity.json` — `update.py` rewrites it on every deploy.

## How the daily update works

`update.py` reads every project's `repo` from `content.json` and calls the
GitHub API for its latest commits, last-pushed time, 7/30-day commit counts,
and star count, writing `data/activity.json`. The Action runs it on each deploy
using the built-in `GITHUB_TOKEN` (no secrets to manage), and the page reads
that file at load time. Run it locally with `python portfolio/update.py`.

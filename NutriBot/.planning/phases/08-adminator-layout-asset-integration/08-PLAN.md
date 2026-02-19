# Phase 8: Adminator Layout & Asset Integration — Execution Plan

---
wave: 1
depends_on: []
files_modified: []
autonomous: false
---

## Overview

Integrate Adminator-style layout into NutriBot using Bootstrap 5 CDN and extracted assets. No npm — copy static files from Adminator template and use CDN for Bootstrap.

**Constraint:** No npm on target machine. Use Bootstrap 5 CDN + copy theme.css, themify fonts/CSS from Adminator; hand-write layout CSS.

## must_haves

- [ ] Bootstrap 5 + Adminator-style layout available (CDN + static assets)
- [ ] New base.html uses sidebar, topbar, main content structure
- [ ] Sidebar nav links to all existing NutriBot routes
- [ ] Responsive layout (sidebar collapses on mobile)
- [ ] HTMX script preserved and working

---

# Plan 08-01: Asset Setup (No npm)

---
wave: 1
depends_on: []
files_modified: [static/css/adminator-layout.css, static/css/theme.css]
autonomous: true
---

## Tasks

<task name="static-dir">
Create `static/` directory if missing. Ensure `main.py` mounts `/static` (it already does when static_dir.exists()). Create subdirs: `static/css/`, `static/fonts/themify/`.
</task>

<task name="copy-theme">
Copy `Adminator-admin-dashboard-master/Adminator-admin-dashboard-master/src/assets/styles/utils/theme.css` to `static/css/theme.css`. This file is plain CSS with :root and [data-theme="dark"] variables. No build required.
</task>

<task name="icons">
Use Bootstrap Icons from CDN (no font copying). Link `https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css` in base.html. Use `bi bi-house`, `bi bi-calendar`, `bi bi-bar-chart`, etc. instead of Themify. Simpler than copying Adminator's themify fonts (which may be build-generated).
</task>

<task name="layout-css">
Create `static/css/adminator-layout.css` with layout rules for Adminator-style structure. Reference: `Adminator-admin-dashboard-master/src/index.html` structure. Include: (1) body.app, wrapper for sidebar + main; (2) .sidebar: fixed left, width 256px, background var(--c-bkg-sidebar), z-index; (3) .page-container: margin-left 256px, min-height 100vh; (4) .header.navbar: topbar, full width, background var(--c-bkg-card), border-bottom; (5) .main-content: padding, background var(--c-bkg-body); (6) @media (max-width: 768px): sidebar hidden by default, .page-container margin 0, .sidebar-toggle shows sidebar (use Bootstrap collapse or simple JS to toggle .sidebar-open on body); (7) .sidebar-link, .nav-item styling for menu items. Use CSS variables from theme.css. Keep minimal — enough for layout and nav, not full Adminator component library.
</task>

## Verification

- /static/css/theme.css returns 200
- /static/css/adminator-layout.css returns 200
- CSS variables (--c-bkg-sidebar, etc.) defined in theme.css

---

# Plan 08-02: Base Layout Migration

---
wave: 2
depends_on: [08-01]
files_modified: [templates/base.html]
autonomous: true
---

## Tasks

<task name="base-structure">
Rewrite `templates/base.html` with Adminator layout structure. Structure: (1) DOCTYPE, html, head with meta viewport, title block; (2) Link Bootstrap 5 CSS and Bootstrap Icons from CDN; then theme.css, adminator-layout.css from /static/css/; (3) HTMX script: `https://unpkg.com/htmx.org@1.9.10`; (4) body class="app"; (5) Outer wrapper div; (6) Sidebar div.sidebar with .sidebar-inner, .sidebar-logo (brand "BCSD Child Nutrition"), .sidebar-menu ul with nav items; (7) .page-container div; (8) .header.navbar topbar with #sidebar-toggle button (ti-menu icon), search form (action=/search, method=get), Review Mode toggle link; (9) main.main-content with div for {% block content %}; (10) Bootstrap 5 JS bundle from CDN (https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js) and sidebar-toggle script before </body>. Preserve all existing nav links from current base.html.
</task>

<task name="sidebar-nav">
Populate sidebar with all NutriBot routes. Use Adminator nav-item pattern: `<li class="nav-item"><a class="sidebar-link" href="/path"><span class="icon-holder"><i class="bi bi-house"></i></span><span class="title">Label</span></a></li>`. Map routes: Today (/today), Review (/review), Trends (/trends), History (/history), Comparison (/comparison), Dashboard (/dashboard), Quick Capture (/quick), Inbox (/inbox), Backups (/backups), Presets (/presets), Year Planner (/planner), Calendar (/calendar), Assistant (/assistant), Assistant v2 (/assistant-v2), Evidence (/evidence), Retention (/retention), Exports (/exports), Hygiene (/hygiene), Export (/export), Templates (/templates), New Template (/templates/new), New Task (/tasks/new). Add Search at top (form or link to /search). Add Review Mode link (conditional like current: if review_mode cookie show "Review Mode ON" with distinct style). Use Bootstrap Icons: bi-house, bi-calendar3, bi-bar-chart, bi-folder, bi-envelope, bi-gear, bi-search, etc. — pick appropriate icons per section. Group into logical sections with spacing (e.g. mT-30 on first item) if desired.
</task>

<task name="sidebar-toggle">
Add sidebar toggle for mobile. Button with id="sidebar-toggle" and class="sidebar-toggle" in topbar (use bi-list icon). Use vanilla JS (no jQuery): on click, toggle class "sidebar-open" on body or sidebar. In adminator-layout.css (from 08-01), ensure .sidebar-open .sidebar is visible on mobile when toggled. Alternatively use Bootstrap 5 offcanvas if simpler — but Adminator uses a custom sidebar overlay pattern. Prefer minimal JS: document.getElementById('sidebar-toggle').addEventListener('click', function(){ document.body.classList.toggle('sidebar-open'); });
</task>

<task name="preserve-styles">
Move critical NutriBot-specific styles from current base.html inline styles into a block or separate CSS. Status classes (.status-pending, .status-in_progress, .status-completed), .checklist-item, .note-item, .btn — ensure they still work. Add to adminator-layout.css or a new static/css/nutribot.css. Forms and tables should use Bootstrap classes where possible; keep any HTMX-specific styling.
</task>

## Verification

- GET /today returns 200 with new layout (sidebar + topbar + content)
- Sidebar shows all nav links; each link navigates correctly
- HTMX works (e.g. checklist toggle on task detail)
- Mobile: sidebar collapses; toggle button shows sidebar
- No broken CSS (fonts load, layout renders)
- Review Mode link works (cookie toggle)

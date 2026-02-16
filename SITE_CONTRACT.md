# Site Contract

This document specifies exactly what `mf` assumes about the Hugo site it operates on, and what the Hugo theme must provide to render the content `mf` generates. If you are adapting `mf` for your own site, this is the compatibility checklist. If the metafunctor.com site is ever rebuilt from scratch, this document tells you what structure to recreate.

The assumptions fall into three tiers: Hugo platform conventions, site directory structure, and theme-level contracts. Tier 3 is further divided into what `mf` **generates** and what the theme **consumes** — these are two sides of the same contract.

## Tier 1: Hugo Platform Conventions

These are standard Hugo behaviors. Any Hugo site already satisfies them.

| Assumption | Detail |
|------------|--------|
| Content lives in `content/` | All markdown content under `<site_root>/content/` |
| Static assets in `static/` | Files served verbatim under `<site_root>/static/` |
| YAML front matter | Delimited by `---` lines, parsed as YAML |
| Leaf bundles | `content/<section>/<slug>/index.md` |
| Branch bundles | `content/<section>/<slug>/_index.md` |
| Section `_index.md` | Top-level `_index.md` in each section directory is skipped during content scanning |
| Standard front matter fields | `title`, `date`, `draft`, `tags`, `categories`, `description`, `featured`, `aliases` |
| `hugo.toml` at site root | Used as fallback for `baseURL` resolution in series sync |

These are intentional and should not be abstracted away.

## Tier 2: Site Directory Structure

These are content section names and static asset paths. They are hardcoded in `mf` but could differ across Hugo sites.

### Content Sections

Defined in two places that must stay in sync:

**`SitePaths` dataclass** (`src/mf/core/config.py:23-53`):

| Field | Path | Used by |
|-------|------|---------|
| `papers` | `content/papers` | Paper generation, content scanner |
| `projects` | `content/projects` | Project generation, content scanner |
| `publications` | `content/publications` | Publication generation, content scanner |
| `posts` | `content/post` | Post management, content scanner, auditor |

Note: posts use the **singular** `content/post`, not `content/posts`. This is a metafunctor convention that would trip up many Hugo setups.

**`ContentScanner.CONTENT_TYPES`** (`src/mf/content/scanner.py:106-114`):

| Key | Path | Notes |
|-----|------|-------|
| `post` | `content/post` | Blog posts (singular) |
| `papers` | `content/papers` | All papers |
| `projects` | `content/projects` | GitHub projects |
| `writing` | `content/writing` | Long-form writing (not in SitePaths) |
| `publications` | `content/publications` | Peer-reviewed papers |
| `research` | `content/research` | Research content (not in SitePaths) |
| `series` | `content/series` | Blog series landing pages |

The scanner knows about `writing`, `research`, and `series` sections that SitePaths does not track. These are only scanned for read purposes (analytics, auditing), not generated into.

**`ContentAuditor.DEFAULT_CONTENT_TYPES`** (`src/mf/content/auditor.py:146`):

```python
DEFAULT_CONTENT_TYPES = ("post", "papers", "writing")
```

These are the sections audited by default for `linked_project` references. The `writing` section is metafunctor-specific.

### Static Asset Paths

| Path | Purpose | Source |
|------|---------|--------|
| `static/latex/<slug>/` | Compiled LaTeX HTML output per paper | `SitePaths.latex` |
| `static/latex/<slug>/index.html` | Main HTML rendering of paper | Embedded via iframe in paper pages |
| `static/latex/<slug>/<slug>.pdf` | PDF file for each paper | Referenced in paper front matter |

The `static/latex/` convention is central to how papers work. The paper page embeds `<iframe src="/latex/{slug}/index.html">` and links to `/latex/{slug}/{pdf_file}`.

## Tier 3: Theme Contract

These are front matter fields, taxonomies, and layouts that `mf` generates and that the Hugo theme must understand. This is the tightest coupling.

### Taxonomies

The full taxonomy configuration from `hugo.toml`:

```toml
[taxonomies]
  tag = "tags"
  category = "categories"
  genre = "genres"                        # paper, novel, essay, slides, etc.
  series = "series"                       # multi-part content grouping
  linked_project = "linked-projects"      # NOTE: URL slug differs from field name
```

| Taxonomy | Front matter key | URL path | Purpose | Used by |
|----------|-----------------|----------|---------|---------|
| `tags` | `tags: [...]` | `/tags/` | Global keyword taxonomy | All content types |
| `categories` | `categories: [...]` | `/categories/` | Content classification | Posts |
| `genre` | `genres: [...]` | `/genres/` | Content format type | Papers, writing |
| `series` | `series: [...]` | `/series/` | Multi-part content grouping | Posts |
| `linked_project` | `linked_project: [...]` | `/linked-projects/` | Links content to projects | Posts, papers, writing |

**Important:** The `linked_project` taxonomy uses the URL slug `linked-projects` (with a hyphen), not `linked_project`. This is because `content/projects/` already occupies the `/projects/` URL. The front matter field is still `linked_project` (with underscore).

Hugo's related content system also weights these taxonomies:

```toml
[related]
  [[related.indices]]
    name = "tags"
    weight = 100
  [[related.indices]]
    name = "linked-projects"
    weight = 90
  [[related.indices]]
    name = "categories"
    weight = 80
  [[related.indices]]
    name = "keywords"
    weight = 60
  [[related.indices]]
    name = "date"
    weight = 10
```

### Custom Layouts

| Layout | Set by | Purpose |
|--------|--------|---------|
| `project-landing` | `projects/generator.py:147` | Branch bundle root for rich projects |
| `project-section` | `projects/generator.py:300` | Sub-sections (docs, tutorials, etc.) within rich projects |

These layouts must exist in the theme's `layouts/` directory. Simple (leaf bundle) projects use the default `projects/single.html` layout.

### Papers

**What `mf` generates** (`papers/templates.py`):

```yaml
# Standard Hugo
title: "Paper Title"
slug: "paper-slug"
date: 2024-01-15
draft: false
tags: [statistics, reliability]
featured: true

# Paper-specific
authors:
  - "Author Name"
abstract: "Paper abstract text"
category: "preprint"          # preprint, journal, conference, thesis
stars: 5                      # Quality rating (1-5)
venue: "Journal Name"
status: "published"           # draft, preprint, submitted, published
arxiv_id: "2401.12345"
doi: "10.1234/example"
github_url: "https://github.com/..."
project_url: "/projects/related-project/"
external_url: "https://..."
image: "thumbnail.png"

# PDF display
pdf_file: "paper.pdf"         # Filename only, served from /latex/{slug}/
pdf_size: "1.2 MB"
page_count: 15
pdf_only: false               # true = PDF embed, false = HTML iframe
```

Paper pages also include inline HTML/CSS/JS in the body for the iframe embed or PDF viewer. The CSS classes used are: `.iframe-wrap`, `.action-bar`, `.pdf-container`. These reference CSS custom properties from the theme:

- `--color-border-default` (fallback: `#ddd`)
- `--color-accent-primary` (fallback: `#007acc`)
- `--color-bg-secondary` (fallback: `#f5f5f5`)

**What the theme consumes** (`layouts/papers/`):

The **list layout** (`list.html`) renders a filterable card grid. Each paper card reads:
- `category` — used to filter out non-paper types ("novel", "essay" excluded)
- `stars` — rendered as star icons (0-5), used as sort key
- `authors` — shown in metadata row
- `page_count`, `pdf_size` — shown in metadata row
- `venue` — shown if present
- `abstract` — shown in detailed view
- `tags` — rendered as clickable badges
- `pdf_file` + `slug` — constructs download URL `/latex/{slug}/{pdf_file}`
- `github_url`, `arxiv_id`, `project_url`, `external_url` — action buttons
- `image` — card thumbnail

Client-side features: search by title/authors/tags, sort by date/stars/title/pages, filter by category and tag, toggle detailed/compact view. URL parameters persist filter state.

The **single layout** (`single.html`) reads:
- `related_posts` — resolved via `.Site.GetPage()` to render linked posts
- Uses `.Site.RegularPages.Related()` for automatic related content
- Includes floating TOC partial and Giscus comments

The **homepage** (`layouts/index.html`) shows the top 6 papers sorted by `stars` descending.

### Publications

**What `mf` generates** (`publications/generate.py`):

```yaml
title: "Paper Title"
abstract: "..."
authors:
  - name: "Author Name"       # Note: dict format, not plain string
date: "2024-01-15T00:00:00Z"
tags: [statistics]

publication:                   # Nested under publication:
  type: "journal"
  venue: "Journal Name"
  status: "published"
  doi: "10.1234/example"
  year: 2024

links:
  - name: "GitHub"
    url: "https://github.com/..."
  - name: "Paper"
    url: "/papers/paper-slug/"

# Asset paths (full paths, not filenames)
pdf: "/latex/slug/paper.pdf"
html: "/latex/slug/"
cite: "/latex/slug/cite.bib"
```

Key difference from papers: publications use full paths (`pdf: "/latex/slug/paper.pdf"`) while papers use filenames (`pdf_file: "paper.pdf"`). The theme must handle both patterns.

**What the theme consumes** (`layouts/publications/`):

The **single layout** reads:
- `SubTitle` — subtitle (not generated by mf currently)
- `authors[]` — each with `name` and optional `email`
- `abstract` — full abstract text
- `html`, `pdf` — view/download links
- `links[]` — array of `{name, url}` pairs
- `cite` — path to BibTeX file; if absent, generates BibTeX from front matter
- `doi`, `publisher` — publication metadata
- `tags` — tag links
- Includes BibTeX copy-to-clipboard and download functionality

The **list layout** separates content into two sections:
1. **Peer-reviewed** — entries with `publication.status = "published"` or no `publication` param
2. **Preprints** — entries in `/publications/preprints/` subdirectory

For each entry reads: `publication.venue`, `publication.doi`, `publication.arxiv`, `abstract` (truncated to 200 chars), `html`, `pdf`, `links[]`, `tags`.

### Projects

**What `mf` generates** (`projects/generator.py`):

```yaml
# Standard Hugo
title: "Project Name"
date: 2024-01-15T00:00:00Z
draft: false
description: "One-line description"
featured: false
categories: []
aliases: []                    # Hugo URL redirects

# Nested project metadata
project:
  status: "active"
  type: "library"              # library, tool, application, research, etc.
  year_started: 2024

tech:
  languages:
    - "Python"
  frameworks: []
  topics: ["statistics", "reliability"]

sources:
  github: "https://github.com/user/repo"
  github_pages: "https://user.github.io/repo"
  documentation: ""

packages:
  pypi: "package-name"
  npm: ""
  cran: ""
  r_universe: ""
  crates: ""
  conan: ""
  vcpkg: ""

external_docs:
  readthedocs: "https://..."

papers:
  - title: "Related Paper"
    venue: "Conference"
    year: 2024
    arxiv: "2401.12345"
    doi: "10.1234/..."
    pdf: "/latex/slug/paper.pdf"

metrics:
  stars: 42                    # GitHub stars
  downloads: 0
  citations: 0

image: "screenshot.png"

related_posts:
  - "/post/2024-01-about-project/"
related_projects:
  - "/projects/related-project/"
```

**What the theme consumes** (`layouts/projects/`):

The **single layout** reads the full nested structure:
- `project.status` — rendered as `.status-badge.status-{status}` (dynamic CSS class)
- `project.type` — rendered as `.type-badge`
- `project.year_started` — displayed in sidebar
- `featured` — rendered as `.featured-badge`
- `tech.languages[]` — language list
- `image` — featured image
- `html`, `pdf` — documentation links (same keys as publications)
- `sources.github`, `sources.github_pages`, `sources.documentation` — link buttons
- `packages.pypi`, `packages.cran`, `packages.r_universe`, `packages.npm`, `packages.crates`, `packages.conan`, `packages.vcpkg` — package registry links
- `papers[]` — supports both string refs and `{title, venue, year, arxiv, doi, pdf}` objects (uses `reflect.IsMap` to distinguish)
- `metrics.stars`, `metrics.downloads`, `metrics.citations` — sidebar metrics
- `related_posts[]`, `related_projects[]` — resolved via `.Site.GetPage()` and rendered in `.cross-references-section`
- `.Description` — project description

Layout is a two-column grid: `.project-main-content` (1fr) + `.project-sidebar` (300px, sticky).

The **list layout** reads additional fields not in the nested structure:
- `primary_language` — filter key
- `github_url` — direct GitHub link
- `documentation_url`, `demo_url` — action buttons
- `stars` — quality rating (distinct from `metrics.stars`)
- `github_stars` — GitHub star count for sorting
- `license` — license badge

Client-side features: search, sort by featured/name/stars/date, filter by category and language, grid/list toggle with localStorage persistence.

The **homepage** shows projects where `featured: true`, sorted by stars.

The **packages layout** (`layouts/packages/list.html`) aggregates `packages.pypi`, `packages.cran`, and `packages.r_universe` from all projects to build a unified package registry page with shields.io badges.

### Branch Bundle Sections for Rich Projects

Rich projects (branch bundles) create sub-directories with `_index.md` files:

| Section | Weight | Default title |
|---------|--------|---------------|
| `docs` | 10 | Documentation |
| `tutorials` | 20 | Tutorials |
| `posts` | 25 | Posts |
| `examples` | 30 | Examples |
| `api` | 40 | API Reference |
| `changelog` | 50 | Changelog |

Each section page uses `layout: project-section`.

### Series

**What `mf` generates** (`series/` module):

Series landing pages at `content/series/{slug}/_index.md` with:
```yaml
title: "Series Title"
description: "Series description"
status: "active"              # active, completed, archived
featured: true
tags: [math, programming]
color: "#667eea"              # Hex color for UI
icon: "icon-name"             # Icon identifier
related_projects: [slug1, slug2]
associations:
  featured:                   # Featured artifacts
    - type: "project"
      slug: "project-slug"
    - type: "paper"
      slug: "paper-slug"
  projects: [slug1, slug2]
  papers: [slug1, slug2]
  writing: [slug1, slug2]
  links:
    - name: "External Resource"
      url: "https://..."
```

Posts belong to a series via `series: [series-slug]` in their front matter. Posts are ordered by `series_weight` (ascending), then by `date`.

**What the theme consumes** (`layouts/series/`):

The **list layout** shows all series as cards using `.Data.Terms` taxonomy data. Each card shows the series title, description, and post count.

The **term layout** (individual series page) reads:
- `associations.featured[]` — `{type, slug}` objects mapped to pages: project→`/projects/slug`, paper→`/papers/slug`, writing→`/writing/slug`
- `associations.projects[]`, `associations.papers[]`, `associations.writing[]` — slug lists resolved to pages
- `associations.links[]` — `{name, url}` pairs for external links
- `series_weight` — per-post ordering weight
- Renders a sidebar (desktop >1200px) with quick nav, project/paper/writing lists, external links, and series stats

The **series-navigation partial** is included in post single layouts to show series context with a numbered post list.

### Posts

Posts are managed via `mf posts` (database-free, reads/writes front matter directly). The `set`/`unset`/`feature`/`tag` commands manipulate standard Hugo fields plus:

- `linked_project: [slug]` — Custom taxonomy
- `series: [name]` — Custom taxonomy
- `related_posts: ["/post/..."]`
- `related_projects: ["/projects/..."]`

**What the theme consumes** (`layouts/post/`):

The **single layout** reads:
- `author` — author name
- `tags` — tag links
- `related_projects[]` — resolved via `.Site.GetPage()` as `.related-project-card` elements
- `series[]` — first series used for series navigation partial
- `type` — excluded from standard display if "essay" or "novel"
- `.Date`, `.Lastmod` — compared to show "updated" indicator
- `.ReadingTime` — reading time estimate
- Includes TOC partial, series-navigation partial, and Giscus comments

The **list layout** reads:
- `categories[]` — category badges
- `tags[]` — first 5 shown with "+X more" overflow
- `description` — card preview (falls back to `.Summary` then `.Plain`)
- `.Date`, `.ReadingTime` — metadata display

Client-side features: search, sort by newest/oldest/title, filter by category and tag.

### Writing and Research

These sections are not generated by `mf` but are scanned by `ContentScanner` and audited for `linked_project` references.

**Writing** (`layouts/writing/`) — Long-form content:
- **List layout** separates novels (`writing_type: "novel"`) from essays
- Novels read: `image`, `abstract`, `page_count`, `word_count`, `status`
- Essays read: `context`, `description`, `tags`
- **Single layout** reads: `sidebar_related[]`, `html_path`, `pdf_path`, `github_url`, `page_count`, `word_count`, `status`, `related_posts[]`

**Research** (`layouts/research/`) — Research documents:
- **List layout** reads: `authors`, `venue`, `abstract`, `pdf`, `github`, `doi`
- **Single layout** reads: `html`, `pdf`, `description`, `tags`

These are relevant because `mf content audit` and `mf analytics` scan these sections. If writing/research fields change, audit checks may need updating.

## Hardcoded GitHub Username

Several files contain the hardcoded GitHub username `queelius`:

| File | Line | Context |
|------|------|---------|
| `content/scanner.py:364` | `f"github.com/queelius/{project_slug}"` | Finding content about a project |
| `content/matcher.py:114,125` | `f"github.com/queelius/{slug}"` | Matching content to projects |
| `analytics/aggregator.py:315,516` | `f"github.com/queelius/{slug}"` | Analytics link suggestions |

These construct GitHub URLs for content matching. If a different user operates `mf`, these would need updating. The username should ideally come from configuration or be inferred from the projects database.

## Hardcoded Fallback URL

`series/mkdocs.py:84` has a hardcoded fallback:

```python
return "https://metafunctor.com/"
```

This is used when neither `.mf/config.yaml` `site_url` nor `hugo.toml` `baseURL` provides a URL. It should use a generic fallback or error instead.

## Hugo Configuration Requirements

Beyond content and layouts, `hugo.toml` must configure:

```toml
# Unsafe HTML in markdown (required for paper iframe embeds)
[markup.goldmark.renderer]
  unsafe = true

# Math rendering (LaTeX delimiters in content)
[markup.goldmark.extensions.passthrough]
  enable = true
  [markup.goldmark.extensions.passthrough.delimiters]
    block = [['\[', '\]'], ['$$', '$$']]
    inline = [['\(', '\)']]

# Related content weights
[related]
  [[related.indices]]
    name = "tags"
    weight = 100
  [[related.indices]]
    name = "linked-projects"
    weight = 90
```

The theme is based on **ananke** (`theme = 'ananke'`) with extensive custom layouts overlaid.

## Hardcoded References in Theme

The Hugo layouts contain their own hardcoded values:

| Value | Location | Purpose |
|-------|----------|---------|
| `queelius/metafunctor` | Giscus `data-repo` in papers, projects, post single layouts | Comments system |
| `G-E08ZXTFTTY` | `hugo.toml` Google Analytics | Analytics tracking |
| `metafunctor-com` | `hugo.toml` Disqus shortname | Comments fallback |
| PyPI/CRAN/R-universe author URLs | `hugo.toml` `[params]` | Package registry author pages |

## What You Need to Reproduce This Site

If rebuilding metafunctor.com or adapting `mf` for a new site:

### Minimum (content generation works)

1. **Hugo site with `hugo.toml`** at root
2. **`.mf/` directory** at site root (created by `mf init`)
3. **Content sections**: `content/post/`, `content/papers/`, `content/projects/`, `content/publications/`, `content/series/` (and optionally `content/writing/`, `content/research/`)
4. **Static directory**: `static/latex/` for compiled paper assets
5. **Custom taxonomies**: `linked_project` (URL: `linked-projects`), `series`, and `genre` (URL: `genres`) registered in `hugo.toml`
6. **Unsafe HTML enabled** in Goldmark renderer (for paper iframe embeds)

### Full (theme renders everything correctly)

7. **Custom layouts**: `project-landing` and `project-section` in theme
8. **Section layouts**: `layouts/{papers,projects,publications,series,post,writing,research}/` with list and single templates
9. **Packages layout**: `layouts/packages/list.html` that aggregates project package data
10. **Partials**: `floating-toc.html`, `toc.html`, `series-navigation.html`
11. **Theme support** for nested front matter: `project.*`, `tech.*`, `sources.*`, `packages.*`, `metrics.*`, `publication.*`, `associations.*`
12. **CSS custom properties**: Full design token set including `--color-border-default`, `--color-accent-primary`, `--color-bg-secondary`, `--ink`, `--paper`, `--accent`, spacing/radius/shadow scales
13. **Client-side**: Search/filter/sort JavaScript on list pages for papers, projects, and posts
14. **Giscus comments** integration with theme-aware dark/light sync
15. **Related content** configuration with weighted taxonomy indices

## Gaps Between mf and Theme

Fields the theme reads but `mf` does not currently generate:

| Field | Section | Theme reads | `mf` generates? |
|-------|---------|-------------|-----------------|
| `SubTitle` | publications | Single layout | No |
| `publisher` | publications | Single layout | No |
| `publication.arxiv` | publications | List layout | No (uses `arxiv_id` at top level) |
| `github_stars` | projects | List layout sort | No (uses `metrics.stars`) |
| `demo_url` | projects | List layout action button | No |
| `license` | projects | List layout badge | No |
| `primary_language` | projects | List layout filter | Generated in DB, not in front matter |
| `writing_type` | writing | List layout separation | Not mf-managed |
| `sidebar_related` | writing | Single layout sidebar | Not mf-managed |
| `genre` / `genres` | papers | Taxonomy | Not generated |

These represent either future `mf` enhancements or fields that are manually maintained.

## Future Configurability

The most impactful changes for making `mf` portable:

1. **Content section name map** — Move `CONTENT_TYPES` from class variable to config. The `post` vs `posts` difference alone blocks adoption.
2. **GitHub username** — Read from config or infer from project data instead of hardcoding `queelius`.
3. **Fallback URL** — Remove the `metafunctor.com` default; require explicit configuration.
4. **Front matter schema** — The nested project structure (`project:`, `tech:`, `sources:`, `packages:`, `metrics:`) is the hardest to generalize. Consider flattening or making the nesting configurable per theme.
5. **Taxonomy URL slugs** — The `linked_project` → `linked-projects` URL mapping is a Hugo config concern, but `mf` should document this requirement clearly for new adopters.

These are documented for future work. The current priority is making the coupling explicit, not eliminating it.

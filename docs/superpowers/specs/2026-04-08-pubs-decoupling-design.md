# Spec: Decoupled Publications Database

**Date**: 2026-04-08
**Status**: Approved
**Approach**: Typed dataclass model (Approach 2)

## Summary

Decouple `mf pubs` from `paper_db.json` by introducing a separate `pubs_db.json` database with its own schema, lifecycle tracking, and artifact management. The publication system becomes fully self-contained: no runtime dependency on paper_db.

## Motivation

`mf pubs` currently filters `paper_db.json` for entries with a venue or `status: published`. This couples two different concerns:

- **paper_db**: ingestion pipeline (source repos to Hugo static assets)
- **pubs_db** (new): publication lifecycle (draft to published, with artifacts and timeline)

Decoupling lets each system evolve independently. Publications gain lifecycle states (submitted, under-review, accepted), artifact tracking (slides, posters, videos, photos), and event timelines. The paper ingestion pipeline remains unchanged.

## Data Model

### PubEntry

```python
@dataclass
class PubEntry:
    slug: str
    title: str
    authors: list[dict]      # [{"name": ..., "email": ..., "orcid": ...}]
    date: str                 # ISO date
    status: str               # see Status Lifecycle
    type: str                 # see Publication Types

    # Optional metadata
    abstract: str | None = None
    tags: list[str] = field(default_factory=list)
    venue: str | None = None
    venue_details: dict | None = None   # {name, track, year, location}
    doi: str | None = None
    arxiv_id: str | None = None

    # Artifacts: paths (site-relative) or URLs, all self-contained
    artifacts: dict[str, str | None] = field(default_factory=dict)

    # External links
    links: list[dict] = field(default_factory=list)   # [{"name": ..., "url": ...}]

    # Event log
    timeline: list[dict] = field(default_factory=list) # [{"date": ..., "event": ..., "note": ...}]

    # Source cross-reference (informational only, not used for resolution)
    source_repo: str | None = None  # relative path from ~/github/
```

### Status Lifecycle

```
draft --> preprint --> submitted --> under-review --> accepted --> published
                  \-> withdrawn     \-> rejected --> revised --> resubmitted
```

Valid values: `draft`, `preprint`, `submitted`, `under-review`, `accepted`, `published`, `rejected`, `revised`, `withdrawn`.

### Publication Types

Valid values: `conference paper`, `journal article`, `workshop paper`, `thesis`, `technical report`, `white paper`, `preprint`, `book chapter`.

### Artifacts

Each value is a site-relative path (starting with `/`) or a URL (starting with `http`). Null or absent means the artifact does not exist.

| Key | Description |
|-----|-------------|
| `pdf` | Paper PDF |
| `html` | Web-rendered HTML version |
| `slides` | Presentation slides |
| `poster` | Conference poster |
| `video` | Recorded talk (URL) |
| `bibtex` | BibTeX citation file |
| `supplement` | Supplementary material |
| `code` | Code repository (URL) |
| `data` | Dataset (URL) |
| `photos` | Conference/event photos (directory path or URL) |

## Database

### Storage

File: `.mf/pubs_db.json` in the metafunctor repo (alongside `paper_db.json`).

Format:
```json
{
  "_schema_version": 1,
  "cognitive-mri": {
    "title": "Cognitive MRI of AI Conversations",
    "authors": [{"name": "Alex Towell", "email": "lex@metafunctor.com"}],
    "date": "2025-12-09",
    "status": "published",
    "type": "conference paper",
    "venue": "Complex Networks 2025",
    "artifacts": {
      "pdf": "/latex/cognitive-mri-ai-conversations/paper.pdf",
      "html": "/latex/cognitive-mri-ai-conversations/",
      "slides": "/latex/cognitive-mri-ai-conversations/41_Towell_Alex.pdf",
      "bibtex": "/latex/cognitive-mri-ai-conversations/cite.bib"
    },
    "timeline": [
      {"date": "2025-12-09", "event": "published", "note": "Complex Networks 2025"}
    ]
  }
}
```

### PubsDatabase class

Located in `mf/publications/database.py`.

- `load()` / `save()`: JSON read/write via `safe_write_json` (atomic writes with backup)
- `get(slug) -> PubEntry | None`
- `set(entry: PubEntry)`: upsert by slug, validates before writing
- `remove(slug)`
- `__iter__`: yields slugs
- `__len__`: entry count
- `validate(entry)`: checks required fields (`title`, `status`, `type`), status in allowed set, type in allowed set. Raises `ValueError` on failure. Called by `save()`.

### Config

Add `pubs_db` path to `mf.core.config.get_paths()`, resolved the same way as `paper_db`:
```python
"pubs_db": site_root / ".mf" / "pubs_db.json"
```

## Migration

One-time `mf pubs migrate` command that seeds `pubs_db.json` from `paper_db.json`.

### Inclusion criteria

For each paper_db entry:
1. `status: published` or has `venue` or has non-arxiv DOI: include as `published`
2. Has `arxiv_id`: include as `preprint`
3. `status: draft` with existing PDF/HTML artifacts in `/static/latex/`: include as `draft`
4. Everything else (novels, essays, no artifacts): skip

### Field mapping

| paper_db field | pubs_db field |
|----------------|---------------|
| `title` | `title` |
| `authors` | `authors` (normalize to dict format) |
| `date` | `date` |
| `abstract` | `abstract` |
| `tags` | `tags` |
| `category` | `type` |
| `venue` | `venue` |
| `doi` | `doi` |
| `arxiv_id` | `arxiv_id` |
| `pdf_path` | `artifacts.pdf` |
| `html_path` | `artifacts.html` |
| `cite_path` | `artifacts.bibtex` |
| `github_url` | `artifacts.code` |
| slides found in `links[]` | `artifacts.slides` |
| `source_path` | `source_repo` (strip `~/github/` prefix) |

### Slug mapping

Use the existing publication slug mappings from `generate.py`:
- `reliability-estimation-in-series-systems` -> `math-proj`
- `2016-ieee-int-8-ccts` -> `mab`
- `2015-cs-thesis` -> `cs-thesis`
- `cognitive-mri-ai-conversations` -> `cognitive-mri`
- `ransomware-icci2025` -> `ransomware`

All other entries use their paper_db slug directly.

### Timeline seed

Each migrated entry gets one initial timeline event:
```json
{"date": "<entry date>", "event": "migrated", "note": "Migrated from paper_db"}
```

### Output

Print a summary table: slug, title (truncated), status, included/skipped, reason. Write `pubs_db.json`.

## CLI Commands

All commands in `mf/publications/commands.py`, reading from `pubs_db.json`.

| Command | Description |
|---------|-------------|
| `mf pubs list` | List publications. Flags: `--status`, `--type`, `--tag`, `--venue`, `-q` text search, `--json`. |
| `mf pubs show SLUG` | Show full entry details (formatted JSON panel). |
| `mf pubs add SLUG` | Add new entry. Required: `--title`, `--type`, `--status`. Optional: `--venue`, `--doi`, `--pdf`, `--html`, `--code`, etc. |
| `mf pubs update SLUG` | Update fields. Any flag sets that field: `--status submitted`, `--venue "AAAI 2027"`, `--pdf /latex/foo/paper.pdf`. |
| `mf pubs log SLUG` | Append timeline event. Required: `--event`. Optional: `--note`, `--date` (defaults to today). |
| `mf pubs generate` | Generate Hugo `content/publications/` from pubs_db. Optional: `--slug`, `--force`. |
| `mf pubs migrate` | One-time seed from paper_db. |
| `mf pubs stats` | Counts by status, type, venue. |

Removed as separate commands (subsumed by `list` flags):
- `mf pubs categories` becomes `mf pubs list --type ...`
- `mf pubs tags` becomes `mf pubs list --tag ...`
- `mf pubs preprints` becomes `mf pubs list --status preprint`

## Hugo Integration

### Frontmatter format

`mf pubs generate` writes `content/publications/{slug}/index.md`:

```yaml
---
title: "Cognitive MRI of AI Conversations"
abstract: "..."
authors:
  - name: Alex Towell
    email: lex@metafunctor.com
date: "2025-12-09T00:00:00Z"
publication:
  type: conference paper
  status: published
  venue: Complex Networks 2025
  doi: "..."
  arxiv: "..."
  year: 2025
tags:
  - complex networks
artifacts:
  pdf: /latex/cognitive-mri-ai-conversations/paper.pdf
  html: /latex/cognitive-mri-ai-conversations/
  slides: /latex/cognitive-mri-ai-conversations/41_Towell_Alex.pdf
  bibtex: /latex/cognitive-mri-ai-conversations/cite.bib
links:
  - name: GitHub
    url: https://github.com/queelius/cognitive-mri-conversations
---
```

### Template changes

`layouts/publications/single.html`:
- Read `{{ .Params.artifacts.pdf }}` instead of `{{ .Params.pdf }}`
- Read `{{ .Params.artifacts.html }}` instead of `{{ .Params.html }}`
- Read `{{ .Params.artifacts.bibtex }}` instead of `{{ .Params.cite }}`
- Add buttons for `artifacts.slides`, `artifacts.poster`, `artifacts.video`, `artifacts.photos` when present
- Add status badge in header (colored pill: green=published, yellow=preprint, blue=submitted, gray=draft)

`layouts/publications/list.html`:
- Add status badges next to each entry

### Artifact button icons

| Artifact | Label | Color |
|----------|-------|-------|
| html | Read Online | green (#28a745) |
| pdf | Download PDF | blue (#007acc) |
| slides | Slides | purple (#6f42c1) |
| poster | Poster | teal (#20c997) |
| video | Watch Talk | red (#dc3545) |
| photos | Photos | orange (#fd7e14) |
| bibtex | (handled by cite section) | |
| code | (in links) | |
| data | (in links) | |

### Status badge colors

| Status | Color | Label |
|--------|-------|-------|
| published | green (#28a745) | Published |
| accepted | green (#28a745) | Accepted |
| preprint | yellow (#ffc107) | Preprint |
| submitted | blue (#007acc) | Submitted |
| under-review | blue (#007acc) | Under Review |
| draft | gray (#6c757d) | Draft |
| rejected | red (#dc3545) | Rejected |
| revised | orange (#fd7e14) | Revised |
| withdrawn | gray (#6c757d) | Withdrawn |

## File Changes

### New files
- `mf/publications/database.py`: `PubEntry`, `PubsDatabase`
- `mf/publications/migrate.py`: Migration logic from paper_db
- `.mf/pubs_db.json`: Generated by migration

### Modified files
- `mf/core/config.py`: Add `pubs_db` path
- `mf/publications/commands.py`: Rewrite all commands to use PubsDatabase
- `mf/publications/generate.py`: Read from PubsDatabase, emit `artifacts` frontmatter
- `mf/publications/sync.py`: Rewrite to sync Hugo frontmatter back into pubs_db (reads `content/publications/` and updates pubs_db.json)
- `metafunctor/layouts/publications/single.html`: Artifacts object, status badges
- `metafunctor/layouts/publications/list.html`: Status badges

### Unchanged files
- `mf/core/database.py`: PaperDatabase/PaperEntry remain as-is
- `mf/papers/`: Entire papers pipeline unchanged
- `.mf/paper_db.json`: Not modified

## Non-Goals

- Automatic sync between paper_db and pubs_db
- Replacing paper_db or changing `mf papers`
- Submission tracking (venue deadlines, review portals)
- Co-author management or ORCID lookup
- Changes to `mf papers ingest/generate` pipeline

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`mf` is a CLI toolkit for synchronizing external sources (LaTeX papers, GitHub projects) to the metafunctor.com Hugo static site. It provides database-backed management with automatic backups, GitHub integration, and Hugo content generation.

**Core Identity:** External source → Hugo content synchronization
- Papers: LaTeX source files → Hugo paper pages
- Projects: GitHub repos → Hugo project pages
- Series: External source repos → Hugo series landing pages
- Posts: Direct front matter management (no database)

## Development Commands

```bash
# Install in development mode
pip install -e .
pip install -e ".[dev]"     # With dev dependencies
pip install -e ".[all]"     # With PDF support and dev tools

# Run tests
pytest                       # All tests (1113 tests)
pytest tests/test_core/      # Specific directory
pytest -k "test_backup"      # Tests matching pattern
pytest --cov=mf --cov-report=html  # With coverage

# Type checking and linting
mypy src/mf
ruff check src/mf
```

## Architecture

### Module Structure (`src/mf/`)

| Module | Purpose | Has DB? |
|--------|---------|---------|
| `papers/` | LaTeX paper processing and Hugo content generation | `paper_db.json` |
| `projects/` | GitHub project import, refresh, and content generation | `projects_db.json` |
| `series/` | Content series management and sync with external repos | `series_db.json` |
| `posts/` | Blog post front matter management | No (reads Hugo files directly) |
| `publications/` | Peer-reviewed subset of papers | Uses `paper_db.json` |
| `content/` | Cross-content operations (linking, auditing, scanning) | No |
| `taxonomy/` | Tag/category hygiene (duplicates, orphans, normalization) | No |
| `health/` | Content health checks (links, descriptions, images, stale) | No |
| `analytics/` | Content analytics and insights | No |
| `core/` | Config, database base classes, backup, field ops, integrity | Shared infrastructure |
| `backup/` | Backup management and rollback | No |
| `config/` | Configuration management | No |
| `claude/` | Claude Code integration (skill generation, context helpers) | No |

### CLI Structure (`src/mf/cli.py`)

Entry point using Click. All command groups registered at module level via `main.add_command()`.

**Core (database-backed):**
- `mf papers` — generate, sync, process, set/unset, feature, tag, zenodo, fetch-cff, stats, show, list
- `mf projects` — import, refresh, sync, generate, clean, set/unset, feature, hide, tag, fetch-codemeta, make-rich, stats, show, list
- `mf series` — list, show, stats, sync, create, delete, add/remove, set/unset, feature, tag
- `mf pubs` — generate, sync, list

**Content operations (no database):**
- `mf posts` — list, create, set/unset, feature, tag
- `mf content` — match-projects, about, list-projects, audit (with `--extended`, `--check`, `--severity`)
- `mf taxonomy` — audit, normalize, orphans, stats
- `mf health` — links, descriptions, images, stale, drafts

**Infrastructure:**
- `mf analytics` — projects, gaps, tags, timeline, suggestions, summary
- `mf integrity` — check, fix, orphans
- `mf backup` — Backup management and rollback
- `mf config` — Configuration management
- `mf claude` — Claude Code integration (skill generation, context helpers)

Global options: `--verbose`, `--dry-run`

### Core Layer (`src/mf/core/`)

- `config.py` — 3-tier site root resolution: `MF_SITE_ROOT` env → walk-up for `.mf/` → global config (`~/.config/mf/config.yaml`). Path management via `SitePaths` dataclass. The global config allows `mf` to work from any directory.
- `database.py` — Database classes: `PaperDatabase`, `ProjectsDatabase`, `ProjectsCache`, `SeriesDatabase`
- `backup.py` — Atomic JSON writes with timestamped backups and rotation
- `field_ops.py` — Generic field schema (`FieldDef`, `FieldType`), coercion, validation, and change tracking (`ChangeResult`). Uses `FieldDatabase` protocol. Domain-specific schemas in `papers/field_ops.py`, `projects/field_ops.py`, `series/field_ops.py`.
- `integrity.py` — Cross-database validation and consistency checks
- `crypto.py` — Hash utilities for source file tracking
- `prompts.py` — Interactive prompts

### Key Patterns

**Database pattern:** All databases follow the same interface:
- JSON files with `_comment`, `_example`, `_schema_version` metadata keys
- `load()` / `save()` with automatic backup creation
- `get()`, `set()`, `update()`, `delete()` operations
- `search()` with filters (query, tags, category, etc.)
- Entry dataclasses (`PaperEntry`) with property accessors

**Field operations pattern:** `set`/`unset`/`feature`/`tag` commands share generic infrastructure from `core/field_ops.py`. Each domain (papers, projects, series) defines its own `FIELD_SCHEMA` dict mapping field names to `FieldDef` objects. Common flags: `--regenerate` triggers content regeneration after change, `--off` reverses toggles.

**Posts are database-free:** Unlike papers/projects/series, `mf posts` reads and writes Hugo front matter directly via `ContentScanner` and `FrontMatterEditor`. No `.mf/*.json` involved.

**ContentScanner:** Central content reader in `content/scanner.py`. Scans Hugo content directories, parses front matter, and returns structured items. Used by posts, taxonomy, health, analytics, and content audit.

### Path Resolution

3-tier resolution for finding site root:
1. `MF_SITE_ROOT` environment variable (highest priority, used in tests)
2. Walk up from cwd looking for `.mf/` directory
3. Global config file `~/.config/mf/config.yaml` `site_root` key (allows `mf` to work from any directory)

All paths derived from site root via `get_paths()` → `SitePaths` dataclass.

### Data Files (in `.mf/` directory)

```
.mf/
  paper_db.json           # Paper metadata
  projects_db.json        # Project overrides
  series_db.json          # Series metadata
  config.yaml             # mf configuration
  cache/
    projects.json         # GitHub API cache (gitignored)
  backups/
    papers/               # Paper database backups
    projects/             # Projects database backups
    series/               # Series database backups
```

## Content Generation Workflow

### Papers vs Publications

1. **`/papers/`** — All papers (preprints, drafts, published). Generated FROM `paper_db.json` via `mf papers generate`. Uses `pdf_path`, `html_path`, `cite_path`.

2. **`/publications/`** — Curated subset (peer-reviewed, published only). Generated FROM `paper_db.json` via `mf pubs generate`. Only entries with `status: "published"`, a `venue`, or a DOI.

| paper_db.json | content/papers/ | content/publications/ |
|---------------|-----------------|----------------------|
| `pdf_path`    | `pdf_file` (filename only) | `pdf` (full path) |
| `html_path`   | Used in body HTML | `html` (directory path) |
| `cite_path`   | Used in body HTML | `cite` (full path) |

### Zenodo Integration

`mf papers zenodo` manages DOI registration via the Zenodo API. Requires `ZENODO_API_TOKEN` env var. Supports sandbox mode for testing.

### README URL Rewriting

`projects/readme.py` rewrites relative URLs in imported GitHub READMEs to absolute GitHub URLs (blob/tree/raw.githubusercontent.com).

## Testing

Tests use `tmp_path` fixture for isolation. Key fixtures in `tests/conftest.py`:
- `sample_paper_db`, `sample_projects_db` — Pre-populated test databases
- `mock_site_root` — Creates mock Hugo site structure and sets `MF_SITE_ROOT`

Test directories mirror source: `tests/test_papers/`, `tests/test_projects/`, `tests/test_series/`, `tests/test_posts/`, `tests/test_taxonomy/`, `tests/test_health/`, `tests/test_core/`, `tests/test_publications/`, `tests/test_analytics/`, etc.

## Tool Orchestration

`mf` works with `repoindex` (repo queries) and `crier` (content distribution):
- Use `repoindex events` to check what's changed before updating projects
- Use `mf` for site content generation
- Use `crier` for cross-posting after content is ready

See `ORCHESTRATION.md` for detailed workflows.

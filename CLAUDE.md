# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`mf` is a standalone CLI toolkit for synchronizing external sources (LaTeX papers, GitHub projects, PyPI/CRAN packages) to the metafunctor.com Hugo static site. Extracted from the [metafunctor](https://github.com/queelius/metafunctor) site repo into its own package at [github.com/queelius/mf](https://github.com/queelius/mf).

**Core identity:** External source → JSON database → Hugo content. Databases are truth; Hugo pages are derived artifacts.

**Repo relationship:** `mf` operates on a Hugo site via path resolution (`MF_SITE_ROOT` env → walk-up for `.mf/` → `~/.config/mf/config.yaml`). It has no dependency on the site repo itself.

## Development Commands

```bash
# Install
pip install -e ".[dev]"          # Dev dependencies (pytest, mypy, ruff)
pip install -e ".[all]"          # Everything including PDF support

# Tests (1271 tests)
pytest                            # All tests
pytest tests/test_papers/         # One module
pytest -k "test_backup"           # Pattern match
pytest --cov=mf --cov-report=html # Coverage

# Lint and type check
ruff check src/mf
mypy src/mf
```

Test config is in `pyproject.toml` under `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, `pythonpath = ["src"]`, `addopts = "-v --tb=short"`. Ruff uses `line-length = 100`, ignores E501, targets Python 3.10.

## Architecture

### Module Layout (`src/mf/`)

| Module | Purpose | Database |
|--------|---------|----------|
| `papers/` | LaTeX → Hugo paper pages | `paper_db.json` |
| `projects/` | GitHub repos → Hugo project pages | `projects_db.json` + `cache/projects.json` |
| `series/` | External repo blog series → Hugo series pages | `series_db.json` |
| `packages/` | PyPI/CRAN registry → Hugo package pages | `packages_db.json` |
| `publications/` | Curated peer-reviewed subset of papers | Uses `paper_db.json` |
| `posts/` | Blog post front matter management | None (reads Hugo files directly) |
| `content/` | Cross-content linking, auditing, scanning | None |
| `taxonomy/` | Tag/category hygiene | None |
| `health/` | Content quality checks | None |
| `analytics/` | Content analytics | None |
| `core/` | Config, database base, backup, field ops, integrity | Infrastructure |
| `backup/` | Backup management CLI | None |
| `config/` | Config management CLI | None |
| `claude/` | Claude Code skill generation/installation | None |

### CLI Entry Point (`src/mf/cli.py`)

Click-based CLI. The `main` group accepts `--verbose`/`--dry-run` as global options, stored in a `Context` object passed via `@click.pass_obj`. Command groups are registered via `main.add_command()` at module level.

Command groups: `papers`, `projects`, `series`, `packages`, `pubs`, `posts`, `content`, `taxonomy`, `health`, `analytics`, `integrity`, `backup`, `config`, `claude`.

### Core Layer (`src/mf/core/`)

**`config.py`** — 3-tier site root resolution (env → walk-up → global config). `get_site_root()` is `lru_cache`-decorated — tests must call `config.get_site_root.cache_clear()` before monkeypatching. `SitePaths` frozen dataclass holds all derived paths. `get_paths()` builds `SitePaths` from a site root.

**`database.py`** — `PaperDatabase`, `ProjectsDatabase`, `ProjectsCache`, `SeriesDatabase`, `PackageDatabase`. All follow the same interface: JSON files with `_comment`/`_example`/`_schema_version` metadata keys, `load()`/`save()` with auto-backup, CRUD + `search()` with filters, entry dataclasses (`PaperEntry`, `PackageEntry`, etc.) wrapping `dict[str, Any]`.

**`field_ops.py`** — Generic `FieldDef`/`FieldType`/`ChangeResult` infrastructure. The `FieldDatabase` protocol normalizes set/unset/modify across database types. Each domain module (`papers/field_ops.py`, `projects/field_ops.py`, etc.) defines its own `FIELD_SCHEMA` dict.

**`backup.py`** — `safe_write_json()` does atomic writes with timestamped backups and rotation.

**`integrity.py`** / **`integrity_commands.py`** — Cross-database validation. The CLI is in `integrity_commands.py` (not `integrity/commands.py`), imported directly in `cli.py`.

### Key Patterns

**Database-backed modules** (papers, projects, series, packages) all share: `commands.py` (Click CLI), `field_ops.py` (schema), `generator.py` (Hugo content output), plus domain-specific files. The `set`/`unset`/`feature`/`tag` commands use shared infrastructure from `core/field_ops.py`.

**Posts are database-free:** `mf posts` reads and writes Hugo front matter directly via `ContentScanner` and `FrontMatterEditor`. No `.mf/*.json` involved.

**ContentScanner** (`content/scanner.py`): Central Hugo content reader. Scans content directories, parses YAML front matter, returns structured items. Used by posts, taxonomy, health, analytics, and content audit. Defines `CONTENT_TYPES` mapping section names to paths (note: posts use singular `content/post`, not `content/posts`).

**Registry adapter pattern** (`packages/registries/`): PyPI and CRAN adapters satisfy a `RegistryAdapter` protocol. Users can override by placing scripts in `.mf/registries/`. Each adapter module exposes a module-level `adapter` instance.

### Path Resolution and Data Files

All `mf` data lives in `.mf/` at the Hugo site root (not in this repo):

```
.mf/
  paper_db.json         projects_db.json      series_db.json      packages_db.json
  config.yaml
  cache/projects.json   (gitignored)
  backups/{papers,projects,series,packages}/
  registries/           (user-provided adapter overrides)
```

### Papers vs Publications

`/papers/` = all papers (preprints, drafts, published). `/publications/` = curated subset (peer-reviewed only, filtered by `status: "published"`, venue, or DOI). Both generated from `paper_db.json` but with different front matter schemas — papers use `pdf_file` (filename), publications use `pdf` (full path).

## Testing

Tests use `tmp_path` fixture for isolation. Key fixtures in `tests/conftest.py`:
- `mock_site_root` — Creates full `.mf/` + `content/` structure, monkeypatches `get_site_root()` (with cache clear)
- `create_content_file` — Factory fixture for creating Hugo content files with YAML front matter
- `sample_paper_db`, `sample_projects_db`, `sample_series_db` — Pre-populated test databases

Test directories mirror source: `tests/test_papers/`, `tests/test_projects/`, etc.

## Site Contract

`SITE_CONTRACT.md` documents every assumption `mf` makes about the Hugo site it operates on — content section names, static asset paths, front matter schemas, taxonomy configuration, and theme layouts. Read it before modifying any generator or template code.

Key gotchas documented there:
- Posts use `content/post` (singular), not `content/posts`
- `linked_project` taxonomy has URL slug `linked-projects` (with hyphen) because `/projects/` is taken
- GitHub username `queelius` is hardcoded in `content/scanner.py`, `content/matcher.py`, `analytics/aggregator.py`
- Fallback URL `metafunctor.com` is hardcoded in `series/mkdocs.py`

## Tool Orchestration

`mf` works with `repoindex` (repo queries) and `crier` (content distribution):
- Use `repoindex events` to check what's changed before updating projects
- Use `mf` for site content generation
- Use `crier` for cross-posting after content is ready

See `ORCHESTRATION.md` for detailed workflows.

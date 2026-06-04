# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`mf` is a standalone CLI toolkit for synchronizing external sources (LaTeX papers, GitHub projects, PyPI/CRAN packages) to the metafunctor.com Hugo static site. Extracted from the [metafunctor](https://github.com/queelius/metafunctor) site repo into its own package at [github.com/queelius/mf](https://github.com/queelius/mf).

**Core identity:** External source produces a JSON database, which produces Hugo content. Databases are truth; Hugo pages are derived artifacts.

**Repo relationship:** `mf` operates on a Hugo site via path resolution (`MF_SITE_ROOT` env, then walk-up for `.mf/`, then `~/.config/mf/config.yaml`). It has no dependency on the site repo itself.

## Development Commands

```bash
# Install
pip install -e ".[dev]"          # Dev dependencies (pytest, mypy, ruff)
pip install -e ".[all]"          # Everything including PDF support

# Tests (~1370, growing)
pytest                            # All tests
pytest tests/test_papers/         # One module
pytest tests/test_papers/test_commands.py::test_set  # One test
pytest -k "test_backup"           # Pattern match
pytest --cov=mf --cov-report=html # Coverage (HTML at htmlcov/index.html)

# Lint and type check
ruff check src/mf
mypy src/mf
```

Test config is in `pyproject.toml` under `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, `pythonpath = ["src"]`, `addopts = "-v --tb=short"`. Ruff uses `line-length = 100`, ignores E501, targets Python 3.10.

## Architecture

### Module Layout (`src/mf/`)

| Module | Purpose | Database |
|--------|---------|----------|
| `papers/` | Ingest pre-built paper artifacts into Hugo paper pages | `paper_db.json` |
| `projects/` | GitHub repos into Hugo project pages | `projects_db.json` + `cache/projects.json` |
| `series/` | External repo blog series into Hugo series pages | `series_db.json` |
| `packages/` | PyPI/CRAN registry into Hugo package pages | `packages_db.json` |
| `publications/` | Scholarly publication registry with lifecycle tracking | `pubs_db.json` |
| `posts/` | Blog post front matter management | None (reads Hugo files directly) |
| `content/` | Cross-content linking, auditing, scanning | None |
| `taxonomy/` | Tag/category hygiene | None |
| `health/` | Content quality checks | None |
| `analytics/` | Content analytics | None |
| `core/` | Config, database base, backup, field ops, integrity | Infrastructure |
| `backup/` | Backup management CLI | None |
| `config/` | Config management CLI | None |

### CLI Entry Point (`src/mf/cli.py`)

Click-based CLI. The `main` group accepts `--verbose`/`--dry-run` as global options, stored in a `Context` object passed via `@click.pass_obj`. Command groups are registered via `main.add_command()` at module level.

Command groups: `papers`, `projects`, `series`, `packages`, `pubs`, `posts`, `content`, `taxonomy`, `health`, `analytics`, `integrity`, `backup`, `config`.

### Core Layer (`src/mf/core/`)

**`config.py`** does 3-tier site root resolution (env, then walk-up, then global config). `get_site_root()` is `lru_cache`-decorated, so tests must call `config.get_site_root.cache_clear()` before monkeypatching. `SitePaths` frozen dataclass holds all derived paths. `get_paths()` builds `SitePaths` from a site root.

**`database.py`** has `PaperDatabase`, `ProjectsDatabase`, `ProjectsCache`, `SeriesDatabase`, `PackageDatabase`. All follow the same interface: JSON files with `_comment`/`_example`/`_schema_version` metadata keys, `load()`/`save()` with auto-backup, CRUD + `search()` with filters, entry dataclasses (`PaperEntry`, `PackageEntry`, etc.) wrapping `dict[str, Any]`.

**`field_ops.py`** has generic `FieldDef`/`FieldType`/`ChangeResult` infrastructure. The `FieldDatabase` protocol normalizes set/unset/modify across database types. Each domain module (`papers/field_ops.py`, `projects/field_ops.py`, etc.) defines its own `FIELD_SCHEMA` dict.

**`backup.py`** has `safe_write_json()`, which does atomic writes with timestamped backups and rotation.

**`integrity.py`** and **`integrity_commands.py`** handle cross-database validation. The CLI is in `integrity_commands.py` (not `integrity/commands.py`), imported directly in `cli.py`.

**`crypto.py`** has `compute_file_hash()` for artifact integrity checks (used by papers ingest, pubs pull/check). **`prompts.py`** has interactive prompt helpers (`confirm`, `prompt_choice`) used by destructive commands.

### Key Patterns

**Database-backed modules** (papers, projects, series, packages, publications) all share: `commands.py` (Click CLI), `generator.py` (Hugo content output), plus domain-specific files. Papers, projects, series, and packages also have `field_ops.py` (schema) with shared `set`/`unset`/`feature`/`tag` commands from `core/field_ops.py`. Publications uses a standalone `PubsDatabase` with `PubEntry` dataclass (validated fields, lifecycle tracking).

**Publications submodule structure:** `publications/` has expanded beyond the standard template into multiple files: `database.py` (PubEntry + PubsDatabase), `generate.py` (Hugo output), `migrate.py` (one-time `paper_db` to `pubs_db` seed), `pull.py` (copy artifacts from source repos into `static/`), `sync.py` (back-sync metadata from `content/publications/` to `paper_db`), and `zenodo.py` (DOI minting via Zenodo API). The CLI surface includes `add`/`update`/`list`/`show`/`stats`/`log`/`generate`/`migrate`/`pull`/`check`/`zenodo` subcommands.

**Read-only audit pattern:** Several modules expose diagnostic commands that find drift without modifying anything: `mf series audit` and `mf series audit-nav` (drift between `series_db`, source repos, and Hugo content), `mf series diff` (per-post body and frontmatter drift), `mf papers diff` / `mf projects diff` / `mf packages diff` / `mf pubs diff` (render drift: whether the on-disk Hugo page matches what `generate` would produce now), `mf content audit` (linked_project taxonomy refs), `mf integrity check` (cross-database consistency), `mf health check` (content quality). Each writes findings to a structured report; remediation is always a separate explicit command.

**Posts are database-free:** `mf posts` reads and writes Hugo front matter directly via `ContentScanner` and `FrontMatterEditor`. No `.mf/*.json` involved.

**ContentScanner** (`content/scanner.py`): Central Hugo content reader. Scans content directories, parses YAML front matter, returns structured items. Used by posts, taxonomy, health, analytics, and content audit. Defines `CONTENT_TYPES` mapping section names to paths (note: posts use singular `content/post`, not `content/posts`).

**Registry adapter pattern** (`packages/registries/`): PyPI and CRAN adapters satisfy a `RegistryAdapter` protocol. Users can override by placing scripts in `.mf/registries/`. Each adapter module exposes a module-level `adapter` instance.

**Lazy imports inside Click commands:** Every `commands.py` module imports its heavy dependencies *inside* command function bodies, not at module top. `mf --help` should not transitively load `requests`, the registry adapters, or the PDF code path. Do not hoist these imports during refactoring; the lazy form is intentional and load-bearing for CLI responsiveness.

**Render-drift engine** (`core/drift.py`): The four projection modules (papers, projects, packages, publications) each split their generator into a pure `render_*_page(...) -> str` and a separate write path. `core/drift.py` defines a `Renderer` protocol (the per-module binding seam, mirroring `core/field_ops.py`), `check_render_drift` (compares each on-disk page against a fresh render using semantic frontmatter-plus-body equality, never textual YAML), and the shared `run_diff_command` / `print_dry_run_preview` helpers. This powers `mf <module> diff` (read-only) and the enriched `generate --dry-run`, which reports `would create|update|skip` per page. The render functions must be deterministic (no wall-clock dates; papers pins a date into `paper_db` on first generate so it stays stable). The generic `parse_post` / `parse_text` / `frontmatter_equal` primitives live in `core/frontmatter.py`, with series-specific ownership tiers layered on top in `series/frontmatter.py`.

### House Style

- **No em-dashes (U+2014).** A repo-level hook (`check-banned-phrases.sh` from the soul plugin) scans every file write and rejects the em-dash character. The hook checks the *whole file*, not just the diff, so an edit to a file that already contains em-dashes will be rejected on the legacy content. Use commas, colons, periods, or parentheses instead. This applies uniformly to code comments, prose, JSON, and YAML. The cleanest path when touching a non-compliant file is a full `Write` rewrite that fixes all instances in one shot.
- **All destructive commands support `--dry-run`.** Read `ctx.dry_run` from the global Click context (via `@click.pass_obj`) and gate every mutation, not just the final `db.save()`. `Entry.update()` mutates the in-memory database in-place *before* save, so dry-run paths must skip the mutation itself; gating only `db.save()` lets in-memory state diverge from disk and breaks any code that reads after the mutation in the same process.
- **Read-only commands stay read-only.** `mf series audit`, `mf pubs check`, `mf integrity check`, `mf content audit`, and `mf health check` may not write to disk under any branch. If a check needs to record state (e.g., last-audit timestamp), promote it out of the audit command into a separate explicit command.

### Path Resolution and Data Files

All `mf` data lives in `.mf/` at the Hugo site root (not in this repo):

```
.mf/
  paper_db.json         projects_db.json      series_db.json      packages_db.json
  pubs_db.json
  config.yaml
  cache/projects.json   (gitignored)
  backups/{papers,projects,series,packages,pubs}/
  registries/           (user-provided adapter overrides)
```

### Papers vs Publications

`/papers/` and `/publications/` are **independent modules with separate databases**.

- **Papers** (`paper_db.json`) track source files and build artifacts. `mf papers ingest` copies pre-built HTML/PDF from paper repos into `/static/latex/{slug}/`. `mf papers generate` creates Hugo content from the artifacts. Papers cover all papers regardless of publication status. Build is decoupled: paper repos own their Makefiles with `pdf` and `html` targets, and `mf` only ingests pre-built outputs (see `PAPER_BUILD_DECOUPLING.md`).

- **Publications** (`pubs_db.json`) are a scholarly registry with lifecycle tracking (draft, submitted, accepted, published), artifact URLs, timeline events, and venue metadata. `mf pubs generate` creates Hugo content from `pubs_db.json`. The two databases can share slugs but neither depends on the other at runtime. `mf pubs migrate` is a one-time tool to seed `pubs_db.json` from legacy `paper_db.json` entries.

## Testing

Tests use `tmp_path` fixture for isolation. Key fixtures in `tests/conftest.py`:
- `mock_site_root`: Creates full `.mf/` + `content/` structure, monkeypatches `get_site_root()` (with cache clear)
- `create_content_file`: Factory fixture for creating Hugo content files with YAML front matter
- `sample_paper_db`, `sample_projects_db`, `sample_series_db`: Pre-populated test databases

Test directories mirror source: `tests/test_papers/`, `tests/test_projects/`, etc. CLI tests use Click's `CliRunner` plus the `mock_site_root` fixture; HTTP-fetching code is mocked at the call site (e.g., patch `mf.packages.registries.pypi.fetch_json`).

**Shared mutable entry gotcha:** `Entry.data` is the same `dict` object as `db._data[slug]`. Calling `entry.update(...)` mutates the database in-place immediately, *before* `db.save()`. Dry-run code paths must gate the mutation itself, not just the save.

## Site Contract

`SITE_CONTRACT.md` documents every assumption `mf` makes about the Hugo site it operates on: content section names, static asset paths, front matter schemas, taxonomy configuration, and theme layouts. Read it before modifying any generator or template code.

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

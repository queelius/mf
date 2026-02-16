# mf

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

A CLI toolkit for synchronizing external content sources to a Hugo static site.

## The Problem

A personal site accumulates content from many sources: LaTeX papers, GitHub projects, publication records, blog post series. Keeping Hugo pages in sync with these sources is tedious:

- A paper gets updated, but the Hugo page still shows the old abstract
- A GitHub project description changes, but the site doesn't reflect it
- You write posts about a project but forget to link them together
- Database files drift out of sync with content files

Manual synchronization doesn't scale. You need automation that understands your content model.

## The Approach

`mf` treats Hugo content generation as a **sync problem**:

```
External Source → Database → Hugo Content
     (LaTeX)       (JSON)     (Markdown)
     (GitHub)
```

Each source type has:
- A **processor** that extracts metadata from the source
- A **database** that stores canonical state (JSON with automatic backups)
- A **generator** that produces Hugo content pages

The databases are the source of truth. Hugo pages are derived artifacts. When sources change, you re-sync; when you need to regenerate pages, the data is already there.

## What It Does

**Papers**: Process LaTeX sources, extract metadata (title, abstract, authors), track PDF files, generate Hugo paper pages with embedded PDFs.

**Projects**: Import GitHub repositories, cache metadata (description, stars, languages), generate Hugo project pages. Refresh stale data on demand.

**Series**: Sync blog post series from external repositories. Pull posts in, push edits out.

**Content Linking**: Automatically find posts that mention projects and add `linked_project` taxonomy entries.

**Analytics**: Understand your content—which projects lack documentation, which tags are overused, what could be cross-linked.

**Integrity**: Validate database consistency, find orphaned entries, auto-fix common issues.

## Installation

```bash
git clone https://github.com/queelius/mf.git
cd mf
pip install -e .

# With PDF support (thumbnails, page counts)
pip install -e ".[pdf]"

# With dev tools (pytest, mypy, ruff)
pip install -e ".[dev]"

# Everything
pip install -e ".[all]"
```

Requires Python 3.10+.

## Quick Start

```bash
# Initialize the .mf/ directory
mf init

# Import your GitHub projects
mf projects import --user <username>

# Generate Hugo pages
mf projects generate

# Check what needs updating
mf projects refresh --older-than 24
```

## Commands

### Papers

```bash
mf papers process /path/to/paper.tex    # Process LaTeX source
mf papers list                          # List all papers
mf papers sync                          # Check for stale papers
mf papers generate                      # Regenerate Hugo pages
mf papers generate --slug my-paper      # Single paper
mf papers fields                        # List valid paper fields
mf papers set my-paper stars 5          # Set a field value
mf papers unset my-paper venue          # Remove a field
mf papers feature my-paper              # Mark as featured
mf papers tag my-paper --add stats      # Add a tag
```

### Projects

```bash
mf projects import --user <name>        # Import from GitHub
mf projects refresh                     # Update cached data
mf projects refresh --older-than 24     # Only stale entries
mf projects generate                    # Generate Hugo pages
mf projects list --featured             # Show featured projects
mf projects rate-limit                  # Check GitHub API quota
mf projects fields                      # List valid project fields
mf projects set my-proj category library  # Set a field value
mf projects unset my-proj stars         # Remove a field
mf projects feature my-proj             # Mark as featured
mf projects hide my-proj                # Hide from listings
mf projects tag my-proj --add python    # Add a tag
```

### Series

```bash
mf series list                          # Show all series
mf series sync stepanov                 # Pull posts from source repo
mf series sync stepanov --push          # Push edits back to source
mf series add stepanov content/post/... # Add post to series
mf series fields                        # List valid series fields
mf series set my-series status completed  # Set a field value
mf series unset my-series color         # Remove a field
mf series feature my-series             # Mark as featured
mf series tag my-series --add math      # Add a tag
```

### Content

```bash
mf content audit                        # Audit linked_project refs
mf content audit --extended             # Run all quality checks
mf content audit --list-checks          # Show available checks
mf content match-projects               # Auto-link content to projects
mf content about <project>              # Find content about a project
```

### Analytics

```bash
mf analytics summary                    # Full overview
mf analytics gaps                       # Projects without content
mf analytics suggestions                # Recommended links
mf analytics tags                       # Tag distribution
mf analytics timeline                   # Content over time
```

### Integrity

```bash
mf integrity check                      # Validate databases
mf integrity fix --dry-run              # Preview fixes
mf integrity fix -y                     # Apply fixes
mf integrity orphans                    # Find orphaned entries
```

### Infrastructure

```bash
mf backup status                        # Backup health
mf backup list                          # Available backups
mf backup rollback paper_db             # Restore from backup
mf config show                          # Current configuration
```

### Global Options

```bash
mf --dry-run <command>                  # Preview mode
mf --verbose <command>                  # Detailed output
```

## Data Model

All data lives in `.mf/` at the project root:

```
.mf/
├── config.yaml           # Configuration
├── paper_db.json         # Paper metadata
├── projects_db.json      # Project overrides
├── series_db.json        # Series configuration
├── cache/
│   └── projects.json     # GitHub API cache (gitignored)
└── backups/
    ├── papers/           # Timestamped backups
    └── projects/
```

Databases use a consistent pattern:
- JSON with `_schema_version`, `_comment` metadata
- Automatic backup on every save
- CRUD operations with search/filter support

## Configuration

### GitHub Token

For higher API rate limits:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
```

### Hugo Site

`mf` finds your Hugo site by walking up from the current directory looking for `.mf/` or `hugo.toml`. You can also set:

```bash
export MF_SITE_ROOT=/path/to/hugo/site
```

## Design Philosophy

**Databases are truth.** Hugo pages are generated artifacts. Never edit generated pages directly—edit the database or source, then regenerate.

**Idempotent operations.** Running a command twice produces the same result. Safe to re-run when uncertain.

**Dry-run everything.** Every destructive operation supports `--dry-run`. Preview before committing.

**Automatic backups.** Every database write creates a timestamped backup. Rollback is always available.

**Explicit linking.** Content-to-project relationships use the `linked_project` taxonomy, not magic inference. Automation suggests; humans approve.

## Relationship to metafunctor.com

`mf` was extracted from the [metafunctor](https://github.com/queelius/metafunctor) Hugo site repository into its own standalone package. It operates on the Hugo site via path resolution (see Configuration above) but has no direct dependency on the site repo.

This decoupling means:
- `mf` can be installed and versioned independently
- The Hugo site repo stays clean (no Python tooling mixed in)
- `mf` can be reused or adapted for other Hugo sites

## Adapting for Your Site

While built for [metafunctor.com](https://metafunctor.com), the patterns are transferable. If you have a similar setup (Hugo site + external content sources), fork and adapt:

1. Modify the content type schemas in `src/mf/core/database.py`
2. Adjust the Hugo generators in `src/mf/papers/` and `src/mf/projects/`
3. Update front matter field names to match your theme
4. Keep the backup/integrity/analytics infrastructure — it's general-purpose

See `CLAUDE.md` for architecture details.

## Development

```bash
pip install -e ".[dev]"

pytest                              # Run tests
pytest -k "test_backup"             # Pattern match
pytest --cov=mf --cov-report=html   # Coverage

mypy src/mf                         # Type check
ruff check src/mf                   # Lint
```

## License

MIT

# Design: First-class `mf packages` System

**Date:** 2026-02-16
**Status:** Approved

## Summary

Add a first-class `mf packages` module for managing software packages published to registries (PyPI, CRAN, etc.). Packages get their own database, CLI commands, Hugo content generation, and per-package pages at `/packages/{name}/`.

Registry adapters follow a plugin-like pattern: built-in adapters ship with mf in `src/mf/packages/registries/`, users can override or extend them by dropping scripts into `.mf/registries/`.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Relationship to projects | Independent, optionally linked | Packages can exist without a project; most will link to one |
| Initial registries | PyPI + CRAN | Primary languages; add more later |
| Data source | Direct API calls | Self-contained, no repoindex dependency |
| Page content | Summary card | Name, version, install command, badges, description, link to project/registry |
| Adapter architecture | Protocol + importlib discovery | Lightweight, type-safe, extensible |
| Adapter location (built-in) | `src/mf/packages/registries/` | Inside the packages module, clean and discoverable |
| Adapter location (user) | `.mf/registries/` | Site-local, user scripts override built-ins |
| Adapter contract | Python Protocol class | One method: `fetch_metadata(name) -> PackageMetadata | None` |

## Module Layout

```
src/mf/packages/
    __init__.py
    commands.py            # Click CLI group
    database.py            # PackageDatabase + PackageEntry
    field_ops.py           # PACKAGES_SCHEMA + thin wrappers
    generator.py           # Hugo content generation
    registries/
        __init__.py        # RegistryAdapter Protocol + discover_registries()
        pypi.py            # PyPI JSON API adapter
        cran.py            # CRAN API adapter

.mf/
    packages_db.json       # Package database
    backups/packages/      # Backup directory
    registries/            # User-provided overrides/extensions
```

## Registry Adapter Protocol

```python
from typing import Protocol
from dataclasses import dataclass

@dataclass
class PackageMetadata:
    """Standardized metadata returned by any registry adapter."""
    name: str
    registry: str                      # "pypi", "cran", etc.
    latest_version: str
    description: str
    homepage: str | None = None
    license: str | None = None
    downloads: int | None = None       # monthly or total, registry-dependent
    versions: list[str] | None = None  # last N versions
    install_command: str | None = None # "pip install foo"
    registry_url: str | None = None    # link to package on registry site
    last_updated: str | None = None    # ISO date of last release

class RegistryAdapter(Protocol):
    """Contract for registry adapters."""
    name: str  # e.g. "pypi"

    def fetch_metadata(self, package_name: str) -> PackageMetadata | None:
        """Fetch package metadata. Returns None if not found."""
        ...
```

One dataclass, one protocol, one method. Adapters can add helpers internally.

## Discovery and Override

`registries/__init__.py` provides:

```python
def discover_registries(
    extra_dirs: list[Path] | None = None,
) -> dict[str, RegistryAdapter]:
    """Scan built-in + user dirs, import .py files, return name -> adapter map.

    Each .py file must define a module-level `adapter` instance that satisfies
    RegistryAdapter (has `name: str` and `fetch_metadata()`).

    Resolution order (last wins):
      1. Built-in: src/mf/packages/registries/*.py
      2. User: .mf/registries/*.py
    """
```

User files with the same name as a built-in override the built-in entirely. New filenames add new registries.

## Database

Follows the existing mf database pattern:

```json
{
    "_comment": "Package registry metadata managed by mf",
    "_schema_version": 1,
    "reliabilitytheory": {
        "name": "reliabilitytheory",
        "registry": "cran",
        "project": "reliabilitytheory",
        "latest_version": "0.3.0",
        "description": "Reliability Theory Tools",
        "install_command": "install.packages('reliabilitytheory')",
        "registry_url": "https://cran.r-project.org/package=reliabilitytheory",
        "downloads": 1200,
        "license": "MIT",
        "last_synced": "2026-02-16T12:00:00Z"
    }
}
```

Key: package name. Optional `project` field links to an mf project slug.

`PackageDatabase` class with standard interface: `load()`, `save()`, `get()`, `set()`, `update()`, `delete()`, `search()`, `items()`.

`PackageEntry` dataclass with property accessors (matching `PaperEntry` / `SeriesEntry` pattern).

## Field Schema

`PACKAGES_SCHEMA` in `packages/field_ops.py`:

| Field | Type | Description |
|-------|------|-------------|
| `name` | STRING | Package name on registry |
| `registry` | STRING (choices: pypi, cran) | Which registry |
| `project` | STRING | Optional linked mf project slug |
| `description` | STRING | Package description |
| `latest_version` | STRING | Latest version string |
| `install_command` | STRING | Install command for users |
| `registry_url` | STRING | URL to package on registry |
| `license` | STRING | License identifier |
| `downloads` | INT | Download count |
| `tags` | STRING_LIST | Package tags |
| `featured` | BOOL | Show in featured section |
| `stars` | INT | Quality rating (0-5) |
| `aliases` | STRING_LIST | Hugo URL aliases |

## CLI Commands

```
mf packages list                                   # List all packages
mf packages show <name>                            # Show package details
mf packages add <name> --registry pypi [--project slug]  # Add + fetch metadata
mf packages remove <name>                          # Remove a package
mf packages sync [<name>]                          # Refresh from registry (all or one)
mf packages generate [<name>]                      # Generate Hugo content (all or one)
mf packages set <name> <field> <value>             # Override a field
mf packages unset <name> <field>                   # Remove an override
```

Standard flags: `--dry-run`, `--verbose`, `--regenerate` (on set/unset).

## Hugo Content Generation

Generates `content/packages/{name}/index.md` (leaf bundle):

```yaml
---
title: "reliabilitytheory"
slug: "reliabilitytheory"
date: 2026-02-16
description: "Reliability Theory Tools"
registry: "cran"
latest_version: "0.3.0"
install_command: "install.packages('reliabilitytheory')"
registry_url: "https://cran.r-project.org/package=reliabilitytheory"
downloads: 1200
license: "MIT"
featured: false
linked_project: "/projects/reliabilitytheory/"
---
```

Hugo theme needs a `layouts/packages/` directory with templates (separate concern, tracked in SITE_CONTRACT.md).

## Integration Points

### SitePaths additions

```python
# In SitePaths dataclass
packages: Path          # content/packages
packages_db: Path       # .mf/packages_db.json
packages_backups: Path  # .mf/backups/packages
```

### CLI registration

```python
# In cli.py
from mf.packages.commands import packages
main.add_command(packages)
```

### SITE_CONTRACT.md

Add packages to the site contract: content section, front matter fields consumed by theme, taxonomy integration.

## Built-in Adapters

### pypi.py

Uses the PyPI JSON API (`https://pypi.org/pypi/{name}/json`). No authentication required. Extracts: version, description, homepage, license, download stats (from `https://pypistats.org/api/packages/{name}/recent`), install command (`pip install {name}`).

### cran.py

Uses CRAN metadata (`https://crandb.r-pkg.org/{name}` or scrapes the CRAN package page). Extracts: version, description, license, install command (`install.packages('{name}')`), CRAN URL.

## Testing

- Unit tests for each registry adapter (mock HTTP responses)
- Unit tests for database CRUD
- Unit tests for field_ops schema validation
- Unit tests for content generation
- Integration tests for CLI commands
- Test that user overrides in `.mf/registries/` take precedence

Test directory: `tests/test_packages/`

# Pubs Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple `mf pubs` from `paper_db.json` by introducing `pubs_db.json` with typed data model, lifecycle tracking, artifact management, and one-time migration.

**Architecture:** New `PubEntry` dataclass and `PubsDatabase` class in `mf/publications/database.py`. All existing `mf pubs` commands rewritten to read/write `pubs_db.json`. Hugo templates updated to read artifacts from structured `artifacts` frontmatter object. One-time migration seeds pubs_db from paper_db.

**Tech Stack:** Python 3.12, Click CLI, Rich tables, PyYAML, Hugo (Go templates)

**Spec:** `docs/superpowers/specs/2026-04-08-pubs-decoupling-design.md`

---

### Task 1: Add pubs_db path to config

**Files:**
- Modify: `src/mf/core/config.py:24-58` (SitePaths dataclass)
- Modify: `src/mf/core/config.py:194-221` (get_paths function)
- Test: `tests/test_publications/test_database.py` (new file, created in Task 2)

- [ ] **Step 1: Add pubs_db and pubs_backups to SitePaths**

In `src/mf/core/config.py`, add two fields to the `SitePaths` dataclass after `packages_backups`:

```python
    # Publications
    pubs_db: Path
    pubs_backups: Path
```

- [ ] **Step 2: Add pubs_db and pubs_backups to get_paths()**

In `src/mf/core/config.py`, add to the `SitePaths(...)` constructor call in `get_paths()`, after the `packages_backups` line:

```python
        # Publications
        pubs_db=mf_dir / "pubs_db.json",
        pubs_backups=mf_dir / "backups" / "pubs",
```

- [ ] **Step 3: Verify config loads**

Run: `cd /home/spinoza/github/repos/mf && python -c "from mf.core.config import get_paths; p = get_paths(); print(p.pubs_db)"`

Expected: `/home/spinoza/github/repos/metafunctor/.mf/pubs_db.json`

- [ ] **Step 4: Commit**

```bash
git add src/mf/core/config.py
git commit -m "feat(config): add pubs_db and pubs_backups paths to SitePaths"
```

---

### Task 2: Create PubEntry dataclass and PubsDatabase

**Files:**
- Create: `src/mf/publications/database.py`
- Create: `tests/test_publications/test_database.py`

- [ ] **Step 1: Write failing tests for PubEntry and PubsDatabase**

Create `tests/test_publications/test_database.py`:

```python
"""Tests for PubEntry and PubsDatabase."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_pub_data():
    return {
        "title": "Test Paper",
        "authors": [{"name": "Alex Towell", "email": "lex@metafunctor.com"}],
        "date": "2026-04-08",
        "status": "draft",
        "type": "conference paper",
        "abstract": "A test abstract.",
        "tags": ["testing"],
        "artifacts": {"pdf": "/latex/test/paper.pdf"},
        "timeline": [{"date": "2026-04-08", "event": "created", "note": "Test"}],
    }


class TestPubEntry:
    def test_create_from_dict(self, sample_pub_data):
        from mf.publications.database import PubEntry

        entry = PubEntry.from_dict("test-paper", sample_pub_data)
        assert entry.slug == "test-paper"
        assert entry.title == "Test Paper"
        assert entry.status == "draft"
        assert entry.type == "conference paper"
        assert entry.artifacts.get("pdf") == "/latex/test/paper.pdf"

    def test_to_dict_roundtrip(self, sample_pub_data):
        from mf.publications.database import PubEntry

        entry = PubEntry.from_dict("test-paper", sample_pub_data)
        data = entry.to_dict()
        assert data["title"] == "Test Paper"
        assert data["status"] == "draft"
        assert data["artifacts"]["pdf"] == "/latex/test/paper.pdf"

    def test_missing_required_field_raises(self):
        from mf.publications.database import PubEntry

        with pytest.raises(ValueError, match="title"):
            PubEntry.from_dict("bad", {"status": "draft", "type": "preprint"})

    def test_invalid_status_raises(self, sample_pub_data):
        from mf.publications.database import PubEntry

        sample_pub_data["status"] = "banana"
        with pytest.raises(ValueError, match="status"):
            PubEntry.from_dict("test", sample_pub_data)

    def test_invalid_type_raises(self, sample_pub_data):
        from mf.publications.database import PubEntry

        sample_pub_data["type"] = "manga"
        with pytest.raises(ValueError, match="type"):
            PubEntry.from_dict("test", sample_pub_data)


class TestPubsDatabase:
    def test_load_empty(self, tmp_path):
        from mf.publications.database import PubsDatabase

        db = PubsDatabase(tmp_path / "pubs_db.json")
        db.load()
        assert len(db) == 0

    def test_set_and_get(self, tmp_path, sample_pub_data):
        from mf.publications.database import PubEntry, PubsDatabase

        db = PubsDatabase(tmp_path / "pubs_db.json")
        db.load()
        entry = PubEntry.from_dict("test-paper", sample_pub_data)
        db.set(entry)
        assert db.get("test-paper") is not None
        assert db.get("test-paper").title == "Test Paper"

    def test_save_and_reload(self, tmp_path, sample_pub_data):
        from mf.publications.database import PubEntry, PubsDatabase

        db_path = tmp_path / "pubs_db.json"
        db = PubsDatabase(db_path)
        db.load()
        entry = PubEntry.from_dict("test-paper", sample_pub_data)
        db.set(entry)
        db.save()

        db2 = PubsDatabase(db_path)
        db2.load()
        assert len(db2) == 1
        assert db2.get("test-paper").title == "Test Paper"

    def test_remove(self, tmp_path, sample_pub_data):
        from mf.publications.database import PubEntry, PubsDatabase

        db = PubsDatabase(tmp_path / "pubs_db.json")
        db.load()
        db.set(PubEntry.from_dict("test-paper", sample_pub_data))
        assert len(db) == 1
        db.remove("test-paper")
        assert len(db) == 0

    def test_iter(self, tmp_path, sample_pub_data):
        from mf.publications.database import PubEntry, PubsDatabase

        db = PubsDatabase(tmp_path / "pubs_db.json")
        db.load()
        db.set(PubEntry.from_dict("paper-a", sample_pub_data))
        db.set(PubEntry.from_dict("paper-b", sample_pub_data))
        slugs = list(db)
        assert "paper-a" in slugs
        assert "paper-b" in slugs

    def test_validate_on_set_rejects_bad_entry(self, tmp_path):
        from mf.publications.database import PubEntry, PubsDatabase

        db = PubsDatabase(tmp_path / "pubs_db.json")
        db.load()
        with pytest.raises(ValueError):
            PubEntry.from_dict("bad", {"status": "draft", "type": "preprint"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/spinoza/github/repos/mf && python -m pytest tests/test_publications/test_database.py -v`

Expected: FAIL (ImportError, module not found)

- [ ] **Step 3: Implement PubEntry and PubsDatabase**

Create `src/mf/publications/database.py`:

```python
"""
Publication database: typed data model and JSON persistence.

Decoupled from paper_db.json. Self-contained lifecycle tracking,
artifact management, and timeline events.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

from mf.core.backup import safe_write_json
from mf.core.config import get_paths

console = Console()

VALID_STATUSES = frozenset({
    "draft", "preprint", "submitted", "under-review",
    "accepted", "published", "rejected", "revised", "withdrawn",
})

VALID_TYPES = frozenset({
    "conference paper", "journal article", "workshop paper",
    "thesis", "technical report", "white paper", "preprint",
    "book chapter",
})

SPECIAL_KEYS = frozenset({"_schema_version"})


@dataclass
class PubEntry:
    """A single publication entry."""

    slug: str
    title: str
    authors: list[dict] = field(default_factory=list)
    date: str = ""
    status: str = "draft"
    type: str = "preprint"

    abstract: str | None = None
    tags: list[str] = field(default_factory=list)
    venue: str | None = None
    venue_details: dict | None = None
    doi: str | None = None
    arxiv_id: str | None = None

    artifacts: dict[str, str | None] = field(default_factory=dict)
    links: list[dict] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    source_repo: str | None = None

    @classmethod
    def from_dict(cls, slug: str, data: dict[str, Any]) -> PubEntry:
        """Create a PubEntry from a dict, validating required fields."""
        if not data.get("title"):
            raise ValueError(f"Publication '{slug}' missing required field: title")
        status = data.get("status", "draft")
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Publication '{slug}' has invalid status '{status}'. "
                f"Valid: {sorted(VALID_STATUSES)}"
            )
        pub_type = data.get("type", "preprint")
        if pub_type not in VALID_TYPES:
            raise ValueError(
                f"Publication '{slug}' has invalid type '{pub_type}'. "
                f"Valid: {sorted(VALID_TYPES)}"
            )
        return cls(
            slug=slug,
            title=data["title"],
            authors=data.get("authors", []),
            date=data.get("date", ""),
            status=status,
            type=pub_type,
            abstract=data.get("abstract"),
            tags=data.get("tags", []),
            venue=data.get("venue"),
            venue_details=data.get("venue_details"),
            doi=data.get("doi"),
            arxiv_id=data.get("arxiv_id"),
            artifacts=data.get("artifacts", {}),
            links=data.get("links", []),
            timeline=data.get("timeline", []),
            source_repo=data.get("source_repo"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict (for JSON storage)."""
        d: dict[str, Any] = {
            "title": self.title,
            "authors": self.authors,
            "date": self.date,
            "status": self.status,
            "type": self.type,
        }
        if self.abstract:
            d["abstract"] = self.abstract
        if self.tags:
            d["tags"] = self.tags
        if self.venue:
            d["venue"] = self.venue
        if self.venue_details:
            d["venue_details"] = self.venue_details
        if self.doi:
            d["doi"] = self.doi
        if self.arxiv_id:
            d["arxiv_id"] = self.arxiv_id
        if self.artifacts:
            d["artifacts"] = self.artifacts
        if self.links:
            d["links"] = self.links
        if self.timeline:
            d["timeline"] = self.timeline
        if self.source_repo:
            d["source_repo"] = self.source_repo
        return d


class PubsDatabase:
    """Manages pubs_db.json with safe loading/saving and validation."""

    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            db_path = get_paths().pubs_db
        self.db_path = Path(db_path)
        self._data: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        if not self.db_path.exists():
            self._data = {"_schema_version": 1}
            self._loaded = True
            return
        try:
            with open(self.db_path, encoding="utf-8") as f:
                self._data = json.load(f)
            self._loaded = True
        except json.JSONDecodeError as e:
            console.print(f"[red]ERROR: {self.db_path} contains invalid JSON![/red]")
            console.print(f"JSON Error: {e}")
            sys.exit(1)

    def save(self) -> None:
        if not self._loaded:
            raise RuntimeError("Database not loaded. Call load() first.")
        if "_schema_version" not in self._data:
            self._data["_schema_version"] = 1
        sorted_data = {k: self._data[k] for k in sorted(self._data)}
        safe_write_json(self.db_path, sorted_data, create_backup_first=True)

    def get(self, slug: str) -> PubEntry | None:
        if slug in SPECIAL_KEYS or slug not in self._data:
            return None
        return PubEntry.from_dict(slug, self._data[slug])

    def set(self, entry: PubEntry) -> None:
        if entry.slug in SPECIAL_KEYS:
            raise ValueError(f"Cannot use reserved key: {entry.slug}")
        self._data[entry.slug] = entry.to_dict()

    def remove(self, slug: str) -> None:
        self._data.pop(slug, None)

    def __contains__(self, slug: str) -> bool:
        return slug in self._data and slug not in SPECIAL_KEYS

    def __iter__(self) -> Iterator[str]:
        for key in self._data:
            if key not in SPECIAL_KEYS:
                yield key

    def __len__(self) -> int:
        return sum(1 for k in self._data if k not in SPECIAL_KEYS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/spinoza/github/repos/mf && python -m pytest tests/test_publications/test_database.py -v`

Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/mf/publications/database.py tests/test_publications/test_database.py
git commit -m "feat(pubs): add PubEntry dataclass and PubsDatabase with tests"
```

---

### Task 3: Implement migration from paper_db

**Files:**
- Create: `src/mf/publications/migrate.py`
- Test: `tests/test_publications/test_migrate.py`

- [ ] **Step 1: Write failing test for migration**

Create `tests/test_publications/test_migrate.py`:

```python
"""Tests for paper_db to pubs_db migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def make_paper_db(tmp_path, entries):
    """Write a paper_db.json and return the path."""
    db_path = tmp_path / "paper_db.json"
    data = {"_schema_version": "2.0", "_comment": "test", "_example": {}}
    data.update(entries)
    db_path.write_text(json.dumps(data))
    return db_path


class TestMigration:
    def test_published_paper_included(self, tmp_path):
        from mf.publications.migrate import migrate_paper_db

        paper_db = make_paper_db(tmp_path, {
            "my-paper": {
                "title": "Published Paper",
                "authors": [{"name": "Alex"}],
                "date": "2025-01-01",
                "status": "published",
                "category": "conference paper",
                "venue": "AAAI 2025",
                "pdf_path": "/latex/my-paper/paper.pdf",
                "html_path": "/latex/my-paper/",
                "github_url": "https://github.com/queelius/repo",
            }
        })
        pubs_db_path = tmp_path / "pubs_db.json"
        results = migrate_paper_db(paper_db, pubs_db_path)

        assert len(results["included"]) == 1
        assert "my-paper" in results["included"]

        data = json.loads(pubs_db_path.read_text())
        entry = data["my-paper"]
        assert entry["status"] == "published"
        assert entry["type"] == "conference paper"
        assert entry["venue"] == "AAAI 2025"
        assert entry["artifacts"]["pdf"] == "/latex/my-paper/paper.pdf"
        assert entry["artifacts"]["html"] == "/latex/my-paper/"
        assert entry["artifacts"]["code"] == "https://github.com/queelius/repo"

    def test_novel_skipped(self, tmp_path):
        from mf.publications.migrate import migrate_paper_db

        paper_db = make_paper_db(tmp_path, {
            "my-novel": {
                "title": "A Novel",
                "category": "novel",
                "status": "draft",
            }
        })
        pubs_db_path = tmp_path / "pubs_db.json"
        results = migrate_paper_db(paper_db, pubs_db_path)

        assert len(results["included"]) == 0
        assert "my-novel" in results["skipped"]

    def test_slug_mapping_applied(self, tmp_path):
        from mf.publications.migrate import migrate_paper_db

        paper_db = make_paper_db(tmp_path, {
            "cognitive-mri-ai-conversations": {
                "title": "Cognitive MRI",
                "authors": [{"name": "Alex"}],
                "date": "2025-12-09",
                "status": "published",
                "category": "conference paper",
                "venue": "Complex Networks 2025",
            }
        })
        pubs_db_path = tmp_path / "pubs_db.json"
        migrate_paper_db(paper_db, pubs_db_path)

        data = json.loads(pubs_db_path.read_text())
        assert "cognitive-mri" in data
        assert "cognitive-mri-ai-conversations" not in data

    def test_timeline_seeded(self, tmp_path):
        from mf.publications.migrate import migrate_paper_db

        paper_db = make_paper_db(tmp_path, {
            "my-paper": {
                "title": "A Paper",
                "status": "published",
                "category": "conference paper",
                "date": "2025-06-01",
            }
        })
        pubs_db_path = tmp_path / "pubs_db.json"
        migrate_paper_db(paper_db, pubs_db_path)

        data = json.loads(pubs_db_path.read_text())
        tl = data["my-paper"]["timeline"]
        assert len(tl) == 1
        assert tl[0]["event"] == "migrated"

    def test_authors_normalized(self, tmp_path):
        from mf.publications.migrate import migrate_paper_db

        paper_db = make_paper_db(tmp_path, {
            "my-paper": {
                "title": "A Paper",
                "authors": ["Alex Towell", {"name": "John Matta"}],
                "status": "published",
                "category": "journal article",
            }
        })
        pubs_db_path = tmp_path / "pubs_db.json"
        migrate_paper_db(paper_db, pubs_db_path)

        data = json.loads(pubs_db_path.read_text())
        authors = data["my-paper"]["authors"]
        assert authors[0] == {"name": "Alex Towell"}
        assert authors[1] == {"name": "John Matta"}

    def test_slides_extracted_from_links(self, tmp_path):
        from mf.publications.migrate import migrate_paper_db

        paper_db = make_paper_db(tmp_path, {
            "my-paper": {
                "title": "A Paper",
                "status": "published",
                "category": "conference paper",
                "links": [
                    {"name": "Slides", "url": "/latex/my-paper/slides.pdf"},
                    {"name": "GitHub", "url": "https://github.com/foo"},
                ],
            }
        })
        pubs_db_path = tmp_path / "pubs_db.json"
        migrate_paper_db(paper_db, pubs_db_path)

        data = json.loads(pubs_db_path.read_text())
        assert data["my-paper"]["artifacts"].get("slides") == "/latex/my-paper/slides.pdf"
        # GitHub link should NOT be in artifacts (already handled by github_url)
        links = data["my-paper"].get("links", [])
        assert any(l["name"] == "GitHub" for l in links)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/spinoza/github/repos/mf && python -m pytest tests/test_publications/test_migrate.py -v`

Expected: FAIL (ImportError)

- [ ] **Step 3: Implement migrate_paper_db**

Create `src/mf/publications/migrate.py`:

```python
"""
One-time migration from paper_db.json to pubs_db.json.

Reads paper_db, applies inclusion criteria and field mappings,
writes a new pubs_db.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()

# Slug mappings from the old generate.py
SLUG_MAPPINGS = {
    "reliability-estimation-in-series-systems": "math-proj",
    "2016-ieee-int-8-ccts": "mab",
    "2015-cs-thesis": "cs-thesis",
    "cognitive-mri-ai-conversations": "cognitive-mri",
    "ransomware-icci2025": "ransomware",
}

# Categories that are not academic publications
SKIP_CATEGORIES = {"novel", "essay", "novella", "short story"}

# paper_db special keys
PAPER_SPECIAL_KEYS = {"_comment", "_example", "_schema_version"}


def _should_include(data: dict[str, Any]) -> tuple[bool, str, str]:
    """Decide if a paper_db entry should be included in pubs_db.

    Returns:
        (include, status_to_assign, reason)
    """
    category = data.get("category", "").lower()
    if category in SKIP_CATEGORIES:
        return False, "", f"category={category}"

    status = data.get("status", "")
    venue = data.get("venue", "")
    doi = data.get("doi", "")
    arxiv_id = data.get("arxiv_id", "")

    # Rule 1: published, has venue, or has non-arxiv DOI
    if status == "published" or venue:
        return True, "published", "published/has venue"
    if doi and "arxiv" not in doi.lower():
        return True, "published", "has DOI"

    # Rule 2: has arxiv_id
    if arxiv_id:
        return True, "preprint", "has arxiv_id"

    # Rule 3: draft with artifacts
    if data.get("pdf_path") or data.get("html_path"):
        return True, "draft", "has artifacts"

    return False, "", "no venue/doi/arxiv/artifacts"


def _normalize_authors(authors: list) -> list[dict]:
    """Normalize authors to [{name: ..., email: ...}] format."""
    result = []
    for author in authors:
        if isinstance(author, dict):
            result.append(author)
        elif isinstance(author, str):
            result.append({"name": author})
    return result


def _map_type(category: str) -> str:
    """Map paper_db category to pubs_db type."""
    mapping = {
        "conference paper": "conference paper",
        "conference": "conference paper",
        "journal article": "journal article",
        "research paper": "conference paper",
        "technical report": "technical report",
        "technical paper": "technical report",
        "white paper": "white paper",
        "master's thesis": "thesis",
        "thesis": "thesis",
        "book chapter": "book chapter",
    }
    return mapping.get(category.lower(), "preprint")


def _extract_slides_from_links(links: list[dict]) -> tuple[str | None, list[dict]]:
    """Extract slides URL from links, return (slides_url, remaining_links)."""
    slides = None
    remaining = []
    for link in links:
        name = link.get("name", "").lower()
        if name in ("slides", "presentation", "talk"):
            slides = link.get("url")
        else:
            remaining.append(link)
    return slides, remaining


def _derive_source_repo(source_path: str | None) -> str | None:
    """Derive source_repo from absolute source_path."""
    if not source_path:
        return None
    home_github = str(Path.home() / "github")
    if source_path.startswith(home_github):
        rel = source_path[len(home_github):].lstrip("/")
        # Take everything up to the paper file
        parts = Path(rel).parts
        # Usually: category/repo/... or just repo/...
        # Return the repo-level path (first 2 parts if nested, or first 1)
        if len(parts) >= 2:
            return str(Path(parts[0]) / parts[1])
        if parts:
            return parts[0]
    return None


def migrate_paper_db(
    paper_db_path: Path,
    pubs_db_path: Path,
) -> dict[str, list[str]]:
    """Migrate entries from paper_db to pubs_db.

    Args:
        paper_db_path: Path to paper_db.json
        pubs_db_path: Path to write pubs_db.json

    Returns:
        Dict with "included" and "skipped" slug lists.
    """
    with open(paper_db_path, encoding="utf-8") as f:
        paper_data = json.load(f)

    pubs_data: dict[str, Any] = {"_schema_version": 1}
    included = []
    skipped = []

    table = Table(title="Migration Summary")
    table.add_column("Slug", style="cyan")
    table.add_column("Title", max_width=40)
    table.add_column("Status", style="green")
    table.add_column("Result", style="bold")
    table.add_column("Reason", style="dim")

    for slug, data in sorted(paper_data.items()):
        if slug in PAPER_SPECIAL_KEYS:
            continue

        include, pub_status, reason = _should_include(data)
        title = data.get("title", slug)

        if not include:
            skipped.append(slug)
            table.add_row(slug, title[:40], "", "[red]SKIP[/red]", reason)
            continue

        # Apply slug mapping
        pub_slug = SLUG_MAPPINGS.get(slug, slug)

        # Build artifacts
        artifacts: dict[str, str | None] = {}
        if data.get("pdf_path"):
            artifacts["pdf"] = data["pdf_path"]
        if data.get("html_path"):
            artifacts["html"] = data["html_path"]
        if data.get("cite_path"):
            artifacts["bibtex"] = data["cite_path"]
        if data.get("github_url"):
            artifacts["code"] = data["github_url"]

        # Extract slides from links
        slides_url = None
        remaining_links = []
        if data.get("links"):
            slides_url, remaining_links = _extract_slides_from_links(data["links"])
        if slides_url:
            artifacts["slides"] = slides_url

        # Build entry
        entry: dict[str, Any] = {
            "title": title,
            "authors": _normalize_authors(data.get("authors", [])),
            "date": data.get("date", ""),
            "status": pub_status,
            "type": _map_type(data.get("category", "")),
        }

        if data.get("abstract"):
            entry["abstract"] = data["abstract"]
        if data.get("tags"):
            entry["tags"] = data["tags"]
        if data.get("venue"):
            entry["venue"] = data["venue"]
        if data.get("doi"):
            entry["doi"] = data["doi"]
        if data.get("arxiv_id"):
            entry["arxiv_id"] = data["arxiv_id"]
        if artifacts:
            entry["artifacts"] = artifacts
        if remaining_links:
            entry["links"] = remaining_links

        # Source repo
        source_repo = _derive_source_repo(data.get("source_path") or data.get("source_dir"))
        if source_repo:
            entry["source_repo"] = source_repo

        # Timeline seed
        entry["timeline"] = [{
            "date": data.get("date", ""),
            "event": "migrated",
            "note": "Migrated from paper_db",
        }]

        pubs_data[pub_slug] = entry
        included.append(pub_slug)
        table.add_row(
            pub_slug if pub_slug == slug else f"{pub_slug} ({slug})",
            title[:40],
            pub_status,
            "[green]INCLUDE[/green]",
            reason,
        )

    # Write pubs_db.json
    pubs_db_path.parent.mkdir(parents=True, exist_ok=True)
    sorted_data = {k: pubs_data[k] for k in sorted(pubs_data)}
    pubs_db_path.write_text(json.dumps(sorted_data, indent=2, ensure_ascii=False))

    console.print(table)
    console.print(f"\n[green]Included: {len(included)}[/green], "
                  f"[red]Skipped: {len(skipped)}[/red]")
    console.print(f"Written to: {pubs_db_path}")

    return {"included": included, "skipped": skipped}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/spinoza/github/repos/mf && python -m pytest tests/test_publications/test_migrate.py -v`

Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/mf/publications/migrate.py tests/test_publications/test_migrate.py
git commit -m "feat(pubs): add paper_db to pubs_db migration with tests"
```

---

### Task 4: Rewrite CLI commands

**Files:**
- Modify: `src/mf/publications/commands.py` (full rewrite)

- [ ] **Step 1: Rewrite commands.py to use PubsDatabase**

Replace the entire contents of `src/mf/publications/commands.py` with:

```python
"""CLI commands for publications management.

Publications are tracked in pubs_db.json, decoupled from paper_db.json.
"""

from __future__ import annotations

from datetime import date

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def _load_db():
    from mf.publications.database import PubsDatabase
    db = PubsDatabase()
    db.load()
    return db


@click.group(name="pubs")
def pubs() -> None:
    """Manage publications (pubs_db.json)."""
    pass


@pubs.command(name="list")
@click.option("-q", "--query", help="Search in title/abstract")
@click.option("-s", "--status", help="Filter by status")
@click.option("-t", "--tag", multiple=True, help="Filter by tag(s)")
@click.option("--type", "pub_type", help="Filter by type")
@click.option("--venue", help="Filter by venue")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_pubs(query, status, tag, pub_type, venue, as_json):
    """List publications."""
    import json as json_module

    db = _load_db()
    results = []
    for slug in db:
        entry = db.get(slug)
        if not entry:
            continue
        if status and entry.status != status:
            continue
        if pub_type and entry.type != pub_type:
            continue
        if venue and venue.lower() not in (entry.venue or "").lower():
            continue
        if tag and not any(t in entry.tags for t in tag):
            continue
        if query:
            q = query.lower()
            if q not in entry.title.lower() and q not in (entry.abstract or "").lower():
                continue
        results.append(entry)

    if as_json:
        output = [{"slug": e.slug, "title": e.title, "status": e.status,
                    "type": e.type, "date": e.date, "venue": e.venue}
                   for e in results]
        console.print(json_module.dumps(output, indent=2))
        return

    if not results:
        console.print("[yellow]No publications found[/yellow]")
        return

    table = Table(title=f"Publications ({len(results)})")
    table.add_column("Slug", style="cyan")
    table.add_column("Title", max_width=40)
    table.add_column("Status", style="green")
    table.add_column("Type", style="blue")
    table.add_column("Venue", style="dim", max_width=20)

    for e in sorted(results, key=lambda x: x.date or "", reverse=True):
        title = e.title[:40] + "..." if len(e.title) > 40 else e.title
        v = (e.venue or "")[:20]
        table.add_row(e.slug, title, e.status, e.type, v)

    console.print(table)


@pubs.command()
@click.argument("slug")
def show(slug):
    """Show details for a publication."""
    import json as json_module
    from rich.syntax import Syntax

    db = _load_db()
    entry = db.get(slug)
    if not entry:
        console.print(f"[red]Not found: {slug}[/red]")
        return

    data = entry.to_dict()
    data["slug"] = entry.slug
    syntax = Syntax(json_module.dumps(data, indent=2), "json",
                    theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Publication: {slug}"))


@pubs.command()
@click.argument("slug")
@click.option("--title", required=True, help="Publication title")
@click.option("--type", "pub_type", required=True, help="Publication type")
@click.option("--status", default="draft", help="Status (default: draft)")
@click.option("--venue", help="Venue name")
@click.option("--doi", help="DOI")
@click.option("--arxiv", help="arXiv ID")
@click.option("--pdf", help="PDF path")
@click.option("--html", help="HTML path")
@click.option("--code", help="Code URL")
@click.option("--source-repo", help="Source repo path (relative to ~/github/)")
@click.pass_obj
def add(ctx, slug, title, pub_type, status, venue, doi, arxiv,
        pdf, html, code, source_repo):
    """Add a new publication."""
    from mf.publications.database import PubEntry

    db = _load_db()
    if slug in db:
        console.print(f"[red]Already exists: {slug}[/red]")
        return

    artifacts = {}
    if pdf:
        artifacts["pdf"] = pdf
    if html:
        artifacts["html"] = html
    if code:
        artifacts["code"] = code

    entry = PubEntry.from_dict(slug, {
        "title": title,
        "status": status,
        "type": pub_type,
        "date": str(date.today()),
        "venue": venue,
        "doi": doi,
        "arxiv_id": arxiv,
        "artifacts": artifacts,
        "source_repo": source_repo,
        "timeline": [{"date": str(date.today()), "event": "created",
                       "note": "Added via mf pubs add"}],
    })

    dry_run = ctx.dry_run if ctx else False
    if dry_run:
        console.print(f"[yellow]DRY RUN: would add {slug}[/yellow]")
        return

    db.set(entry)
    db.save()
    console.print(f"[green]Added: {slug}[/green]")


@pubs.command()
@click.argument("slug")
@click.option("--title", help="Update title")
@click.option("--status", help="Update status")
@click.option("--type", "pub_type", help="Update type")
@click.option("--venue", help="Update venue")
@click.option("--doi", help="Update DOI")
@click.option("--arxiv", help="Update arXiv ID")
@click.option("--pdf", help="Update PDF artifact path")
@click.option("--html", help="Update HTML artifact path")
@click.option("--slides", help="Update slides artifact path")
@click.option("--poster", help="Update poster artifact path")
@click.option("--video", help="Update video artifact URL")
@click.option("--photos", help="Update photos path")
@click.option("--code", help="Update code artifact URL")
@click.option("--bibtex", help="Update bibtex artifact path")
@click.pass_obj
def update(ctx, slug, title, status, pub_type, venue, doi, arxiv,
           pdf, html, slides, poster, video, photos, code, bibtex):
    """Update fields of an existing publication."""
    db = _load_db()
    entry = db.get(slug)
    if not entry:
        console.print(f"[red]Not found: {slug}[/red]")
        return

    if title:
        entry.title = title
    if status:
        from mf.publications.database import VALID_STATUSES
        if status not in VALID_STATUSES:
            console.print(f"[red]Invalid status: {status}[/red]")
            return
        entry.status = status
    if pub_type:
        from mf.publications.database import VALID_TYPES
        if pub_type not in VALID_TYPES:
            console.print(f"[red]Invalid type: {pub_type}[/red]")
            return
        entry.type = pub_type
    if venue:
        entry.venue = venue
    if doi:
        entry.doi = doi
    if arxiv:
        entry.arxiv_id = arxiv

    artifact_updates = {
        "pdf": pdf, "html": html, "slides": slides, "poster": poster,
        "video": video, "photos": photos, "code": code, "bibtex": bibtex,
    }
    for key, val in artifact_updates.items():
        if val is not None:
            entry.artifacts[key] = val

    dry_run = ctx.dry_run if ctx else False
    if dry_run:
        console.print(f"[yellow]DRY RUN: would update {slug}[/yellow]")
        return

    db.set(entry)
    db.save()
    console.print(f"[green]Updated: {slug}[/green]")


@pubs.command()
@click.argument("slug")
@click.option("--event", required=True, help="Event name")
@click.option("--note", default="", help="Event note")
@click.option("--date", "event_date", default=None, help="Event date (default: today)")
@click.pass_obj
def log(ctx, slug, event, note, event_date):
    """Append a timeline event to a publication."""
    db = _load_db()
    entry = db.get(slug)
    if not entry:
        console.print(f"[red]Not found: {slug}[/red]")
        return

    if event_date is None:
        event_date = str(date.today())

    entry.timeline.append({
        "date": event_date,
        "event": event,
        "note": note,
    })

    dry_run = ctx.dry_run if ctx else False
    if dry_run:
        console.print(f"[yellow]DRY RUN: would log {event} on {slug}[/yellow]")
        return

    db.set(entry)
    db.save()
    console.print(f"[green]Logged: {event} on {slug}[/green]")


@pubs.command()
@click.option("--slug", help="Generate only this slug")
@click.option("--force", is_flag=True, help="Overwrite existing files")
@click.pass_obj
def generate(ctx, slug, force):
    """Generate Hugo content/publications/ from pubs_db."""
    from mf.publications.generate import generate_publications

    dry_run = ctx.dry_run if ctx else False
    generate_publications(slug=slug, dry_run=dry_run, force=force)


@pubs.command()
@click.pass_obj
def migrate(ctx):
    """One-time migration from paper_db to pubs_db."""
    from mf.core.config import get_paths
    from mf.publications.migrate import migrate_paper_db

    paths = get_paths()
    dry_run = ctx.dry_run if ctx else False

    if paths.pubs_db.exists() and not dry_run:
        console.print(f"[yellow]pubs_db.json already exists at {paths.pubs_db}[/yellow]")
        console.print("Use --dry-run to preview, or delete the file to re-migrate.")
        return

    if dry_run:
        console.print("[yellow]DRY RUN: previewing migration[/yellow]")
        import tempfile
        from pathlib import Path
        pubs_path = Path(tempfile.mktemp(suffix=".json"))
    else:
        pubs_path = paths.pubs_db

    migrate_paper_db(paths.paper_db, pubs_path)

    if dry_run:
        pubs_path.unlink(missing_ok=True)


@pubs.command()
def stats():
    """Show publication statistics."""
    db = _load_db()

    status_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    venue_counts: dict[str, int] = {}

    for slug in db:
        entry = db.get(slug)
        if not entry:
            continue
        status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
        type_counts[entry.type] = type_counts.get(entry.type, 0) + 1
        if entry.venue:
            venue_counts[entry.venue] = venue_counts.get(entry.venue, 0) + 1

    content = f"[cyan]Total publications:[/cyan] {len(db)}"
    if status_counts:
        content += "\n\n[bold]By status:[/bold]"
        for s, c in sorted(status_counts.items(), key=lambda x: -x[1]):
            content += f"\n  {s}: {c}"
    if type_counts:
        content += "\n\n[bold]By type:[/bold]"
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
            content += f"\n  {t}: {c}"
    if venue_counts:
        content += "\n\n[bold]By venue:[/bold]"
        for v, c in sorted(venue_counts.items(), key=lambda x: -x[1]):
            content += f"\n  {v}: {c}"

    console.print(Panel(content, title="Publication Statistics"))
```

- [ ] **Step 2: Run existing tests to check nothing is broken**

Run: `cd /home/spinoza/github/repos/mf && python -m pytest tests/test_publications/ -v`

Expected: Database and migration tests PASS. Old generate/sync tests may fail (expected, they still reference paper_db). We'll fix generate next.

- [ ] **Step 3: Commit**

```bash
git add src/mf/publications/commands.py
git commit -m "feat(pubs): rewrite CLI commands to use pubs_db"
```

---

### Task 5: Rewrite generate.py for pubs_db

**Files:**
- Modify: `src/mf/publications/generate.py` (full rewrite)

- [ ] **Step 1: Rewrite generate.py to read from PubsDatabase and emit artifacts frontmatter**

Replace the entire contents of `src/mf/publications/generate.py` with:

```python
"""
Generate Hugo publication content from pubs_db.json.

Creates content/publications/{slug}/index.md with artifacts frontmatter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from mf.core.config import get_paths
from mf.publications.database import PubsDatabase, PubEntry

console = Console()


def pub_to_frontmatter(entry: PubEntry) -> dict[str, Any]:
    """Convert a PubEntry to Hugo frontmatter dict."""
    fm: dict[str, Any] = {"title": entry.title}

    if entry.abstract:
        fm["abstract"] = entry.abstract

    if entry.authors:
        fm["authors"] = entry.authors

    if entry.date:
        fm["date"] = f"{entry.date}T00:00:00Z"

    # Publication metadata block
    pub_meta: dict[str, Any] = {
        "type": entry.type,
        "status": entry.status,
    }
    if entry.venue:
        pub_meta["venue"] = entry.venue
    if entry.doi:
        pub_meta["doi"] = entry.doi
    if entry.arxiv_id:
        pub_meta["arxiv"] = entry.arxiv_id
    if entry.date:
        try:
            pub_meta["year"] = int(entry.date[:4])
        except (ValueError, IndexError):
            pass
    fm["publication"] = pub_meta

    if entry.tags:
        fm["tags"] = entry.tags

    # Artifacts (non-null only)
    artifacts = {k: v for k, v in entry.artifacts.items() if v}
    if artifacts:
        fm["artifacts"] = artifacts

    # Links (excluding artifact-handled ones)
    if entry.links:
        fm["links"] = entry.links

    return fm


def generate_publication_content(fm: dict[str, Any]) -> str:
    """Render frontmatter dict to Hugo markdown."""
    yaml_content = yaml.dump(
        fm, default_flow_style=False, allow_unicode=True,
        sort_keys=False, width=1000,
    )
    return f"---\n{yaml_content}---\n"


def generate_publications(
    slug: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Generate Hugo publication pages from pubs_db."""
    paths = get_paths()
    db = PubsDatabase()
    db.load()

    slugs = [slug] if slug else list(db)
    generated = 0

    for pub_slug in slugs:
        entry = db.get(pub_slug)
        if not entry:
            if slug:
                console.print(f"[red]Not found: {pub_slug}[/red]")
            continue

        out_dir = paths.publications / pub_slug
        out_file = out_dir / "index.md"

        if out_file.exists() and not force:
            # Merge: update artifacts/publication without overwriting manual edits
            existing = out_file.read_text()
            fm = pub_to_frontmatter(entry)
            content = generate_publication_content(fm)

            if dry_run:
                console.print(f"[yellow]DRY RUN: would update {out_file}[/yellow]")
            else:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file.write_text(content)
                console.print(f"[green]Updated: {out_file}[/green]")
            generated += 1
        else:
            fm = pub_to_frontmatter(entry)
            content = generate_publication_content(fm)

            if dry_run:
                console.print(f"[yellow]DRY RUN: would create {out_file}[/yellow]")
            else:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file.write_text(content)
                console.print(f"[green]Created: {out_file}[/green]")
            generated += 1

    console.print(f"\n[bold]Generated {generated} publication(s)[/bold]")
```

- [ ] **Step 2: Run a quick smoke test**

Run: `cd /home/spinoza/github/repos/mf && python -c "
from mf.publications.database import PubEntry, PubsDatabase
from mf.publications.generate import pub_to_frontmatter, generate_publication_content
e = PubEntry.from_dict('test', {'title': 'Test', 'status': 'draft', 'type': 'preprint', 'artifacts': {'pdf': '/test.pdf'}})
fm = pub_to_frontmatter(e)
print(generate_publication_content(fm))
"`

Expected: YAML frontmatter with `artifacts:` block containing `pdf: /test.pdf`

- [ ] **Step 3: Commit**

```bash
git add src/mf/publications/generate.py
git commit -m "feat(pubs): rewrite generate.py to read pubs_db and emit artifacts frontmatter"
```

---

### Task 6: Run migration on real data

**Files:**
- Creates: metafunctor `.mf/pubs_db.json` (via running the migrate command)

- [ ] **Step 1: Run migration in dry-run mode**

Run: `cd /home/spinoza/github/repos/metafunctor && mf pubs migrate --dry-run`

Expected: Summary table showing included/skipped papers. Verify the 5 known publications (cognitive-mri, cs-thesis, mab, math-proj, ransomware) are included. No file written.

- [ ] **Step 2: Run migration for real**

Run: `cd /home/spinoza/github/repos/metafunctor && mf pubs migrate`

Expected: `pubs_db.json` written to `.mf/pubs_db.json`. Verify with `mf pubs list` and `mf pubs stats`.

- [ ] **Step 3: Verify a specific entry**

Run: `mf pubs show cognitive-mri`

Expected: JSON with title, authors, status=published, venue=Complex Networks 2025, artifacts.pdf, artifacts.html, artifacts.slides, timeline with migrated event.

- [ ] **Step 4: Generate Hugo content from pubs_db**

Run: `mf pubs generate --force`

Expected: `content/publications/` files regenerated. Verify with `cat content/publications/cognitive-mri/index.md | head -20` that frontmatter has `artifacts:` block.

- [ ] **Step 5: Commit pubs_db.json**

```bash
cd /home/spinoza/github/repos/metafunctor
git add .mf/pubs_db.json
git commit -m "feat: add pubs_db.json (migrated from paper_db)"
```

---

### Task 7: Update Hugo templates

**Files:**
- Modify: `layouts/publications/single.html` (in metafunctor repo)
- Modify: `layouts/publications/list.html` (in metafunctor repo)

- [ ] **Step 1: Update single.html to read from artifacts**

In `/home/spinoza/github/repos/metafunctor/layouts/publications/single.html`, replace the links section (the `<section>` with HTML/PDF/links buttons, roughly lines 36-56) with:

```html
      <!-- Artifact Links -->
      <section style="margin-bottom: 1.5rem;">
        <div style="display: flex; gap: 1.5rem; flex-wrap: wrap;">
          {{ with .Params.artifacts }}
            {{ with .html }}
            <a href="{{ if hasPrefix . "http" }}{{ . }}{{ else }}{{ . | absURL }}{{ end }}" target="_blank" style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #28a745; color: white; border-radius: 5px; text-decoration: none; font-size: 1rem;">
              Read Online
            </a>
            {{ end }}
            {{ with .pdf }}
            <a href="{{ if hasPrefix . "http" }}{{ . }}{{ else }}{{ . | absURL }}{{ end }}" target="_blank" style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #007acc; color: white; border-radius: 5px; text-decoration: none; font-size: 1rem;">
              Download PDF
            </a>
            {{ end }}
            {{ with .slides }}
            <a href="{{ if hasPrefix . "http" }}{{ . }}{{ else }}{{ . | absURL }}{{ end }}" target="_blank" style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #6f42c1; color: white; border-radius: 5px; text-decoration: none; font-size: 1rem;">
              Slides
            </a>
            {{ end }}
            {{ with .poster }}
            <a href="{{ if hasPrefix . "http" }}{{ . }}{{ else }}{{ . | absURL }}{{ end }}" target="_blank" style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #20c997; color: white; border-radius: 5px; text-decoration: none; font-size: 1rem;">
              Poster
            </a>
            {{ end }}
            {{ with .video }}
            <a href="{{ . }}" target="_blank" style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #dc3545; color: white; border-radius: 5px; text-decoration: none; font-size: 1rem;">
              Watch Talk
            </a>
            {{ end }}
            {{ with .photos }}
            <a href="{{ if hasPrefix . "http" }}{{ . }}{{ else }}{{ . | absURL }}{{ end }}" target="_blank" style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #fd7e14; color: white; border-radius: 5px; text-decoration: none; font-size: 1rem;">
              Photos
            </a>
            {{ end }}
          {{ end }}
          {{ if .Params.links }}
            {{ range .Params.links }}
            <a href="{{ if hasPrefix .url "http" }}{{ .url }}{{ else }}{{ .url | absURL }}{{ end }}" target="_blank" style="display: inline-block; padding: 0.75rem 1.5rem; background-color: #6c757d; color: white; border-radius: 5px; text-decoration: none; font-size: 1rem;">
              {{ .name }}
            </a>
            {{ end }}
          {{ end }}
        </div>
      </section>
```

- [ ] **Step 2: Update the BibTeX section to use artifacts.bibtex**

In the citation script section, replace `{{ if .Params.cite }}` with `{{ if .Params.artifacts.bibtex }}` and replace `{{ $citePath }}` resolution to use `.Params.artifacts.bibtex`:

```html
            {{ if .Params.artifacts.bibtex }}
            {{ $citePath := "" }}
            {{ if hasPrefix .Params.artifacts.bibtex "/" }}
              {{ $citePath = printf "static%s" .Params.artifacts.bibtex }}
            {{ else }}
              {{ $citePath = printf "%s%s" .File.Dir .Params.artifacts.bibtex }}
            {{ end }}
            const bibtex = {{ readFile $citePath }};
```

- [ ] **Step 3: Add status badge to header**

After the `<p>Published on...` line, add:

```html
        {{ with .Params.publication.status }}
        {{ $color := "#6c757d" }}
        {{ if eq . "published" }}{{ $color = "#28a745" }}{{ end }}
        {{ if eq . "accepted" }}{{ $color = "#28a745" }}{{ end }}
        {{ if eq . "preprint" }}{{ $color = "#ffc107" }}{{ end }}
        {{ if eq . "submitted" }}{{ $color = "#007acc" }}{{ end }}
        {{ if eq . "under-review" }}{{ $color = "#007acc" }}{{ end }}
        {{ if eq . "rejected" }}{{ $color = "#dc3545" }}{{ end }}
        {{ if eq . "revised" }}{{ $color = "#fd7e14" }}{{ end }}
        <span style="display: inline-block; padding: 0.25rem 0.75rem; background-color: {{ $color }}; color: white; border-radius: 12px; font-size: 0.85rem; font-weight: 600; margin-left: 0.5rem;">{{ . | title }}</span>
        {{ end }}
```

- [ ] **Step 4: Verify Hugo builds**

Run: `cd /home/spinoza/github/repos/metafunctor && hugo --gc 2>&1 | tail -5`

Expected: Clean build with no template errors.

- [ ] **Step 5: Commit templates**

```bash
cd /home/spinoza/github/repos/metafunctor
git add layouts/publications/single.html layouts/publications/list.html
git commit -m "feat(publications): update templates for artifacts object and status badges"
```

---

### Task 8: Run full test suite and verify

**Files:** No new files.

- [ ] **Step 1: Run all mf tests**

Run: `cd /home/spinoza/github/repos/mf && python -m pytest tests/ -v --tb=short 2>&1 | tail -20`

Expected: All new tests pass. Old generate/sync tests may need updating if they import from the old generate module. Fix any import errors.

- [ ] **Step 2: Update old tests that reference paper_db**

If `tests/test_publications/test_generate.py` or `test_sync.py` fail due to import changes, update them to use the new PubsDatabase API or delete them if they're fully superseded.

- [ ] **Step 3: End-to-end verification**

Run these commands and verify output:

```bash
cd /home/spinoza/github/repos/metafunctor
mf pubs list
mf pubs stats
mf pubs show cognitive-mri
mf pubs generate --force
hugo --gc 2>&1 | tail -5
```

- [ ] **Step 4: Final commit**

```bash
cd /home/spinoza/github/repos/mf
git add -A
git commit -m "chore(pubs): fix remaining tests after pubs_db migration"
```

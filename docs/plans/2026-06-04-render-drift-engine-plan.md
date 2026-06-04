# Render-Drift Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every projection module (papers, projects, packages, publications) a uniform, read-only answer to "what would `generate` change right now?", driven by one shared engine in `core/drift.py`.

**Architecture:** Lift the generic frontmatter primitives into `core/frontmatter.py`. Add `core/drift.py` with a `Renderer` protocol (the per-module binding seam, mirroring `core/field_ops.py`), a `RenderFinding` type, and `check_render_drift` that compares each page's on-disk content against a freshly rendered page using semantic frontmatter+body equality. Split each generator into a pure `render_*_page` and the existing write path. Surface the engine as an enriched `generate --dry-run` and a new read-only `mf <module> diff`.

**Tech Stack:** Python 3.10+, Click, Rich, python-frontmatter, pytest. Lazy imports inside Click command bodies (house rule). No em-dashes in any file (soul-voice hook scans whole files).

**Spec:** `docs/plans/2026-06-04-render-drift-engine.md`.

**Plan-time refinement of the spec:** The spec proposed a uniform "pin synthesized dates in generate" mechanism for determinism. Reading the code showed three of four modules already carry a stable date (packages `add` sets `date_added`; projects date comes from the cache's `created_at`; papers' `render_paper_frontmatter` has a static `"2024-01-01"` default). So determinism is achieved primarily by removing the wall-clock fallbacks. The one module that needs real pinning is papers, where discarding the mtime-derived date would regress sensible dates; there the write path pins the mtime date into `paper_db` once. This is more minimal than the spec and is called out in Task 5.

**Transitional note (call out to the user after Task 6):** After these changes, the first `mf <module> generate` run will rewrite pages whose previous date came from a wall clock, reconciling them to the deterministic render. This is a one-time reconciliation; `diff` is clean afterward.

---

## File Structure

New files:
- `src/mf/core/frontmatter.py` : generic `parse_post`, `parse_text`, `compute_body_hash`, `frontmatter_equal`.
- `src/mf/core/drift.py` : `Renderer` protocol, `RenderFinding`, `check_render_drift`, report/diff/preview helpers, `run_diff_command`.
- `tests/test_core/test_frontmatter.py`, `tests/test_core/test_drift.py`.

Modified files:
- `src/mf/series/frontmatter.py` : import primitives from core, keep the ownership-tier layer, re-export primitives for back-compat.
- `src/mf/publications/generate.py` : add `PublicationsRenderer`.
- `src/mf/publications/commands.py` : add `diff` command; route `generate --dry-run` through the preview.
- `src/mf/packages/generator.py` : extract `render_package_page`; add `PackagesRenderer`.
- `src/mf/packages/commands.py` : add `diff`; route `generate --dry-run`.
- `src/mf/papers/generator.py` : extract `render_paper_page` (deterministic); pin date in write path; add `PapersRenderer`.
- `src/mf/papers/commands.py` : add `diff`; route `generate --dry-run`.
- `src/mf/projects/generator.py` : extract `render_project_page` (deterministic); add `ProjectsRenderer`.
- `src/mf/projects/commands.py` : add `diff`; route `generate --dry-run`.

---

## Task 1: Lift frontmatter primitives into `core/frontmatter.py`

**Files:**
- Create: `src/mf/core/frontmatter.py`
- Modify: `src/mf/series/frontmatter.py` (re-export primitives from core)
- Test: `tests/test_core/test_frontmatter.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_core/test_frontmatter.py`:

```python
from pathlib import Path

from mf.core.frontmatter import (
    compute_body_hash,
    frontmatter_equal,
    parse_post,
    parse_text,
)


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_text_splits_frontmatter_and_body():
    fm, body = parse_text('---\ntitle: "Hi"\ntags:\n  - a\n---\n\nHello world\n')
    assert fm["title"] == "Hi"
    assert fm["tags"] == ["a"]
    assert body.strip() == "Hello world"


def test_parse_post_reads_index_md_from_dir(tmp_path):
    _write(tmp_path / "index.md", '---\ntitle: "Hi"\n---\n\nBody\n')
    fm, body = parse_post(tmp_path)
    assert fm["title"] == "Hi"
    assert body.strip() == "Body"


def test_parse_post_missing_raises(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        parse_post(tmp_path / "nope")


def test_parse_text_and_parse_post_agree(tmp_path):
    text = '---\ntitle: "Hi"\n---\n\nSame body\n'
    _write(tmp_path / "index.md", text)
    assert parse_text(text) == parse_post(tmp_path)


def test_compute_body_hash_ignores_frontmatter(tmp_path):
    a = _write(tmp_path / "a" / "index.md", '---\ntitle: "A"\n---\n\nbody\n')
    b = _write(tmp_path / "b" / "index.md", '---\ntitle: "B"\ntts: true\n---\n\nbody\n')
    assert compute_body_hash(a.parent) == compute_body_hash(b.parent)


def test_frontmatter_equal_is_order_insensitive():
    assert frontmatter_equal({"a": 1, "b": 2}, {"b": 2, "a": 1})
    assert not frontmatter_equal({"a": 1}, {"a": 2})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_core/test_frontmatter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mf.core.frontmatter'`.

- [ ] **Step 3: Create `src/mf/core/frontmatter.py`**

```python
"""Generic frontmatter parsing, hashing, and equality.

Lifted out of mf.series.frontmatter so non-series modules (notably the
render-drift engine in mf.core.drift) can compare a post's body and metadata
without importing series-specific ownership logic. The series module
re-exports these names for backward compatibility and layers its
ownership-tier logic on top.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import frontmatter


def parse_post(path: Path) -> tuple[dict[str, Any], str]:
    """Parse an index.md into (frontmatter_dict, body_text).

    Args:
        path: A post directory (containing index.md) or a path to a markdown
            file directly.

    Raises:
        FileNotFoundError: if the index.md is missing.
    """
    index_file = path / "index.md" if path.is_dir() else path
    if not index_file.exists():
        raise FileNotFoundError(f"No index.md at {index_file}")
    post = frontmatter.load(index_file)
    return dict(post.metadata), post.content


def parse_text(text: str) -> tuple[dict[str, Any], str]:
    """Parse an in-memory markdown string into (frontmatter_dict, body_text)."""
    post = frontmatter.loads(text)
    return dict(post.metadata), post.content


def compute_body_hash(path: Path) -> str:
    """SHA256 of only the body of a post, ignoring frontmatter."""
    _, body = parse_post(path)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def frontmatter_equal(source_fm: dict[str, Any], target_fm: dict[str, Any]) -> bool:
    """Strict semantic equality of parsed frontmatter dicts (key order irrelevant)."""
    return source_fm == target_fm
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_core/test_frontmatter.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Re-point `src/mf/series/frontmatter.py` to the core primitives**

Replace the top of `src/mf/series/frontmatter.py` (the module docstring stays; replace the imports and the four primitive definitions) so it imports the primitives from core and keeps only the series-specific ownership layer. The new import block, placed after the module docstring:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mf.core.database import SeriesEntry
from mf.core.frontmatter import (  # re-exported for back-compat
    compute_body_hash,
    frontmatter_equal,
    parse_post,
    parse_text,
)

__all__ = [
    "compute_body_hash",
    "frontmatter_equal",
    "parse_post",
    "parse_text",
    "DEFAULT_BLOG_OWNED",
    "DEFAULT_SHARED",
    "get_ownership_sets",
    "classify_field",
    "FrontmatterFieldDiff",
    "compare_frontmatter",
]
```

Then DELETE the now-duplicated `import hashlib`, `from pathlib import Path`, `import frontmatter`, and the four function bodies `parse_post`, `compute_body_hash`, `frontmatter_equal` from this file. KEEP `DEFAULT_BLOG_OWNED`, `DEFAULT_SHARED`, `get_ownership_sets`, `classify_field`, `FrontmatterFieldDiff`, and `compare_frontmatter` exactly as they are (they continue to use the re-exported `parse_post` where needed).

- [ ] **Step 6: Run the series test suite to verify nothing broke**

Run: `pytest tests/test_series/ -v`
Expected: PASS (all existing series tests, including `test_frontmatter.py`, `test_differ.py`, `test_classify.py`, still green; `mf.series.frontmatter` re-exports keep their imports valid).

- [ ] **Step 7: Commit**

```bash
git add src/mf/core/frontmatter.py src/mf/series/frontmatter.py tests/test_core/test_frontmatter.py
git commit -m "refactor(core): lift frontmatter primitives into core/frontmatter"
```

---

## Task 2: The drift engine in `core/drift.py`

**Files:**
- Create: `src/mf/core/drift.py`
- Test: `tests/test_core/test_drift.py`

- [ ] **Step 1: Write the failing test (engine logic, against a fake Renderer)**

Create `tests/test_core/test_drift.py`:

```python
from pathlib import Path

from mf.core.drift import RenderFinding, check_render_drift


class FakeRenderer:
    """In-memory Renderer for testing the engine without real generators."""

    section = "fake"

    def __init__(self, root: Path, pages: dict[str, str | None]):
        # pages: slug -> rendered text, or None for "not renderable"
        self._root = root
        self._pages = pages

    def iter_slugs(self):
        return list(self._pages)

    def existing_slugs(self):
        return [p.name for p in self._root.iterdir() if (p / "index.md").exists()] if self._root.exists() else []

    def hugo_path(self, slug):
        return self._root / slug / "index.md"

    def render_page(self, slug):
        return self._pages.get(slug)


def _write_page(root: Path, slug: str, text: str) -> None:
    d = root / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.md").write_text(text, encoding="utf-8")


def _status_for(findings, slug):
    return next(f.status for f in findings if f.slug == slug)


def test_current_when_disk_matches_render(tmp_path):
    text = '---\ntitle: "A"\n---\n\nbody\n'
    _write_page(tmp_path, "a", text)
    findings = check_render_drift(FakeRenderer(tmp_path, {"a": text}))
    assert _status_for(findings, "a") == "current"


def test_current_ignores_frontmatter_key_order_and_whitespace(tmp_path):
    on_disk = '---\nb: 2\na: 1\n---\n\nbody\n'
    rendered = '---\na: 1\nb: 2\n---\n\nbody\n'
    _write_page(tmp_path, "a", on_disk)
    findings = check_render_drift(FakeRenderer(tmp_path, {"a": rendered}))
    assert _status_for(findings, "a") == "current"


def test_stale_when_body_differs(tmp_path):
    _write_page(tmp_path, "a", '---\ntitle: "A"\n---\n\nold body\n')
    findings = check_render_drift(FakeRenderer(tmp_path, {"a": '---\ntitle: "A"\n---\n\nnew body\n'}))
    assert _status_for(findings, "a") == "stale"


def test_missing_when_renderable_but_no_page(tmp_path):
    findings = check_render_drift(FakeRenderer(tmp_path, {"a": '---\ntitle: "A"\n---\n\nbody\n'}))
    assert _status_for(findings, "a") == "missing"


def test_orphan_when_page_on_disk_unknown_to_renderer(tmp_path):
    _write_page(tmp_path, "ghost", '---\ntitle: "Ghost"\n---\n\nbody\n')
    findings = check_render_drift(FakeRenderer(tmp_path, {}))
    assert _status_for(findings, "ghost") == "orphan"


def test_orphan_when_known_but_not_renderable_and_on_disk(tmp_path):
    _write_page(tmp_path, "a", '---\ntitle: "A"\n---\n\nbody\n')
    findings = check_render_drift(FakeRenderer(tmp_path, {"a": None}))
    assert _status_for(findings, "a") == "orphan"


def test_findings_are_render_finding_instances(tmp_path):
    findings = check_render_drift(FakeRenderer(tmp_path, {"a": "---\n---\n\nx\n"}))
    assert all(isinstance(f, RenderFinding) for f in findings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_core/test_drift.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mf.core.drift'`.

- [ ] **Step 3: Create `src/mf/core/drift.py`**

```python
"""Render-drift engine: compare on-disk Hugo pages against a fresh render.

A projection module (papers, projects, packages, publications) supplies a
Renderer binding; this module supplies the mechanism. Drift is computed live
by re-rendering and comparing semantically (frontmatter dict equality plus
body equality), never by textual YAML comparison and never by persisted hash
state.

This mirrors the binding-plus-mechanism seam in mf.core.field_ops.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from mf.core.frontmatter import parse_post, parse_text

if TYPE_CHECKING:
    from rich.console import Console


@runtime_checkable
class Renderer(Protocol):
    """Per-module binding the drift engine needs to inspect one section."""

    section: str

    def iter_slugs(self) -> Iterable[str]:
        """Slugs generate would produce a primary page for."""
        ...

    def existing_slugs(self) -> Iterable[str]:
        """Slugs that currently have a primary page on disk."""
        ...

    def hugo_path(self, slug: str) -> Path:
        """Path to the primary page for slug (may or may not exist)."""
        ...

    def render_page(self, slug: str) -> str | None:
        """Text generate would write for slug, or None if not renderable."""
        ...


@dataclass
class RenderFinding:
    """One page's drift status. status in {current, stale, missing, orphan}."""

    slug: str
    status: str
    detail: str = ""


STATUS_STYLE = {
    "stale": "yellow",
    "missing": "green",
    "orphan": "red",
    "current": "dim",
}

_DRY_RUN_VERB = {
    "missing": "create",
    "stale": "update",
    "current": "skip",
    "orphan": "skip (orphan)",
}


def _semantic_equal(rendered: str, path: Path) -> bool:
    r_fm, r_body = parse_text(rendered)
    d_fm, d_body = parse_post(path)
    return r_fm == d_fm and r_body == d_body


def check_render_drift(renderer: Renderer) -> list[RenderFinding]:
    """Compare every page against a fresh render. Read-only."""
    findings: list[RenderFinding] = []
    known = set(renderer.iter_slugs())
    on_disk = set(renderer.existing_slugs())

    for slug in sorted(known):
        path = renderer.hugo_path(slug)
        rendered = renderer.render_page(slug)
        if rendered is None:
            if slug in on_disk or path.exists():
                findings.append(RenderFinding(slug, "orphan", "on disk but not renderable"))
            continue
        if not path.exists():
            findings.append(RenderFinding(slug, "missing", "generate would create"))
        elif _semantic_equal(rendered, path):
            findings.append(RenderFinding(slug, "current"))
        else:
            findings.append(RenderFinding(slug, "stale", "generate would update"))

    for slug in sorted(on_disk - known):
        findings.append(RenderFinding(slug, "orphan", "on disk, unknown to database"))

    return findings


def print_drift_report(
    findings: list[RenderFinding],
    *,
    section: str,
    console: Console,
    show_current: bool = False,
) -> None:
    """Print a findings table. Drift-only by default."""
    from rich.table import Table

    relevant = findings if show_current else [f for f in findings if f.status != "current"]
    if not relevant:
        console.print(f"[green]{section}: all pages current ({len(findings)} checked)[/green]")
        return

    table = Table(title=f"Render drift: {section}")
    table.add_column("Slug", style="cyan")
    table.add_column("Status")
    table.add_column("Detail", style="dim")
    for f in sorted(relevant, key=lambda x: (x.status, x.slug)):
        style = STATUS_STYLE.get(f.status, "")
        status_cell = f"[{style}]{f.status}[/{style}]" if style else f.status
        table.add_row(f.slug, status_cell, f.detail)
    console.print(table)


def print_render_diff(renderer: Renderer, slug: str, console: Console) -> None:
    """Print a unified diff for one page: '-' is on disk, '+' is generate."""
    from rich.panel import Panel
    from rich.syntax import Syntax

    rendered = renderer.render_page(slug)
    if rendered is None:
        console.print(f"[dim]{slug}: not renderable; nothing to diff[/dim]")
        return
    path = renderer.hugo_path(slug)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    diff_lines = list(
        difflib.unified_diff(
            current.splitlines(),
            rendered.splitlines(),
            fromfile=f"{slug} (on disk)",
            tofile=f"{slug} (generate)",
            lineterm="",
        )
    )
    if not diff_lines:
        console.print(f"[dim]{slug}: no textual difference[/dim]")
        return
    syntax = Syntax("\n".join(diff_lines), "diff", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, title=f"diff: {slug}", border_style="cyan"))


def print_dry_run_preview(
    renderer: Renderer,
    *,
    console: Console,
    only_slug: str | None = None,
) -> None:
    """Print 'would create|update|skip: path' for each page."""
    findings = check_render_drift(renderer)
    if only_slug is not None:
        findings = [f for f in findings if f.slug == only_slug]
        if not findings:
            console.print(f"[red]Unknown slug for {renderer.section}: {only_slug}[/red]")
            raise SystemExit(1)
    for f in sorted(findings, key=lambda x: x.slug):
        verb = _DRY_RUN_VERB.get(f.status, f.status)
        console.print(f"  would {verb}: {renderer.hugo_path(f.slug)}")


def run_diff_command(
    renderer: Renderer,
    *,
    console: Console,
    slug: str | None = None,
    full: bool = False,
) -> None:
    """Shared body of every `mf <module> diff` command. Read-only."""
    findings = check_render_drift(renderer)
    if slug is not None:
        match = next((f for f in findings if f.slug == slug), None)
        if match is None:
            console.print(f"[red]Unknown slug for {renderer.section}: {slug}[/red]")
            raise SystemExit(1)
        print_drift_report([match], section=renderer.section, console=console, show_current=True)
        if match.status in ("stale", "missing"):
            print_render_diff(renderer, slug, console)
        return
    print_drift_report(findings, section=renderer.section, console=console)
    if full:
        for f in findings:
            if f.status in ("stale", "missing"):
                print_render_diff(renderer, f.slug, console)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_core/test_drift.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Add helper tests for report/preview/diff (no crashes, correct verbs)**

Append to `tests/test_core/test_drift.py`:

```python
def test_dry_run_preview_uses_create_update_skip_verbs(tmp_path, capsys):
    from rich.console import Console

    from mf.core.drift import print_dry_run_preview

    _write_page(tmp_path, "stale", '---\ntitle: "x"\n---\n\nold\n')
    _write_page(tmp_path, "cur", '---\ntitle: "x"\n---\n\nsame\n')
    renderer = FakeRenderer(
        tmp_path,
        {
            "stale": '---\ntitle: "x"\n---\n\nnew\n',
            "cur": '---\ntitle: "x"\n---\n\nsame\n',
            "new": '---\ntitle: "x"\n---\n\nbody\n',
        },
    )
    print_dry_run_preview(renderer, console=Console())
    out = capsys.readouterr().out
    assert "would update" in out
    assert "would create" in out
    assert "would skip" in out


def test_run_diff_command_unknown_slug_exits(tmp_path):
    import pytest
    from rich.console import Console

    from mf.core.drift import run_diff_command

    with pytest.raises(SystemExit):
        run_diff_command(FakeRenderer(tmp_path, {}), console=Console(), slug="nope")
```

- [ ] **Step 6: Run the new helper tests**

Run: `pytest tests/test_core/test_drift.py -v`
Expected: PASS (9 tests).

- [ ] **Step 7: Commit**

```bash
git add src/mf/core/drift.py tests/test_core/test_drift.py
git commit -m "feat(core): add render-drift engine (Renderer protocol + check_render_drift)"
```

---

## Task 3: Publications (reference Renderer, already split)

**Files:**
- Modify: `src/mf/publications/generate.py` (add `PublicationsRenderer`)
- Modify: `src/mf/publications/commands.py` (add `diff`; route `generate --dry-run`)
- Test: `tests/test_publications/test_drift.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_publications/test_drift.py`:

```python
from mf.core.drift import check_render_drift


def _make_renderer(mock_site_root):
    from mf.core.config import get_paths
    from mf.publications.database import PubEntry, PubsDatabase
    from mf.publications.generate import PublicationsRenderer

    db = PubsDatabase()
    db.load()
    db.set(PubEntry(slug="p1", title="Paper One", status="published", type="preprint", date="2024-01-02"))
    db.save()
    return PublicationsRenderer(db, get_paths())


def test_missing_then_current_after_generate(mock_site_root):
    from mf.publications.generate import generate_publications

    renderer = _make_renderer(mock_site_root)
    findings = {f.slug: f.status for f in check_render_drift(renderer)}
    assert findings["p1"] == "missing"

    generate_publications(slug="p1", dry_run=False, force=False)
    findings = {f.slug: f.status for f in check_render_drift(renderer)}
    assert findings["p1"] == "current"


def test_stale_after_title_change(mock_site_root):
    from mf.publications.generate import generate_publications

    renderer = _make_renderer(mock_site_root)
    generate_publications(slug="p1", dry_run=False, force=False)

    entry = renderer._db.get("p1")
    entry.title = "Paper One (Revised)"
    renderer._db.set(entry)
    renderer._db.save()

    findings = {f.slug: f.status for f in check_render_drift(renderer)}
    assert findings["p1"] == "stale"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_publications/test_drift.py -v`
Expected: FAIL with `ImportError: cannot import name 'PublicationsRenderer'`.

- [ ] **Step 3: Add `PublicationsRenderer` to `src/mf/publications/generate.py`**

Append at the end of the file:

```python
class PublicationsRenderer:
    """Renderer binding for the render-drift engine."""

    section = "publications"

    def __init__(self, db: PubsDatabase, paths) -> None:
        self._db = db
        self._paths = paths

    def iter_slugs(self):
        return list(self._db)

    def existing_slugs(self):
        d = self._paths.publications
        if not d.exists():
            return []
        return [p.name for p in d.iterdir() if (p / "index.md").exists()]

    def hugo_path(self, slug: str) -> Path:
        return self._paths.publications / slug / "index.md"

    def render_page(self, slug: str) -> str | None:
        entry = self._db.get(slug)
        if entry is None:
            return None
        return generate_publication_content(pub_to_frontmatter(entry))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_publications/test_drift.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Add the `mf pubs diff` command and route `generate --dry-run`**

In `src/mf/publications/commands.py`, add a new command (place it after the `generate` command). Note: the module already imports `console` and `get_paths`.

```python
@pubs.command(name="diff")
@click.argument("slug", required=False)
@click.option("--full", is_flag=True, help="Show a unified diff for each drifted page")
@click.pass_obj
def diff(ctx, slug: str | None, full: bool) -> None:
    """Show what `mf pubs generate` would change (read-only).

    \b
    Examples:
        mf pubs diff
        mf pubs diff my-paper
        mf pubs diff --full
    """
    from mf.core.drift import run_diff_command
    from mf.publications.generate import PublicationsRenderer

    renderer = PublicationsRenderer(_load_db(), get_paths())
    run_diff_command(renderer, console=console, slug=slug, full=full)
```

Then change the body of the existing `generate` command so dry-run goes through the preview. Replace its current body:

```python
    from mf.publications.generate import generate_publications

    dry_run = ctx.dry_run if ctx else False
    generate_publications(slug=slug, dry_run=dry_run, force=force)
```

with:

```python
    dry_run = ctx.dry_run if ctx else False
    if dry_run:
        from mf.core.drift import print_dry_run_preview
        from mf.publications.generate import PublicationsRenderer

        renderer = PublicationsRenderer(_load_db(), get_paths())
        print_dry_run_preview(renderer, console=console, only_slug=slug)
        return

    from mf.publications.generate import generate_publications

    generate_publications(slug=slug, dry_run=False, force=force)
```

- [ ] **Step 6: Write CLI tests for the new command surface**

Append to `tests/test_publications/test_drift.py`:

```python
def test_diff_cli_reports_missing(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _make_renderer(mock_site_root)  # seeds p1, no page generated yet
    result = CliRunner().invoke(main, ["pubs", "diff"])
    assert result.exit_code == 0
    assert "missing" in result.output


def test_generate_dry_run_says_would_create(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _make_renderer(mock_site_root)
    result = CliRunner().invoke(main, ["--dry-run", "pubs", "generate"])
    assert result.exit_code == 0
    assert "would create" in result.output
```

- [ ] **Step 7: Run the publications tests**

Run: `pytest tests/test_publications/test_drift.py -v`
Expected: PASS (4 tests).

- [ ] **Step 8: Commit**

```bash
git add src/mf/publications/generate.py src/mf/publications/commands.py tests/test_publications/test_drift.py
git commit -m "feat(pubs): add render-drift diff and enriched generate --dry-run"
```

---

## Task 4: Packages (extract pure render + Renderer)

**Files:**
- Modify: `src/mf/packages/generator.py` (extract `render_package_page`; add `PackagesRenderer`)
- Modify: `src/mf/packages/commands.py` (add `diff`; route `generate --dry-run`)
- Test: `tests/test_packages/test_drift.py`

- [ ] **Step 1: Write the failing test (render purity + determinism)**

Create `tests/test_packages/test_drift.py`:

```python
from mf.core.drift import check_render_drift


def _seed(mock_site_root):
    from mf.packages.database import PackageDatabase

    db = PackageDatabase()
    db.load()
    db.set("requests", {"name": "requests", "registry": "pypi", "date_added": "2024-01-02"})
    db.save()
    return db


def test_render_package_page_is_deterministic(mock_site_root):
    from mf.packages.database import PackageDatabase
    from mf.packages.generator import render_package_page

    _seed(mock_site_root)
    db = PackageDatabase()
    db.load()
    entry = db.get("requests")
    first = render_package_page("requests", entry)
    second = render_package_page("requests", entry)
    assert first == second
    assert "date: 2024-01-02" in first


def test_render_package_page_no_wallclock_date_when_missing(mock_site_root):
    from datetime import date

    from mf.packages.database import PackageDatabase
    from mf.packages.generator import render_package_page

    db = PackageDatabase()
    db.load()
    db.set("nodate", {"name": "nodate", "registry": "pypi"})
    db.save()
    entry = db.get("nodate")
    rendered = render_package_page("nodate", entry)
    # No wall-clock date leaks in: today's date must not appear.
    assert date.today().isoformat() not in rendered


def test_packages_drift_missing_then_current(mock_site_root):
    from mf.core.config import get_paths
    from mf.packages.database import PackageDatabase
    from mf.packages.generator import PackagesRenderer, generate_all_packages

    _seed(mock_site_root)
    db = PackageDatabase()
    db.load()
    renderer = PackagesRenderer(db, get_paths())
    assert {f.slug: f.status for f in check_render_drift(renderer)}["requests"] == "missing"

    generate_all_packages(db, dry_run=False)
    assert {f.slug: f.status for f in check_render_drift(renderer)}["requests"] == "current"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_packages/test_drift.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_package_page'`.

- [ ] **Step 3: Extract the pure render and refactor the write path in `src/mf/packages/generator.py`**

Add `render_package_page` (the string builder, with the wall-clock fallback removed: emit `date` only when `date_added` is present), and make `generate_package_content` call it. Replace the existing `generate_package_content` function body's render section. The new functions:

```python
def render_package_page(slug: str, entry: PackageEntry) -> str:
    """Render the index.md text for a package. Pure: no writes, no wall clock."""
    lines: list[str] = ["---"]
    lines.append(f'title: "{_yaml_escape(entry.name)}"')
    lines.append(f'slug: "{_yaml_escape(slug)}"')
    entry_date = entry.data.get("date_added")
    if entry_date:
        lines.append(f"date: {entry_date}")

    if entry.description:
        lines.append(f'description: "{_yaml_escape(entry.description)}"')
    if entry.registry:
        lines.append(f'registry: "{_yaml_escape(entry.registry)}"')
    if entry.latest_version:
        lines.append(f'latest_version: "{_yaml_escape(entry.latest_version)}"')
    if entry.install_command:
        lines.append(f'install_command: "{_yaml_escape(entry.install_command)}"')
    if entry.registry_url:
        lines.append(f'registry_url: "{_yaml_escape(entry.registry_url)}"')
    if entry.downloads is not None:
        lines.append(f"downloads: {entry.downloads}")
    if entry.license:
        lines.append(f'license: "{_yaml_escape(entry.license)}"')
    if entry.featured:
        lines.append("featured: true")
    if entry.tags:
        lines.append("tags:")
        for tag in entry.tags:
            lines.append(f'  - "{_yaml_escape(tag)}"')
    if entry.project:
        lines.append(f'linked_project: "/projects/{_yaml_escape(entry.project)}/"')
    aliases = entry.data.get("aliases", [])
    if aliases:
        lines.append("aliases:")
        for alias in aliases:
            lines.append(f'  - "{_yaml_escape(alias)}"')

    lines.append("---")
    lines.append("")
    return "\n".join(lines)
```

Then replace the body of `generate_package_content` so it delegates to the renderer:

```python
def generate_package_content(
    slug: str,
    entry: PackageEntry,
    dry_run: bool = False,
) -> None:
    """Generate Hugo content for a single package (render + write)."""
    paths = get_paths()
    content_path = paths.packages / slug / "index.md"
    content = render_package_page(slug, entry)

    if dry_run:
        console.print(f"  [dim]Would write: {content_path}[/dim]")
        return

    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_text(content, encoding="utf-8")
    console.print(f"  [green]✓[/green] Generated: {content_path}")
```

Remove the now-unused `from datetime import date` import at the top of the file if nothing else uses it.

- [ ] **Step 4: Add `PackagesRenderer` to `src/mf/packages/generator.py`**

Append at the end of the file:

```python
class PackagesRenderer:
    """Renderer binding for the render-drift engine."""

    section = "packages"

    def __init__(self, db: PackageDatabase, paths) -> None:
        self._db = db
        self._paths = paths

    def iter_slugs(self):
        return [slug for slug, _ in self._db.items()]

    def existing_slugs(self):
        d = self._paths.packages
        if not d.exists():
            return []
        return [p.name for p in d.iterdir() if (p / "index.md").exists()]

    def hugo_path(self, slug: str):
        return self._paths.packages / slug / "index.md"

    def render_page(self, slug: str) -> str | None:
        entry = self._db.get(slug)
        if entry is None:
            return None
        return render_package_page(slug, entry)
```

`PackageDatabase` and `PackageEntry` are already imported under `TYPE_CHECKING`; for the runtime annotation on `PackagesRenderer.__init__` keep the parameter untyped at runtime (the `TYPE_CHECKING` import is enough for `PackageEntry` in `render_package_page`'s signature because of `from __future__ import annotations`).

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_packages/test_drift.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Add `mf packages diff` and route `generate --dry-run` in `src/mf/packages/commands.py`**

Add the diff command (place after the `generate` command):

```python
@packages.command(name="diff")
@click.argument("name", required=False)
@click.option("--full", is_flag=True, help="Show a unified diff for each drifted page")
def diff(name: str | None, full: bool) -> None:
    """Show what `mf packages generate` would change (read-only).

    \\b
    Examples:
        mf packages diff
        mf packages diff requests
        mf packages diff --full
    """
    from mf.core.config import get_paths
    from mf.core.drift import run_diff_command
    from mf.packages.database import PackageDatabase
    from mf.packages.generator import PackagesRenderer

    db = PackageDatabase()
    db.load()
    renderer = PackagesRenderer(db, get_paths())
    run_diff_command(renderer, console=console, slug=name, full=full)
```

Then enrich the `generate` command. Replace its body:

```python
    from mf.packages.database import PackageDatabase
    from mf.packages.generator import generate_all_packages, generate_package_content

    dry_run = _get_dry_run(ctx)

    db = PackageDatabase()
    db.load()

    if name:
        entry = db.get(name)
        if not entry:
            console.print(f"[red]Package not found: {name}[/red]")
            return

        console.print(f"[cyan]Generating content for {name}...[/cyan]")
        generate_package_content(name, entry, dry_run=dry_run)
    else:
        console.print("[cyan]Generating content for all packages...[/cyan]")
        success, failed = generate_all_packages(db, dry_run=dry_run)
        console.print(f"\n[green]Generated:[/green] {success} success, {failed} failed")
```

with:

```python
    from mf.packages.database import PackageDatabase

    dry_run = _get_dry_run(ctx)

    db = PackageDatabase()
    db.load()

    if dry_run:
        from mf.core.config import get_paths
        from mf.core.drift import print_dry_run_preview
        from mf.packages.generator import PackagesRenderer

        renderer = PackagesRenderer(db, get_paths())
        print_dry_run_preview(renderer, console=console, only_slug=name)
        return

    from mf.packages.generator import generate_all_packages, generate_package_content

    if name:
        entry = db.get(name)
        if not entry:
            console.print(f"[red]Package not found: {name}[/red]")
            return
        console.print(f"[cyan]Generating content for {name}...[/cyan]")
        generate_package_content(name, entry, dry_run=False)
    else:
        console.print("[cyan]Generating content for all packages...[/cyan]")
        success, failed = generate_all_packages(db, dry_run=False)
        console.print(f"\n[green]Generated:[/green] {success} success, {failed} failed")
```

- [ ] **Step 7: Add CLI tests**

Append to `tests/test_packages/test_drift.py`:

```python
def test_packages_diff_cli_reports_missing(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _seed(mock_site_root)
    result = CliRunner().invoke(main, ["packages", "diff"])
    assert result.exit_code == 0
    assert "missing" in result.output


def test_packages_generate_dry_run_says_would_create(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _seed(mock_site_root)
    result = CliRunner().invoke(main, ["--dry-run", "packages", "generate"])
    assert result.exit_code == 0
    assert "would create" in result.output
```

- [ ] **Step 8: Run the full packages suite to confirm no regressions**

Run: `pytest tests/test_packages/ -v`
Expected: PASS (new drift tests plus existing packages tests, including any that exercised `generate_package_content`).

- [ ] **Step 9: Commit**

```bash
git add src/mf/packages/generator.py src/mf/packages/commands.py tests/test_packages/test_drift.py
git commit -m "feat(packages): split render/write, add render-drift diff and dry-run preview"
```

---

## Task 5: Papers (deterministic render + date pinning in write path)

**Files:**
- Modify: `src/mf/papers/generator.py` (extract `render_paper_page`; pin date in write path; add `PapersRenderer`)
- Modify: `src/mf/papers/commands.py` (add `diff`; route `generate --dry-run`)
- Test: `tests/test_papers/test_drift.py`

Notes: papers' source of slugs is the `/static/latex/<slug>/` directory, not `paper_db`. `render_paper_page` must read HTML/PDF metadata but must NOT write a thumbnail and must NOT read the file mtime for the date. The thumbnail write and the one-time date pin stay in the write path (`generate_paper_content`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_papers/test_drift.py`:

```python
from mf.core.drift import check_render_drift


def _seed_latex(mock_site_root, slug="demo"):
    """Create a minimal HTML-only paper under static/latex/<slug>/."""
    from mf.core.config import get_paths

    paths = get_paths()
    d = paths.latex / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(
        "<html><head><title>Demo Paper</title></head><body>x</body></html>",
        encoding="utf-8",
    )
    return slug


def test_render_paper_page_is_deterministic_and_has_no_mtime_date(mock_site_root):
    from datetime import date

    from mf.core.database import PaperDatabase
    from mf.papers.generator import render_paper_page

    _seed_latex(mock_site_root, "demo")
    db = PaperDatabase()
    db.load()
    first = render_paper_page("demo", db)
    second = render_paper_page("demo", db)
    assert first == second
    assert first is not None
    # Wall-clock / mtime date must not leak into a deterministic render.
    assert date.today().isoformat() not in first


def test_render_paper_page_none_when_no_artifacts(mock_site_root):
    from mf.core.config import get_paths
    from mf.core.database import PaperDatabase
    from mf.papers.generator import render_paper_page

    (get_paths().latex / "empty").mkdir(parents=True, exist_ok=True)
    db = PaperDatabase()
    db.load()
    assert render_paper_page("empty", db) is None


def test_papers_drift_missing_then_current(mock_site_root):
    from mf.core.config import get_paths
    from mf.core.database import PaperDatabase
    from mf.papers.generator import PapersRenderer, generate_paper_content

    _seed_latex(mock_site_root, "demo")
    db = PaperDatabase()
    db.load()
    renderer = PapersRenderer(db, get_paths())
    assert {f.slug: f.status for f in check_render_drift(renderer)}["demo"] == "missing"

    generate_paper_content("demo", db, use_image_cache=True, dry_run=False)
    assert {f.slug: f.status for f in check_render_drift(renderer)}["demo"] == "current"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_papers/test_drift.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_paper_page'`.

- [ ] **Step 3: Extract `render_paper_page` in `src/mf/papers/generator.py`**

Add this function (it performs the reads and formatting from the current `generate_paper_content`, minus the mtime date fallback and minus thumbnail generation; the image field is set only if a thumbnail already exists on disk):

```python
def render_paper_page(slug: str, db: PaperDatabase) -> str | None:
    """Render the index.md text for a paper. Pure: reads only, no writes, no mtime.

    Returns None when the paper has no HTML or PDF artifacts.
    """
    paths = get_paths()
    paper_dir = paths.latex / slug
    if not paper_dir.exists():
        return None

    html_file = find_html_file(paper_dir)
    pdf_file = find_pdf_file(paper_dir)
    if not html_file and not pdf_file:
        return None

    is_pdf_only = not html_file and pdf_file
    extracted = extract_paper_metadata(slug, paper_dir)
    entry = db.get(slug)
    manual = entry.data if entry else {}
    metadata = {**extracted, **manual}

    if not metadata.get("title"):
        metadata["title"] = slug.replace("-", " ").title()
    # No mtime fallback here: render stays deterministic. render_paper_frontmatter
    # supplies a static default date when none is stored. The write path pins a
    # real date into paper_db so it is stable thereafter.

    pdf_filename = pdf_file.name if pdf_file else ""
    pdf_size = format_file_size(pdf_file.stat().st_size) if pdf_file else ""
    page_count = metadata.get("page_count", 0)

    thumb_path = paper_dir / "thumbnail.jpg"
    if thumb_path.exists():
        metadata["image"] = f"/latex/{slug}/thumbnail.jpg"

    vars = render_paper_frontmatter(
        slug=slug,
        metadata=metadata,
        pdf_file=pdf_filename,
        pdf_size=pdf_size,
        page_count=page_count,
    )
    template = PDF_ONLY_TEMPLATE if is_pdf_only else PAPER_TEMPLATE
    return template.format(**vars)
```

- [ ] **Step 4: Refactor `generate_paper_content` to use the renderer, keep thumbnail, and pin the date**

Replace the body of `generate_paper_content` so it pins a date into `paper_db` when none is stored (using mtime once), generates the thumbnail (write side effect), then renders and writes:

```python
def generate_paper_content(
    slug: str,
    db: PaperDatabase,
    use_image_cache: bool = True,
    dry_run: bool = False,
) -> bool:
    """Generate Hugo content for a single paper (pin date, thumbnail, render, write)."""
    paths = get_paths()
    paper_dir = paths.latex / slug

    if not paper_dir.exists():
        console.print(f"  [red]Paper directory not found: {paper_dir}[/red]")
        return False

    html_file = find_html_file(paper_dir)
    pdf_file = find_pdf_file(paper_dir)
    if not html_file and not pdf_file:
        console.print(f"  [red]No HTML or PDF found for {slug}[/red]")
        return False

    # Pin a stable date into paper_db once, so render stays deterministic.
    entry = db.get(slug)
    has_date = bool(entry and entry.data.get("date")) or bool(
        extract_paper_metadata(slug, paper_dir).get("date")
    )
    if not has_date and not dry_run:
        import datetime

        mtime = paper_dir.stat().st_mtime
        pinned = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        db.update(slug, date=pinned)

    # Thumbnail generation is a write side effect; keep it out of render.
    if pdf_file and HAS_PDF2IMAGE:
        thumb_path = paper_dir / "thumbnail.jpg"
        if not thumb_path.exists() or not use_image_cache:
            generate_thumbnail(pdf_file, thumb_path, dry_run=dry_run)

    content = render_paper_page(slug, db)
    if content is None:
        console.print(f"  [red]Nothing to render for {slug}[/red]")
        return False

    content_dir = paths.papers / slug
    content_file = content_dir / "index.md"

    if dry_run:
        console.print(f"  [dim]Would write: {content_file}[/dim]")
        return True

    content_dir.mkdir(parents=True, exist_ok=True)
    content_file.write_text(content, encoding="utf-8")
    console.print(f"  [green]✓[/green] Generated: {content_file}")
    return True
```

- [ ] **Step 5: Add `PapersRenderer` to `src/mf/papers/generator.py`**

Append at the end of the file:

```python
class PapersRenderer:
    """Renderer binding for the render-drift engine.

    Slugs come from /static/latex/<slug>/ (the artifact dirs), matching how
    `generate_papers` iterates.
    """

    section = "papers"

    def __init__(self, db: PaperDatabase, paths) -> None:
        self._db = db
        self._paths = paths

    def iter_slugs(self):
        d = self._paths.latex
        if not d.exists():
            return []
        return [p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith(".")]

    def existing_slugs(self):
        d = self._paths.papers
        if not d.exists():
            return []
        return [p.name for p in d.iterdir() if (p / "index.md").exists()]

    def hugo_path(self, slug: str):
        return self._paths.papers / slug / "index.md"

    def render_page(self, slug: str) -> str | None:
        return render_paper_page(slug, self._db)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_papers/test_drift.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Add `mf papers diff` and route `generate --dry-run` in `src/mf/papers/commands.py`**

Add the diff command (place after the `generate` command, which is the one at line 62-73 using group `papers`):

```python
@papers.command(name="diff")
@click.argument("slug", required=False)
@click.option("--full", is_flag=True, help="Show a unified diff for each drifted page")
@click.pass_obj
def diff(ctx, slug: str | None, full: bool) -> None:
    """Show what `mf papers generate` would change (read-only).

    \b
    Examples:
        mf papers diff
        mf papers diff my-paper
        mf papers diff --full
    """
    from mf.core.config import get_paths
    from mf.core.database import PaperDatabase
    from mf.core.drift import run_diff_command
    from mf.papers.generator import PapersRenderer

    db = PaperDatabase()
    db.load()
    renderer = PapersRenderer(db, get_paths())
    run_diff_command(renderer, console=console, slug=slug, full=full)
```

Then route the existing `generate` command's dry-run. Its current body is:

```python
    from mf.papers.generator import generate_papers

    dry_run = ctx.dry_run if ctx else False
    generate_papers(slug=slug, use_image_cache=not no_image_cache, dry_run=dry_run)
```

Replace with:

```python
    dry_run = ctx.dry_run if ctx else False
    if dry_run:
        from mf.core.config import get_paths
        from mf.core.database import PaperDatabase
        from mf.core.drift import print_dry_run_preview
        from mf.papers.generator import PapersRenderer

        db = PaperDatabase()
        db.load()
        renderer = PapersRenderer(db, get_paths())
        print_dry_run_preview(renderer, console=console, only_slug=slug)
        return

    from mf.papers.generator import generate_papers

    generate_papers(slug=slug, use_image_cache=not no_image_cache, dry_run=False)
```

(If the local variable name for the no-image-cache flag differs in the file, keep the existing name; only the dry-run branch is being added.)

- [ ] **Step 8: Add CLI tests**

Append to `tests/test_papers/test_drift.py`:

```python
def test_papers_diff_cli_reports_missing(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _seed_latex(mock_site_root, "demo")
    result = CliRunner().invoke(main, ["papers", "diff"])
    assert result.exit_code == 0
    assert "missing" in result.output


def test_papers_generate_dry_run_says_would_create(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _seed_latex(mock_site_root, "demo")
    result = CliRunner().invoke(main, ["--dry-run", "papers", "generate"])
    assert result.exit_code == 0
    assert "would create" in result.output
```

- [ ] **Step 9: Run the full papers suite to confirm no regressions**

Run: `pytest tests/test_papers/ -v`
Expected: PASS (new drift tests plus existing papers tests; pay attention to any test that asserted on `generate_paper_content` output containing an mtime date, and update it to the deterministic behavior if present).

- [ ] **Step 10: Commit**

```bash
git add src/mf/papers/generator.py src/mf/papers/commands.py tests/test_papers/test_drift.py
git commit -m "feat(papers): deterministic render split with date pinning, add diff and dry-run"
```

---

## Task 6: Projects (deterministic primary-page render + Renderer)

**Files:**
- Modify: `src/mf/projects/generator.py` (extract `render_project_page`; drop now() fallbacks; add `ProjectsRenderer`)
- Modify: `src/mf/projects/commands.py` (add `diff`; route `generate --dry-run`)
- Test: `tests/test_projects/test_drift.py`

Notes: projects' slugs come from the GitHub cache (minus hidden entries). The primary page is `index.md` for a leaf bundle or `_index.md` for a rich project (`rich_project: true`). `render_project_page` renders only that primary page (section stubs, branch extras, and hide-delete stay in the write path and are out of drift scope for this slice). `created_at` comes from the cache; remove the `datetime.now()` fallbacks so render is deterministic.

- [ ] **Step 1: Write the failing test**

Create `tests/test_projects/test_drift.py`:

```python
from mf.core.drift import check_render_drift


def _seed(mock_site_root, slug="proj", rich=False):
    from mf.core.database import ProjectsCache, ProjectsDatabase

    cache = ProjectsCache()
    cache.load()
    cache.set(
        slug,
        {
            "name": slug,
            "html_url": f"https://github.com/queelius/{slug}",
            "description": "A demo project",
            "created_at": "2023-05-01T00:00:00Z",
            "stargazers_count": 3,
            "topics": ["demo"],
            "language": "Python",
        },
    )
    cache.save()

    db = ProjectsDatabase()
    db.load()
    if rich:
        db.set(slug, {"rich_project": True})
        db.save()
    return cache, db


def test_render_project_page_is_deterministic(mock_site_root):
    from mf.projects.generator import merge_project_data, render_project_page

    cache, db = _seed(mock_site_root, "proj")
    merged = merge_project_data("proj", cache.get("proj"), db.get("proj") or {})
    assert render_project_page("proj", merged) == render_project_page("proj", merged)


def test_render_project_page_no_wallclock_date(mock_site_root):
    from datetime import datetime

    from mf.projects.generator import merge_project_data, render_project_page

    cache, db = _seed(mock_site_root, "proj")
    merged = merge_project_data("proj", cache.get("proj"), db.get("proj") or {})
    rendered = render_project_page("proj", merged)
    # created_at is from the cache; this year's now() must not appear.
    assert f"date: {datetime.now().year}" not in rendered
    assert "2023-05-01" in rendered


def test_projects_drift_missing_then_current(mock_site_root):
    from mf.core.config import get_paths
    from mf.core.database import ProjectsCache, ProjectsDatabase
    from mf.projects.generator import ProjectsRenderer, generate_all_projects

    _seed(mock_site_root, "proj")
    cache = ProjectsCache()
    cache.load()
    db = ProjectsDatabase()
    db.load()
    renderer = ProjectsRenderer(cache, db, get_paths())
    assert {f.slug: f.status for f in check_render_drift(renderer)}["proj"] == "missing"

    generate_all_projects(cache, db, dry_run=False)
    assert {f.slug: f.status for f in check_render_drift(renderer)}["proj"] == "current"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_projects/test_drift.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_project_page'`.

- [ ] **Step 3: Make `generate_project_frontmatter` deterministic and extract `render_project_page`**

In `src/mf/projects/generator.py`, change the two wall-clock fallbacks in `generate_project_frontmatter` so dates come only from the cache:

Replace:

```python
    default_date = datetime.now(timezone.utc).isoformat()
    created_at = github_data.get("created_at", default_date)
```

with:

```python
    created_at = github_data.get("created_at", "")
```

And replace (in the project section block):

```python
        f"  year_started: {created_at[:4] if created_at else datetime.now().year}",
```

with:

```python
        f"  year_started: {created_at[:4] if created_at else ''}",
```

Remove the now-unused `from datetime import datetime, timezone` import if nothing else in the file uses it (search the file first; if `datetime` is still referenced elsewhere, leave the import).

Then add the pure primary-page renderer (this mirrors the primary-page portion of `generate_project_content`, leaving stubs and deletes to the write path):

```python
def render_project_page(slug: str, metadata: dict[str, Any]) -> str:
    """Render the primary project page (index.md or _index.md). Pure, deterministic."""
    github_data = metadata.get("github_data", {})
    is_rich = metadata.get("rich_project", False)

    readme_content = metadata.get("readme_override", github_data.get("_readme_content", ""))
    if readme_content and not metadata.get("readme_override"):
        html_url = github_data.get("html_url", "")
        default_branch = github_data.get("default_branch", "main")
        if html_url:
            readme_content = rewrite_readme_urls(readme_content, html_url, default_branch)

    frontmatter = generate_project_frontmatter(slug, metadata, is_branch_bundle=is_rich)
    content = frontmatter
    if readme_content:
        content += readme_content + "\n"
    elif metadata.get("abstract"):
        content += metadata["abstract"] + "\n"
    return content
```

Then refactor `generate_project_content` so its primary-page build delegates to `render_project_page`. Replace the block that computes `frontmatter`, builds `content`, and chooses the path, keeping the write, the section-stub loop, and the dry-run preview intact:

```python
def generate_project_content(
    slug: str,
    metadata: dict[str, Any],
    dry_run: bool = False,
) -> bool:
    """Generate Hugo content for a single project (render primary page + write + stubs)."""
    paths = get_paths()
    github_data = metadata.get("github_data", {})

    is_rich = metadata.get("rich_project", False)
    content_sections = metadata.get("content_sections", [])

    content = render_project_page(slug, metadata)

    if is_rich:
        content_path = paths.projects / slug / "_index.md"
    else:
        content_path = paths.projects / slug / "index.md"

    if dry_run:
        console.print(f"  [dim]Would write: {content_path}[/dim]")
        if is_rich and content_sections:
            for section in content_sections:
                section_path = paths.projects / slug / section / "_index.md"
                console.print(f"  [dim]Would write: {section_path}[/dim]")
        return True

    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_text(content, encoding="utf-8")
    console.print(f"  [green]✓[/green] Generated: {content_path}")

    if is_rich and content_sections:
        project_title = metadata.get("title", github_data.get("name", slug))
        for section in content_sections:
            section_path = paths.projects / slug / section / "_index.md"
            if not section_path.exists():
                section_path.parent.mkdir(parents=True, exist_ok=True)
                section_content = generate_section_frontmatter(section, project_title)
                section_path.write_text(section_content, encoding="utf-8")
                console.print(f"  [green]✓[/green] Generated section: {section_path}")
            else:
                console.print(f"  [dim]Section exists (skipped): {section_path}[/dim]")

    return True
```

- [ ] **Step 4: Add `ProjectsRenderer` to `src/mf/projects/generator.py`**

Append at the end of the file. `hugo_path` resolves `_index.md` vs `index.md` from the rich flag; hidden projects are excluded from `iter_slugs` (they are deleted by the write path, not rendered):

```python
class ProjectsRenderer:
    """Renderer binding for the render-drift engine.

    Slugs come from the GitHub cache, minus hidden projects. The primary page
    is _index.md for rich projects and index.md otherwise.
    """

    section = "projects"

    def __init__(self, cache: ProjectsCache, db: ProjectsDatabase, paths) -> None:
        self._cache = cache
        self._db = db
        self._paths = paths

    def _is_rich(self, slug: str) -> bool:
        overrides = self._db.get(slug) or {}
        return bool(overrides.get("rich_project", False))

    def _is_hidden(self, slug: str) -> bool:
        overrides = self._db.get(slug) or {}
        return bool(overrides.get("hide", False))

    def iter_slugs(self):
        return [slug for slug in self._cache if not self._is_hidden(slug)]

    def existing_slugs(self):
        d = self._paths.projects
        if not d.exists():
            return []
        out = []
        for p in d.iterdir():
            if (p / "_index.md").exists() or (p / "index.md").exists():
                out.append(p.name)
        return out

    def hugo_path(self, slug: str):
        name = "_index.md" if self._is_rich(slug) else "index.md"
        return self._paths.projects / slug / name

    def render_page(self, slug: str) -> str | None:
        github_data = self._cache.get(slug)
        if not github_data:
            return None
        overrides = self._db.get(slug) or {}
        merged = merge_project_data(slug, github_data, overrides)
        return render_project_page(slug, merged)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_projects/test_drift.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Add `mf projects diff` and route `generate --dry-run` in `src/mf/projects/commands.py`**

Add the diff command (place after the `generate` command at line 495; group is `projects`, dry-run helper is `_get_dry_run` at line 14-15):

```python
@projects.command(name="diff")
@click.argument("slug", required=False)
@click.option("--full", is_flag=True, help="Show a unified diff for each drifted page")
def diff(slug: str | None, full: bool) -> None:
    """Show what `mf projects generate` would change (read-only).

    \b
    Examples:
        mf projects diff
        mf projects diff my-project
        mf projects diff --full
    """
    from mf.core.config import get_paths
    from mf.core.database import ProjectsCache, ProjectsDatabase
    from mf.core.drift import run_diff_command
    from mf.projects.generator import ProjectsRenderer

    cache = ProjectsCache()
    cache.load()
    db = ProjectsDatabase()
    db.load()
    renderer = ProjectsRenderer(cache, db, get_paths())
    run_diff_command(renderer, console=console, slug=slug, full=full)
```

Then add a dry-run branch at the top of the existing `generate` command body (right after `dry_run = _get_dry_run(ctx)` is computed; the command currently loads cache+db and calls the generator). Insert:

```python
    if dry_run:
        from mf.core.config import get_paths
        from mf.core.drift import print_dry_run_preview
        from mf.projects.generator import ProjectsRenderer

        cache = ProjectsCache()
        cache.load()
        db = ProjectsDatabase()
        db.load()
        renderer = ProjectsRenderer(cache, db, get_paths())
        print_dry_run_preview(renderer, console=console, only_slug=slug)
        return
```

Make sure this block is placed before the existing non-dry-run generation logic runs, and that `ProjectsCache`/`ProjectsDatabase` remain imported in the non-dry-run path as they already are. If `console` is not already module-level in `projects/commands.py`, import it the same way the other commands in that file do.

- [ ] **Step 7: Add CLI tests**

Append to `tests/test_projects/test_drift.py`:

```python
def test_projects_diff_cli_reports_missing(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _seed(mock_site_root, "proj")
    result = CliRunner().invoke(main, ["projects", "diff"])
    assert result.exit_code == 0
    assert "missing" in result.output


def test_projects_generate_dry_run_says_would_create(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _seed(mock_site_root, "proj")
    result = CliRunner().invoke(main, ["--dry-run", "projects", "generate"])
    assert result.exit_code == 0
    assert "would create" in result.output
```

- [ ] **Step 8: Run the full projects suite to confirm no regressions**

Run: `pytest tests/test_projects/ -v`
Expected: PASS (new drift tests plus existing projects tests; update any existing test that asserted a `datetime.now()`-derived date in generated output).

- [ ] **Step 9: Commit**

```bash
git add src/mf/projects/generator.py src/mf/projects/commands.py tests/test_projects/test_drift.py
git commit -m "feat(projects): deterministic primary-page render split, add diff and dry-run"
```

---

## Task 7: Full-suite verification and docs

**Files:**
- Modify: `CLAUDE.md` (document the new `diff` surface and the render/write split convention)

- [ ] **Step 1: Run the entire test suite**

Run: `pytest`
Expected: PASS. Investigate and fix any test that depended on the old non-deterministic dates or the pre-split generator signatures.

- [ ] **Step 2: Lint and type-check the new and changed code**

Run: `ruff check src/mf && mypy src/mf/core/drift.py src/mf/core/frontmatter.py`
Expected: clean (fix import ordering or annotations as reported).

- [ ] **Step 3: Smoke-test the CLI surface against the real site**

Run:
```bash
mf pubs diff
mf packages diff
mf papers diff
mf projects diff
mf --dry-run packages generate
```
Expected: each prints a drift table or "all pages current"; `--dry-run generate` prints `would create|update|skip` lines and writes nothing.

- [ ] **Step 4: Document the new surface in `CLAUDE.md`**

Under the "Read-only audit pattern" subsection, add `mf <module> diff` to the list of read-only diagnostics, and under "Key Patterns" add a one-paragraph note that projection generators are split into a pure `render_*_page` and a write path, with the shared engine in `core/drift.py`. Do not use em-dashes (the soul-voice hook scans the whole file). Prefer a full `Write` rewrite of any paragraph that already contains legacy em-dashes.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): document render-drift diff surface and render/write split"
```

---

## Self-Review (completed during authoring)

- **Spec coverage:** core/frontmatter lift (Task 1), core/drift engine with Renderer + RenderFinding + check_render_drift + semantic comparison (Task 2), four projection modules wired with render/write split + diff + enriched dry-run (Tasks 3-6), determinism handled per module (Tasks 4-6), tests for current/stale/missing/orphan + determinism + semantic equality + CLI (every module task), CLAUDE.md docs (Task 7). All spec sections map to a task.
- **Non-goals respected:** no ownership tiers for projection modules; no persisted hash state; section stubs / branch extras / hide-delete left in the write path and excluded from drift; series posts untouched; no `mf status` rollup; no audit/integrity migration.
- **Type/name consistency:** `Renderer` methods (`iter_slugs`, `existing_slugs`, `hugo_path`, `render_page`, `section`) used identically across all four module Renderers and the engine; `RenderFinding(slug, status, detail)` consistent; helper names (`check_render_drift`, `print_drift_report`, `print_render_diff`, `print_dry_run_preview`, `run_diff_command`) consistent between definition (Task 2) and call sites (Tasks 3-6).
- **Determinism refinement** versus the spec's uniform pinning is called out at the top and localized to papers (Task 5).

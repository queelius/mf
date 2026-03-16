# Paper Build Decoupling Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all build logic (tex2any, pdflatex) from the `mf papers` module, replacing it with an `ingest` command that copies pre-built artifacts and a `status` command that reports staleness without auto-rebuilding.

**Architecture:** Gut `processor.py` of build functions, keeping backup/copy/restore infrastructure and adding `resolve_artifact_paths()` + `ingest_paper()`. Strip `sync.py` to status-only (delete all rebuild machinery). Remove tex2any-specific parsing from `metadata.py`. Rewire CLI commands: `process` → `ingest`, `sync` → `status`.

**Tech Stack:** Python, Click (CLI), Rich (output), pytest (testing). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-16-paper-build-decoupling-design.md`

---

## Chunk 1: Schema and artifact resolution

### Task 1: Add `html_dir` and `pdf_file_source` properties to PaperEntry

**Files:**
- Modify: `src/mf/core/database.py:97` (after `source_format` property)
- Modify: `src/mf/papers/field_ops.py:80-83` (update `source_format` choices, add new fields)

- [ ] **Step 1: Write failing tests for new PaperEntry properties**

Add to `tests/test_papers/test_processor.py` (we'll restructure imports in Task 3):

```python
# tests/test_papers/test_resolve.py (new file)
"""Tests for artifact path resolution."""

from pathlib import Path

import pytest

from mf.core.database import PaperEntry


class TestPaperEntryArtifactProperties:
    """Tests for html_dir and pdf_file_source properties on PaperEntry."""

    def test_html_dir_returns_value(self):
        entry = PaperEntry(slug="test", data={"html_dir": "custom_html"})
        assert entry.html_dir == "custom_html"

    def test_html_dir_returns_none_when_absent(self):
        entry = PaperEntry(slug="test", data={})
        assert entry.html_dir is None

    def test_pdf_file_source_returns_value(self):
        entry = PaperEntry(slug="test", data={"pdf_file_source": "output.pdf"})
        assert entry.pdf_file_source == "output.pdf"

    def test_pdf_file_source_returns_none_when_absent(self):
        entry = PaperEntry(slug="test", data={})
        assert entry.pdf_file_source is None

    def test_source_format_accepts_pdf(self):
        entry = PaperEntry(slug="test", data={"source_format": "pdf"})
        assert entry.source_format == "pdf"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_papers/test_resolve.py -v`
Expected: FAIL — `AttributeError: 'PaperEntry' object has no attribute 'html_dir'`

- [ ] **Step 3: Implement properties and schema changes**

In `src/mf/core/database.py`, after the `source_format` property (line 97), add:

```python
@property
def html_dir(self) -> str | None:
    """Get source HTML directory override."""
    return self.data.get("html_dir")

@property
def pdf_file_source(self) -> str | None:
    """Get source PDF file override."""
    return self.data.get("pdf_file_source")
```

In `src/mf/papers/field_ops.py`, change `source_format` choices (line 83):
```python
choices=["tex", "pdf", "pregenerated"],
```

Add after the `source_format` entry (after line 84):
```python
"html_dir": FieldDef(
    FieldType.STRING,
    "Source HTML directory override (relative to source_path parent)",
),
"pdf_file_source": FieldDef(
    FieldType.STRING,
    "Source PDF file override (relative to source_path parent)",
),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_papers/test_resolve.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/mf/core/database.py src/mf/papers/field_ops.py tests/test_papers/test_resolve.py
git commit -m "feat(papers): add html_dir, pdf_file_source properties and update source_format choices"
```

---

### Task 2: Implement `resolve_artifact_paths()`

**Files:**
- Modify: `src/mf/papers/processor.py` (add `ArtifactPaths` dataclass and `resolve_artifact_paths()`)
- Test: `tests/test_papers/test_resolve.py` (add resolution tests)

- [ ] **Step 1: Write failing tests for resolve_artifact_paths**

Append to `tests/test_papers/test_resolve.py`:

```python
from mf.papers.processor import ArtifactPaths, resolve_artifact_paths


class TestResolveArtifactPaths:
    """Tests for convention-based artifact path resolution."""

    def test_tex_defaults(self, tmp_path):
        """tex format: html_paper/ dir and {stem}.pdf."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        # Create the expected default artifacts
        html_dir = tmp_path / "html_paper"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html/>")
        pdf_file = tmp_path / "paper.pdf"
        pdf_file.write_text("fake pdf")

        entry = PaperEntry(slug="test", data={"source_path": str(tex_file)})
        result = resolve_artifact_paths(entry)

        assert result.html_dir == html_dir
        assert result.pdf_path == pdf_file

    def test_tex_html_missing(self, tmp_path):
        """tex format: no html_paper/ dir returns None for html_dir."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        pdf_file = tmp_path / "paper.pdf"
        pdf_file.write_text("fake pdf")

        entry = PaperEntry(slug="test", data={"source_path": str(tex_file)})
        result = resolve_artifact_paths(entry)

        assert result.html_dir is None
        assert result.pdf_path == pdf_file

    def test_tex_pdf_missing(self, tmp_path):
        """tex format: no {stem}.pdf returns None for pdf_path."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        html_dir = tmp_path / "html_paper"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html/>")

        entry = PaperEntry(slug="test", data={"source_path": str(tex_file)})
        result = resolve_artifact_paths(entry)

        assert result.html_dir == html_dir
        assert result.pdf_path is None

    def test_tex_custom_stem(self, tmp_path):
        """tex format uses actual stem, not hardcoded 'paper'."""
        tex_file = tmp_path / "cipher_maps.tex"
        tex_file.write_text(r"\documentclass{article}")
        pdf_file = tmp_path / "cipher_maps.pdf"
        pdf_file.write_text("fake pdf")

        entry = PaperEntry(slug="cipher-maps", data={"source_path": str(tex_file)})
        result = resolve_artifact_paths(entry)

        assert result.pdf_path == pdf_file
        # html_paper/ doesn't exist, so None
        assert result.html_dir is None

    def test_pdf_format(self, tmp_path):
        """pdf format: source IS the PDF, no HTML."""
        pdf_file = tmp_path / "paper.pdf"
        pdf_file.write_text("fake pdf")

        entry = PaperEntry(slug="test", data={
            "source_path": str(pdf_file),
            "source_format": "pdf",
        })
        result = resolve_artifact_paths(entry)

        assert result.html_dir is None
        assert result.pdf_path == pdf_file

    def test_pregenerated_format(self, tmp_path):
        """pregenerated format: source parent is HTML dir, glob for PDF."""
        html_dir = tmp_path / "output"
        html_dir.mkdir()
        index = html_dir / "index.html"
        index.write_text("<html/>")
        pdf_file = html_dir / "paper.pdf"
        pdf_file.write_text("fake pdf")

        entry = PaperEntry(slug="test", data={
            "source_path": str(index),
            "source_format": "pregenerated",
        })
        result = resolve_artifact_paths(entry)

        assert result.html_dir == html_dir
        assert result.pdf_path == pdf_file

    def test_pregenerated_no_pdf(self, tmp_path):
        """pregenerated format: no PDF in dir returns None for pdf_path."""
        html_dir = tmp_path / "output"
        html_dir.mkdir()
        index = html_dir / "index.html"
        index.write_text("<html/>")

        entry = PaperEntry(slug="test", data={
            "source_path": str(index),
            "source_format": "pregenerated",
        })
        result = resolve_artifact_paths(entry)

        assert result.html_dir == html_dir
        assert result.pdf_path is None

    def test_override_html_dir(self, tmp_path):
        """html_dir override takes precedence over convention."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        custom_html = tmp_path / "my_html"
        custom_html.mkdir()
        (custom_html / "index.html").write_text("<html/>")

        entry = PaperEntry(slug="test", data={
            "source_path": str(tex_file),
            "html_dir": "my_html",
        })
        result = resolve_artifact_paths(entry)

        assert result.html_dir == custom_html

    def test_override_pdf_file_source(self, tmp_path):
        """pdf_file_source override takes precedence over convention."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        custom_pdf = tmp_path / "build" / "output.pdf"
        custom_pdf.parent.mkdir()
        custom_pdf.write_text("fake pdf")

        entry = PaperEntry(slug="test", data={
            "source_path": str(tex_file),
            "pdf_file_source": "build/output.pdf",
        })
        result = resolve_artifact_paths(entry)

        assert result.pdf_path == custom_pdf

    def test_no_source_path_returns_empty(self):
        """Entry with no source_path returns empty ArtifactPaths."""
        entry = PaperEntry(slug="test", data={})
        result = resolve_artifact_paths(entry)

        assert result.html_dir is None
        assert result.pdf_path is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_papers/test_resolve.py::TestResolveArtifactPaths -v`
Expected: FAIL — `ImportError: cannot import name 'ArtifactPaths' from 'mf.papers.processor'`

- [ ] **Step 3: Implement ArtifactPaths and resolve_artifact_paths**

Add to `src/mf/papers/processor.py` (after the imports, before `backup_existing_paper`):

```python
from dataclasses import dataclass


@dataclass
class ArtifactPaths:
    """Resolved artifact locations for a paper."""

    html_dir: Path | None = None
    pdf_path: Path | None = None


def resolve_artifact_paths(entry: "PaperEntry") -> ArtifactPaths:
    """Resolve artifact locations from source_path + format + overrides.

    Convention for tex format:
    - HTML: html_paper/ in same directory as .tex file
    - PDF: {stem}.pdf in same directory as .tex file

    Convention for pdf format:
    - HTML: none
    - PDF: the source file itself

    Convention for pregenerated format:
    - HTML: parent directory of source file
    - PDF: first *.pdf found in that directory

    Override fields (html_dir, pdf_file_source) in the DB entry take
    precedence, resolved relative to source_path's parent directory.

    Returns absolute paths. Returns None for artifacts that don't exist.
    """
    source_path = entry.source_path
    if not source_path:
        return ArtifactPaths()

    parent = source_path.parent
    fmt = entry.source_format

    # Resolve HTML directory
    html_dir: Path | None = None
    if entry.html_dir:
        candidate = parent / entry.html_dir
        if candidate.is_dir() and (candidate / "index.html").exists():
            html_dir = candidate
    elif fmt == "tex":
        candidate = parent / "html_paper"
        if candidate.is_dir() and (candidate / "index.html").exists():
            html_dir = candidate
    elif fmt == "pregenerated":
        html_dir = parent

    # Resolve PDF path
    pdf_path: Path | None = None
    if entry.pdf_file_source:
        candidate = parent / entry.pdf_file_source
        if candidate.exists():
            pdf_path = candidate
    elif fmt == "tex":
        candidate = parent / f"{source_path.stem}.pdf"
        if candidate.exists():
            pdf_path = candidate
    elif fmt == "pdf":
        if source_path.exists():
            pdf_path = source_path
    elif fmt == "pregenerated":
        pdfs = list(parent.glob("*.pdf"))
        if pdfs:
            pdf_path = pdfs[0]

    return ArtifactPaths(html_dir=html_dir, pdf_path=pdf_path)
```

Note: Add `from dataclasses import dataclass` to the imports at the top of the file (alongside existing imports). `PaperEntry` is NOT imported in processor.py — use the string annotation `"PaperEntry"` in the function signature for the type hint only. The actual attribute access (`entry.source_path`, etc.) works at runtime without the import.

Also update these docstrings/comments:
- `PaperEntry.source_format` docstring in `database.py` (line 96): change `(tex, docx, pregenerated)` to `(tex, pdf, pregenerated)`
- `PaperDatabase.DEFAULT_META._example` comment in `database.py` (line 240): change `# tex (default), docx, pregenerated` to `# tex (default), pdf, pregenerated`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_papers/test_resolve.py -v`
Expected: PASS (all 16 tests)

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest --tb=short`
Expected: All tests pass (no regressions — we only added code)

- [ ] **Step 6: Commit**

```bash
git add src/mf/papers/processor.py tests/test_papers/test_resolve.py
git commit -m "feat(papers): add ArtifactPaths and resolve_artifact_paths"
```

---

## Chunk 2: ingest_paper and CLI

### Task 3: Implement `ingest_paper()` function

**Files:**
- Modify: `src/mf/papers/processor.py` (add `ingest_paper()`, keep `copy_to_static`, `backup_existing_paper`, `restore_backup`)
- Test: `tests/test_papers/test_resolve.py` (add ingest tests)

- [ ] **Step 1: Write failing tests for ingest_paper**

Append to `tests/test_papers/test_resolve.py`:

```python
from mf.papers.processor import ingest_paper


class TestIngestPaper:
    """Tests for ingest_paper orchestration."""

    def _make_tex_paper(self, tmp_path, mock_site_root):
        """Create a tex paper with built artifacts."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        html_dir = tmp_path / "html_paper"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html>paper</html>")
        pdf_file = tmp_path / "paper.pdf"
        pdf_file.write_text("fake pdf content")

        from mf.core.database import PaperDatabase
        db = PaperDatabase()
        db.load()
        db.set("test-paper", {
            "title": "Test Paper",
            "source_path": str(tex_file),
        })
        db.save()
        return tex_file

    def test_ingest_copies_artifacts(self, tmp_path, mock_site_root):
        """Ingest copies HTML and PDF to /static/latex/{slug}/."""
        self._make_tex_paper(tmp_path, mock_site_root)

        result = ingest_paper("test-paper")

        assert result is True
        target = mock_site_root / "static" / "latex" / "test-paper"
        assert (target / "index.html").exists()
        assert (target / "paper.pdf").exists()

    def test_ingest_updates_source_hash(self, tmp_path, mock_site_root):
        """Ingest updates source_hash in DB."""
        self._make_tex_paper(tmp_path, mock_site_root)

        ingest_paper("test-paper")

        from mf.core.database import PaperDatabase
        db = PaperDatabase()
        db.load()
        entry = db.get("test-paper")
        assert entry.source_hash is not None
        assert entry.last_generated is not None

    def test_ingest_skips_unchanged(self, tmp_path, mock_site_root):
        """Ingest skips when source hash unchanged (unless --force)."""
        self._make_tex_paper(tmp_path, mock_site_root)

        # First ingest sets the hash
        ingest_paper("test-paper")
        # Second ingest should skip (return True, no error)
        result = ingest_paper("test-paper")
        assert result is True

    def test_ingest_force_overrides_hash_check(self, tmp_path, mock_site_root):
        """Ingest with force=True always copies."""
        self._make_tex_paper(tmp_path, mock_site_root)

        ingest_paper("test-paper")
        result = ingest_paper("test-paper", force=True)
        assert result is True

    def test_ingest_not_found(self, mock_site_root):
        """Ingest returns False for nonexistent slug."""
        result = ingest_paper("nonexistent")
        assert result is False

    def test_ingest_no_source_path(self, mock_site_root):
        """Ingest returns False when entry has no source_path."""
        from mf.core.database import PaperDatabase
        db = PaperDatabase()
        db.load()
        db.set("no-source", {"title": "No Source"})
        db.save()

        result = ingest_paper("no-source")
        assert result is False

    def test_ingest_source_file_missing(self, mock_site_root):
        """Ingest returns False when source file doesn't exist on disk."""
        from mf.core.database import PaperDatabase
        db = PaperDatabase()
        db.load()
        db.set("bad-path", {
            "title": "Bad Path",
            "source_path": "/nonexistent/paper.tex",
        })
        db.save()

        result = ingest_paper("bad-path")
        assert result is False

    def test_ingest_no_artifacts(self, tmp_path, mock_site_root):
        """Ingest returns False when no artifacts found."""
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        # No HTML dir, no PDF

        from mf.core.database import PaperDatabase
        db = PaperDatabase()
        db.load()
        db.set("empty", {
            "title": "Empty",
            "source_path": str(tex_file),
        })
        db.save()

        result = ingest_paper("empty")
        assert result is False

    def test_ingest_dry_run(self, tmp_path, mock_site_root):
        """Dry run doesn't copy or update DB."""
        self._make_tex_paper(tmp_path, mock_site_root)

        result = ingest_paper("test-paper", dry_run=True)

        assert result is True
        target = mock_site_root / "static" / "latex" / "test-paper"
        assert not target.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_papers/test_resolve.py::TestIngestPaper -v`
Expected: FAIL — `ImportError: cannot import name 'ingest_paper'`

- [ ] **Step 3: Implement ingest_paper**

Add to `src/mf/papers/processor.py` (after `resolve_artifact_paths`):

```python
def ingest_paper(
    slug: str,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    """Ingest pre-built artifacts for a paper into Hugo static directory.

    Requires the paper to already exist in paper_db.json with a source_path.
    Copies HTML directory and/or PDF to /static/latex/{slug}/.

    Args:
        slug: Paper slug (must exist in DB)
        force: Copy even if source hash unchanged
        dry_run: Preview only

    Returns:
        True if successful (or skipped because unchanged)
    """
    db = PaperDatabase()
    db.load()

    entry = db.get(slug)
    if not entry:
        console.print(f"[red]Paper not found: {slug}[/red]")
        return False

    source_path = entry.source_path
    if not source_path:
        console.print(f"[red]No source_path set for {slug}[/red]")
        return False

    if not source_path.exists():
        console.print(f"[red]Source file missing: {source_path}[/red]")
        return False

    # Resolve artifact locations
    artifacts = resolve_artifact_paths(entry)
    if not artifacts.html_dir and not artifacts.pdf_path:
        console.print(f"[red]No artifacts found for {slug}[/red]")
        console.print(f"  Looked for HTML in: {source_path.parent / 'html_paper'}")
        console.print(f"  Looked for PDF: {source_path.parent / (source_path.stem + '.pdf')}")
        return False

    # Check staleness
    source_hash = compute_file_hash(source_path)
    if not force and entry.source_hash == source_hash:
        console.print(f"[green]{slug} is up to date[/green]")
        return True

    console.print(f"[cyan]Ingesting {slug}...[/cyan]")

    backup_path = None
    try:
        # Backup existing
        backup_path = backup_existing_paper(slug, dry_run)

        # Copy HTML directory
        if artifacts.html_dir:
            if not copy_to_static(artifacts.html_dir, slug, dry_run):
                if backup_path:
                    restore_backup(backup_path, slug, dry_run)
                return False

        # Copy PDF (may be in a different location than HTML)
        if artifacts.pdf_path:
            if not dry_run:
                paths = get_paths()
                target_dir = paths.latex / slug
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(artifacts.pdf_path, target_dir / artifacts.pdf_path.name)

        # Update database
        if not dry_run:
            entry.set_source_tracking(source_path, source_hash)
            db.save()

            # Generate Hugo content
            from mf.papers.generator import generate_paper_content
            generate_paper_content(slug, db)

        console.print(f"[green]Successfully ingested: {slug}[/green]")
        return True

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if backup_path and backup_path.exists():
            restore_backup(backup_path, slug, dry_run)
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_papers/test_resolve.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/mf/papers/processor.py tests/test_papers/test_resolve.py
git commit -m "feat(papers): add ingest_paper function"
```

---

### Task 4: Rewire CLI commands (`process` → `ingest`, `sync` → `status`)

**Files:**
- Modify: `src/mf/papers/commands.py:32-78` (replace `process` and `sync` commands)
- Modify: `src/mf/papers/sync.py` (add `paper_status()` function wrapping check+print)

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_papers/test_ingest_command.py`:

```python
"""Tests for ingest and status CLI commands."""

from unittest.mock import patch

from click.testing import CliRunner

from mf.papers.commands import papers


class TestIngestCommand:
    """Tests for mf papers ingest CLI."""

    @patch("mf.papers.processor.ingest_paper")
    def test_ingest_calls_ingest_paper(self, mock_ingest, mock_site_root):
        mock_ingest.return_value = True
        runner = CliRunner()
        result = runner.invoke(papers, ["ingest", "my-paper"])

        assert result.exit_code == 0
        mock_ingest.assert_called_once_with("my-paper", force=False, dry_run=False)

    @patch("mf.papers.processor.ingest_paper")
    def test_ingest_with_force(self, mock_ingest, mock_site_root):
        mock_ingest.return_value = True
        runner = CliRunner()
        result = runner.invoke(papers, ["ingest", "my-paper", "--force"])

        assert result.exit_code == 0
        mock_ingest.assert_called_once_with("my-paper", force=True, dry_run=False)

    def test_ingest_requires_slug(self, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(papers, ["ingest"])
        assert result.exit_code != 0


class TestStatusCommand:
    """Tests for mf papers status CLI."""

    @patch("mf.papers.sync.paper_status")
    def test_status_calls_paper_status(self, mock_status, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(papers, ["status"])

        assert result.exit_code == 0
        mock_status.assert_called_once_with(slug=None)

    @patch("mf.papers.sync.paper_status")
    def test_status_with_slug(self, mock_status, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(papers, ["status", "--slug", "my-paper"])

        assert result.exit_code == 0
        mock_status.assert_called_once_with(slug="my-paper")


class TestPaperStatusFunction:
    """Integration tests for paper_status function."""

    def test_paper_status_not_found(self, mock_site_root, capsys):
        from mf.papers.sync import paper_status
        paper_status(slug="nonexistent")
        # Should not raise; output contains error

    def test_paper_status_up_to_date(self, tmp_path, mock_site_root):
        from mf.core.database import PaperDatabase
        from mf.core.crypto import compute_file_hash
        from mf.papers.sync import paper_status

        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\documentclass{article}")
        h = compute_file_hash(tex_file)

        db = PaperDatabase()
        db.load()
        db.set("up-paper", {
            "title": "Up",
            "source_path": str(tex_file),
            "source_hash": h,
        })
        db.save()

        # Should not raise
        paper_status(slug="up-paper")

    def test_paper_status_all(self, mock_site_root):
        from mf.papers.sync import paper_status
        # Should not raise with no papers
        paper_status(slug=None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_papers/test_ingest_command.py -v`
Expected: FAIL — no `ingest` command, no `paper_status` function

- [ ] **Step 3: Replace process and sync commands in commands.py**

Replace `process` command (lines 32-45) with:

```python
@papers.command()
@click.argument("slug")
@click.option("--force", is_flag=True, help="Ingest even if source unchanged")
@click.pass_obj
def ingest(ctx, slug: str, force: bool) -> None:
    """Ingest pre-built paper artifacts into Hugo site.

    SLUG is the paper slug (must exist in paper_db.json).
    Build the paper first with 'make html pdf' in the paper's repo.
    """
    from mf.papers.processor import ingest_paper

    dry_run = ctx.dry_run if ctx else False
    ingest_paper(slug, force=force, dry_run=dry_run)
```

Replace `sync` command (lines 48-78) with:

```python
@papers.command()
@click.option("--slug", help="Check only a specific paper")
@click.pass_obj
def status(ctx, slug: str | None) -> None:
    """Check paper staleness status.

    Reports which papers have changed source files without
    being re-ingested. Does not modify any files.
    """
    from mf.papers.sync import paper_status

    paper_status(slug=slug)
```

- [ ] **Step 4: Add `paper_status()` to sync.py**

Add to `src/mf/papers/sync.py` (after `print_sync_status`, replacing `sync_papers`):

```python
def paper_status(slug: str | None = None) -> None:
    """Report paper staleness status.

    Args:
        slug: If provided, check only this paper
    """
    db = PaperDatabase()
    db.load()

    if slug:
        entry = db.get(slug)
        if not entry:
            console.print(f"[red]Paper not found: {slug}[/red]")
            return

        result, source_path = check_paper_staleness(entry)
        if result == "missing":
            console.print(f"[red]Source file missing: {entry.source_path}[/red]")
        elif result == "skipped":
            console.print(f"[yellow]{slug}: skipped (no trackable source)[/yellow]")
        elif result == "up_to_date":
            console.print(f"[green]{slug}: up to date[/green]")
        elif result in ("stale", "no_hash"):
            console.print(f"[yellow]{slug}: stale ({result})[/yellow]")
        return

    console.print(f"Checking {len(db)} papers for changes...")
    status = check_all_papers(db)
    print_sync_status(status)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_papers/test_ingest_command.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run full test suite**

Run: `pytest --tb=short`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/mf/papers/commands.py src/mf/papers/sync.py tests/test_papers/test_ingest_command.py
git commit -m "feat(papers): replace process/sync CLI with ingest/status"
```

---

## Chunk 3: Deletions and cleanup

### Task 5: Delete build functions from processor.py

**Files:**
- Modify: `src/mf/papers/processor.py` (delete `find_tex_files`, `run_command`, `generate_html`, `generate_pdf`, `process_paper`)
- Modify: `tests/test_papers/test_processor.py` (delete build tests, update imports)

- [ ] **Step 1: Delete build functions from processor.py**

Remove these functions from `src/mf/papers/processor.py`:
- `find_tex_files()` (lines 24-41)
- `run_command()` (lines 44-77)
- `generate_html()` (lines 80-94)
- `generate_pdf()` (lines 97-152)
- `process_paper()` (lines 219-366)

Also remove the now-unused imports:
- `subprocess` (only used by `run_command`)
- `tempfile` (only used by `process_paper`)
- `from mf.core.prompts import confirm, prompt_user, select_from_list` (only used by `process_paper`)

Keep: `shutil`, `Path`, `Console`, `get_paths`, `compute_file_hash`, `PaperDatabase`, `copy_to_static`, `backup_existing_paper`, `restore_backup`, `ArtifactPaths`, `resolve_artifact_paths`, `ingest_paper`.

Update the module docstring:
```python
"""
Paper artifact ingestion.

Copies pre-built HTML/PDF from paper repos into the Hugo static directory.
"""
```

- [ ] **Step 2: Update test_processor.py**

Remove all tests for deleted functions (lines 1-195 of `test_processor.py`). Keep the backup/copy/restore tests (lines 197-305). Update the imports:

```python
"""Tests for mf.papers.processor module (artifact ingestion)."""

import shutil
from pathlib import Path

import pytest

from mf.papers.processor import (
    backup_existing_paper,
    copy_to_static,
    restore_backup,
)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_papers/test_processor.py -v`
Expected: PASS (only backup/copy/restore tests remain, ~7 tests)

- [ ] **Step 4: Run full test suite**

Run: `pytest --tb=short`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/mf/papers/processor.py tests/test_papers/test_processor.py
git commit -m "refactor(papers): remove build functions from processor"
```

---

### Task 6: Delete rebuild machinery from sync.py

**Files:**
- Modify: `src/mf/papers/sync.py` (delete `sync_papers`, parallel/sequential processing, `SyncResults`, `ProcessingResult`)
- Modify: `tests/test_papers/test_sync.py` (delete rebuild tests, update imports)

- [ ] **Step 1: Delete rebuild code from sync.py**

Remove these from `src/mf/papers/sync.py`:
- `SyncResults` dataclass and `ProcessingResult` dataclass (lines 39-77)
- `sync_papers()` (lines 182-263)
- `_process_papers_sequential()` (lines 265-293)
- `_process_papers_parallel()` (lines 296-379)
- `_process_single_paper_with_timeout()` (lines 382-472)
- `process_stale_paper()` (lines 475-497)

Remove unused imports:
- `from concurrent.futures import ThreadPoolExecutor, as_completed`
- `from concurrent.futures import TimeoutError as FuturesTimeoutError`
- `from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn`
- `from mf.core.prompts import confirm`

Update the module docstring:
```python
"""
Paper staleness detection.

Check if source files have changed since last ingestion.
"""
```

- [ ] **Step 2: Update test_sync.py**

Remove tests for deleted classes/functions (lines 25-58: `SyncResults`, `ProcessingResult` tests). Update imports:

```python
from mf.papers.sync import (
    SyncStatus,
    check_paper_staleness,
    check_all_papers,
    print_sync_status,
)
```

- [ ] **Step 3: Leave `test_staleness_non_tex_format` unchanged**

This test asserts `status == "skipped_non_tex"` with `source_format: "docx"`. The tex-only guard is still present at this point, so the test still passes. It will be deleted and replaced in Task 7.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_papers/test_sync.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/mf/papers/sync.py tests/test_papers/test_sync.py
git commit -m "refactor(papers): remove rebuild machinery from sync"
```

---

### Task 7: Remove tex-only guard from `check_paper_staleness` and tex2any parsing from metadata.py

**Files:**
- Modify: `src/mf/papers/sync.py:94-97` (remove `source_format != "tex"` guard)
- Modify: `src/mf/papers/metadata.py:71,89-100` (remove tex2any-footer-config parsing)
- Modify: `tests/test_papers/test_sync.py` (update `test_staleness_non_tex_format`)

- [ ] **Step 1: Replace `test_staleness_non_tex_format` with new test**

Delete `test_staleness_non_tex_format` from `tests/test_papers/test_sync.py` and add:

```python
def test_staleness_pdf_format_checks_hash(tmp_path):
    """Test that pdf format papers are hash-checked (not skipped)."""
    pdf_file = tmp_path / "paper.pdf"
    pdf_file.write_text("fake pdf")
    entry = PaperEntry(slug="pdf-paper", data={
        "source_path": str(pdf_file),
        "source_format": "pdf",
    })
    status, path = check_paper_staleness(entry)
    # Should be "no_hash" (stale) since no hash stored, NOT "skipped_non_tex"
    assert status == "no_hash"
    assert path == pdf_file
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_papers/test_sync.py::test_staleness_pdf_format_checks_hash -v`
Expected: FAIL — returns `"skipped_non_tex"` instead of `"no_hash"`

- [ ] **Step 3: Remove tex-only guard from check_paper_staleness**

In `src/mf/papers/sync.py`, remove lines 95-97:
```python
    # DELETE THESE LINES:
    if entry.source_format != "tex":
        return ("skipped_non_tex", entry.source_path)
```

Also remove the `"skipped_non_tex"` handling from `check_all_papers` (line 143-144):
```python
    # DELETE THESE LINES:
    elif result == "skipped_non_tex":
        status.skipped.append((entry, f"non-tex format ({entry.source_format})"))
```

Update `check_paper_staleness` docstring to remove `"skipped_non_tex"` from the documented return values.

- [ ] **Step 4: Remove tex2any-footer-config from metadata.py**

In `src/mf/papers/metadata.py`:

Remove the `tex2any_config` field from `__init__` (line 71):
```python
        # DELETE: self.tex2any_config: dict | None = None
```

Remove the tex2any-footer-config parsing block (lines 89-100):
```python
        # DELETE THIS BLOCK:
            # tex2any footer config (contains author, year, etc.)
            if name == "tex2any-footer-config" and content:
                try:
                    self.tex2any_config = json.loads(content)
                    if "author" in self.tex2any_config:
                        author = self.tex2any_config["author"]
                        if isinstance(author, list):
                            self.authors = author
                        elif isinstance(author, str):
                            self.authors = [a.strip() for a in author.split(",")]
                except json.JSONDecodeError:
                    pass
```

Also remove the now-unused `json` import from metadata.py (line 9) — check if json is used elsewhere in the file first.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_papers/ -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest --tb=short`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/mf/papers/sync.py src/mf/papers/metadata.py tests/test_papers/test_sync.py
git commit -m "refactor(papers): remove tex-only guard and tex2any parsing"
```

---

### Task 8: Update documentation and final verification

**Files:**
- Modify: `PAPER_BUILD_DECOUPLING.md` (mark step 4 as complete)
- Modify: `CLAUDE.md` (update papers module description if needed)

- [ ] **Step 1: Update PAPER_BUILD_DECOUPLING.md**

Mark remaining items as completed:

```markdown
### Completed
1. **paper_db.json updated** — ...
2. **Makefiles created** — ...
3. **Resolved moves** — ...
4. **mf package changes** — removed build logic from processor.py, replaced
   process→ingest and sync→status commands, removed tex2any/pdflatex dependencies
```

- [ ] **Step 2: Run full test suite with coverage**

Run: `pytest --cov=mf.papers --cov-report=term-missing --tb=short`

Review coverage. The papers module should maintain high coverage. Any gaps in the new `resolve_artifact_paths` or `ingest_paper` code indicate missing tests.

- [ ] **Step 3: Run ruff and mypy**

```bash
ruff check src/mf/papers/
mypy src/mf/papers/
```

Fix any issues found.

- [ ] **Step 4: Commit docs**

```bash
git add PAPER_BUILD_DECOUPLING.md
git commit -m "docs: mark paper build decoupling step 4 as complete"
```

- [ ] **Step 5: Push**

```bash
git push
```

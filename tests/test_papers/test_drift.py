"""Tests for papers render-drift engine binding."""

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


def _seed_content_page(mock_site_root, slug, date_str):
    """Create a minimal Hugo content page for a paper with the given date."""
    from mf.core.config import get_paths

    paths = get_paths()
    content_dir = paths.papers / slug
    content_dir.mkdir(parents=True, exist_ok=True)
    page = content_dir / "index.md"
    page.write_text(
        f"---\ndate: {date_str}\ntitle: Demo Paper\n---\n\nBody text.\n",
        encoding="utf-8",
    )
    return page


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
    assert "2024-01-01" in first


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


def test_date_pin_reconciles_from_existing_page(mock_site_root):
    """Pin must read the existing page's date rather than falling back to mtime."""
    from mf.core.config import get_paths
    from mf.core.database import PaperDatabase
    from mf.papers.generator import generate_paper_content

    slug = "reconcile-paper"
    _seed_latex(mock_site_root, slug)
    # Pre-create the content page with a known date.
    _seed_content_page(mock_site_root, slug, "2023-05-01")

    db = PaperDatabase()
    db.load()
    # Paper has no stored date and no extracted date: the old code would pin
    # the mtime of the latex dir; the new code must reconcile from the page.
    generate_paper_content(slug, db, use_image_cache=True, dry_run=False)

    # Reload from disk to prove durability.
    db2 = PaperDatabase()
    db2.load()
    entry = db2.get(slug)
    assert entry is not None, "entry must be created by generate"
    assert entry.data.get("date") == "2023-05-01", (
        f"expected '2023-05-01' (reconciled from existing page), got {entry.data.get('date')!r}"
    )


def test_papers_drift_stale_after_title_override_change(mock_site_root):
    """After generate, changing the title override in paper_db makes the page stale."""
    from mf.core.config import get_paths
    from mf.core.database import PaperDatabase
    from mf.papers.generator import PapersRenderer, generate_paper_content

    slug = "title-override-paper"
    _seed_latex(mock_site_root, slug)

    db = PaperDatabase()
    db.load()

    # First generate: pins a date and writes the content page.
    generate_paper_content(slug, db, use_image_cache=True, dry_run=False)

    renderer = PapersRenderer(db, get_paths())
    assert {f.slug: f.status for f in check_render_drift(renderer)}[slug] == "current"

    # Mutate the title field that flows directly into the rendered frontmatter.
    db.update(slug, title="Completely Different Title Override")
    db.save()

    db2 = PaperDatabase()
    db2.load()
    renderer2 = PapersRenderer(db2, get_paths())

    statuses = {f.slug: f.status for f in check_render_drift(renderer2)}
    assert statuses.get(slug) == "stale", (
        f"expected 'stale' after title override, got {statuses.get(slug)!r}"
    )


def test_date_pin_is_durable_across_reload(mock_site_root):
    """Date pinned on first generate must survive a full DB reload and not change on second run."""
    from mf.core.config import get_paths
    from mf.core.database import PaperDatabase
    from mf.papers.generator import PapersRenderer, generate_paper_content

    slug = "durable-paper"
    _seed_latex(mock_site_root, slug)

    db = PaperDatabase()
    db.load()
    # First generate: no existing page, so pin comes from mtime.
    generate_paper_content(slug, db, use_image_cache=True, dry_run=False)

    # Brand-new database object to verify on-disk persistence.
    db2 = PaperDatabase()
    db2.load()
    entry = db2.get(slug)
    assert entry is not None
    pinned_date = entry.data.get("date")
    assert pinned_date, "date must be non-empty after first generate"

    # The renderer built from the reloaded db must report 'current' (not stale).
    renderer = PapersRenderer(db2, get_paths())
    statuses = {f.slug: f.status for f in check_render_drift(renderer)}
    assert statuses.get(slug) == "current", (
        f"expected 'current' after generate, got {statuses.get(slug)!r}"
    )

    # Second generate must not change the stored date (idempotent pin).
    generate_paper_content(slug, db2, use_image_cache=True, dry_run=False)
    db3 = PaperDatabase()
    db3.load()
    entry3 = db3.get(slug)
    assert entry3 is not None
    assert entry3.data.get("date") == pinned_date, (
        f"date changed on second generate: was {pinned_date!r}, now {entry3.data.get('date')!r}"
    )

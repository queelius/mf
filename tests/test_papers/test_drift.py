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

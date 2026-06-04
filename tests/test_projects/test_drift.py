"""Tests for the render-drift engine binding for the projects module."""

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


def test_projects_drift_rich_uses_index_branch(mock_site_root):
    from mf.core.config import get_paths
    from mf.core.database import ProjectsCache, ProjectsDatabase
    from mf.projects.generator import ProjectsRenderer, generate_all_projects

    _seed(mock_site_root, "rich-proj", rich=True)
    cache = ProjectsCache()
    cache.load()
    db = ProjectsDatabase()
    db.load()
    renderer = ProjectsRenderer(cache, db, get_paths())
    assert {f.slug: f.status for f in check_render_drift(renderer)}["rich-proj"] == "missing"
    generate_all_projects(cache, db, dry_run=False)
    assert {f.slug: f.status for f in check_render_drift(renderer)}["rich-proj"] == "current"
    # The primary page for a rich project must be _index.md, not index.md.
    assert renderer.hugo_path("rich-proj").name == "_index.md"

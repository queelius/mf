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


def test_projects_generate_dry_run_says_would_write(mock_site_root):
    """generate --dry-run now delegates to the generator, which prints 'Would write'."""
    from click.testing import CliRunner

    from mf.cli import main

    _seed(mock_site_root, "proj")
    result = CliRunner().invoke(main, ["--dry-run", "projects", "generate"])
    assert result.exit_code == 0
    # The generator's dry-run branch prints "Would write: <path>" (case-sensitive).
    assert "Would write" in result.output


def test_projects_dry_run_reports_hidden_deletion(mock_site_root):
    """generate --dry-run must report a DELETION for a hidden project that has a content dir.

    Previously the render-drift engine would classify it as 'skip (orphan)' because
    iter_slugs() excludes hidden projects. The generator's own dry-run correctly
    prints 'Would delete hidden'.
    """
    from pathlib import Path

    from click.testing import CliRunner

    from mf.cli import main
    from mf.core.config import get_paths
    from mf.core.database import ProjectsCache, ProjectsDatabase

    slug = "hidden-proj"

    # Seed: project in cache + hidden override in db
    cache = ProjectsCache()
    cache.load()
    cache.set(
        slug,
        {
            "name": slug,
            "html_url": f"https://github.com/queelius/{slug}",
            "description": "A hidden project",
            "created_at": "2023-05-01T00:00:00Z",
            "stargazers_count": 0,
            "topics": [],
            "language": "Python",
        },
    )
    cache.save()

    db = ProjectsDatabase()
    db.load()
    db.set(slug, {"hide": True})
    db.save()

    # Create the content dir that would be deleted on real generate
    paths = get_paths()
    content_dir = paths.projects / slug
    content_dir.mkdir(parents=True, exist_ok=True)
    (content_dir / "index.md").write_text("---\ntitle: hidden\n---\n", encoding="utf-8")

    result = CliRunner().invoke(main, ["--dry-run", "projects", "generate"])
    assert result.exit_code == 0
    output_lower = result.output.lower()
    # Must report deletion, not skip
    assert "delete" in output_lower, f"Expected 'delete' in output, got:\n{result.output}"
    assert "skip (orphan)" not in output_lower, (
        f"Output must not call it 'skip (orphan)', got:\n{result.output}"
    )


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


def test_projects_drift_orphan_for_hidden_project(mock_site_root):
    """A project page on disk whose slug is hidden in projects_db appears as orphan.

    iter_slugs() excludes hidden projects, but existing_slugs() finds the dir.
    check_render_drift therefore classifies it as 'orphan, on disk unknown to database'
    rather than skipping it.
    """
    from mf.core.config import get_paths
    from mf.core.database import ProjectsCache, ProjectsDatabase
    from mf.projects.generator import ProjectsRenderer, generate_all_projects

    slug = "soon-hidden"
    _seed(mock_site_root, slug)

    cache = ProjectsCache()
    cache.load()
    db = ProjectsDatabase()
    db.load()

    # First: generate so the content dir exists on disk.
    generate_all_projects(cache, db, dry_run=False)

    renderer = ProjectsRenderer(cache, db, get_paths())
    assert {f.slug: f.status for f in check_render_drift(renderer)}[slug] == "current"

    # Now mark the project hidden in projects_db and save.
    db.set(slug, {"hide": True})
    db.save()

    # Build a fresh renderer that picks up the updated db.
    db2 = ProjectsDatabase()
    db2.load()
    renderer2 = ProjectsRenderer(cache, db2, get_paths())

    statuses = {f.slug: f.status for f in check_render_drift(renderer2)}
    # The slug is no longer in iter_slugs() but the dir is in existing_slugs():
    # drift engine must classify it as 'orphan'.
    assert statuses.get(slug) == "orphan", (
        f"expected 'orphan' for hidden project with on-disk page, got {statuses.get(slug)!r}"
    )


def test_projects_drift_stale_after_title_override_change(mock_site_root):
    """After generate, changing a rendered field causes the page to become stale."""
    from mf.core.config import get_paths
    from mf.core.database import ProjectsCache, ProjectsDatabase
    from mf.projects.generator import ProjectsRenderer, generate_all_projects

    slug = "editable-proj"
    _seed(mock_site_root, slug)

    cache = ProjectsCache()
    cache.load()
    db = ProjectsDatabase()
    db.load()

    generate_all_projects(cache, db, dry_run=False)

    renderer = ProjectsRenderer(cache, db, get_paths())
    assert {f.slug: f.status for f in check_render_drift(renderer)}[slug] == "current"

    # Change a field that flows into the rendered frontmatter (title override).
    db.set(slug, {"title": "A Brand New Title Override"})
    db.save()

    db2 = ProjectsDatabase()
    db2.load()
    renderer2 = ProjectsRenderer(cache, db2, get_paths())

    statuses = {f.slug: f.status for f in check_render_drift(renderer2)}
    assert statuses.get(slug) == "stale", (
        f"expected 'stale' after title override change, got {statuses.get(slug)!r}"
    )

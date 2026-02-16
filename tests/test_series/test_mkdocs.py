"""Tests for MkDocs integration in series sync."""

import json
import pytest
from pathlib import Path

import yaml

from mf.core.database import PaperDatabase, ProjectsDatabase, SeriesEntry
from mf.series.mkdocs import (
    validate_mkdocs_repo,
    get_site_base_url,
    copy_posts_to_mkdocs,
    generate_links_md,
    update_mkdocs_nav,
    execute_mkdocs_sync,
)


@pytest.fixture
def source_repo(tmp_path):
    """Create a source repo with mkdocs.yml."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "docs").mkdir()
    (source / "post").mkdir()

    mkdocs_config = {
        "site_name": "Test Series",
        "nav": [
            {"Home": "index.md"},
            {"Posts": [
                {"Old Post": "post/old-post/index.md"},
            ]},
        ],
    }
    (source / "mkdocs.yml").write_text(
        yaml.dump(mkdocs_config, sort_keys=False),
        encoding="utf-8",
    )
    (source / "docs" / "index.md").write_text("# Home\n")

    return source


@pytest.fixture
def series_entry():
    """Create a series entry with associations."""
    return SeriesEntry(
        slug="test-series",
        data={
            "title": "Test Series",
            "description": "A test series",
            "status": "active",
            "associations": {
                "papers": ["paper-one", "paper-two"],
                "projects": ["project-alpha"],
                "links": [
                    {"name": "Reference", "url": "https://example.com/ref"},
                ],
            },
        },
    )


@pytest.fixture
def series_entry_no_assoc():
    """Create a series entry without associations."""
    return SeriesEntry(
        slug="plain-series",
        data={
            "title": "Plain Series",
            "description": "No associations",
            "status": "active",
        },
    )


@pytest.fixture
def paper_db(tmp_path, mock_site_root):
    """Create a paper database with test entries."""
    data = {
        "_comment": "Test papers",
        "_schema_version": "2.0",
        "paper-one": {
            "title": "First Paper",
            "abstract": "This is the abstract for the first paper. It has multiple sentences. The third sentence adds more detail.",
        },
        "paper-two": {
            "title": "Second Paper",
            "abstract": "Abstract for the second paper.",
        },
    }
    db_path = mock_site_root / ".mf" / "paper_db.json"
    db_path.write_text(json.dumps(data, indent=2))
    db = PaperDatabase(db_path)
    db.load()
    return db


@pytest.fixture
def projects_db(tmp_path, mock_site_root):
    """Create a projects database with test entries."""
    data = {
        "_comment": "Test projects",
        "_schema_version": "2.0",
        "project-alpha": {
            "title": "Project Alpha",
            "description": "A library for alpha processing.",
        },
    }
    db_path = mock_site_root / ".mf" / "projects_db.json"
    db_path.write_text(json.dumps(data, indent=2))
    db = ProjectsDatabase(db_path)
    db.load()
    return db


class TestValidateMkdocsRepo:
    """Tests for validate_mkdocs_repo."""

    def test_valid_when_mkdocs_exists(self, source_repo):
        valid, msg = validate_mkdocs_repo(source_repo)
        assert valid is True
        assert "mkdocs.yml" in msg

    def test_invalid_when_mkdocs_missing(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        valid, msg = validate_mkdocs_repo(empty_dir)
        assert valid is False
        assert "not found" in msg


class TestGetSiteBaseUrl:
    """Tests for get_site_base_url."""

    def test_reads_from_config_yaml(self, mock_site_root):
        config_file = mock_site_root / ".mf" / "config.yaml"
        config_file.write_text("site_url: https://custom.example.com\n")

        url = get_site_base_url()
        assert url == "https://custom.example.com/"

    def test_reads_from_hugo_toml(self, mock_site_root):
        hugo_toml = mock_site_root / "hugo.toml"
        hugo_toml.write_text('baseURL = "https://metafunctor.com"\n')

        url = get_site_base_url()
        assert url == "https://metafunctor.com/"

    def test_config_yaml_overrides_hugo_toml(self, mock_site_root):
        config_file = mock_site_root / ".mf" / "config.yaml"
        config_file.write_text("site_url: https://override.example.com\n")

        hugo_toml = mock_site_root / "hugo.toml"
        hugo_toml.write_text('baseURL = "https://metafunctor.com"\n')

        url = get_site_base_url()
        assert url == "https://override.example.com/"

    def test_default_fallback(self, mock_site_root):
        # No config.yaml or hugo.toml content
        url = get_site_base_url()
        assert url == "https://metafunctor.com/"

    def test_trailing_slash_normalized(self, mock_site_root):
        config_file = mock_site_root / ".mf" / "config.yaml"
        config_file.write_text("site_url: https://example.com/\n")

        url = get_site_base_url()
        assert url == "https://example.com/"
        assert not url.endswith("//")


class TestCopyPostsToMkdocs:
    """Tests for copy_posts_to_mkdocs."""

    def test_copies_posts_to_docs(self, mock_site_root, source_repo):
        """Test that posts are copied to docs/post/ in source."""
        # Create posts in metafunctor
        post_dir = mock_site_root / "content" / "post" / "2024-01-01-alpha"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text(
            '---\ntitle: Alpha Post\nseries:\n  - test-series\n---\nContent A'
        )

        post_dir2 = mock_site_root / "content" / "post" / "2024-02-01-beta"
        post_dir2.mkdir(parents=True)
        (post_dir2 / "index.md").write_text(
            '---\ntitle: Beta Post\nseries:\n  - test-series\n---\nContent B'
        )

        entry = SeriesEntry(slug="test-series", data={})
        count = copy_posts_to_mkdocs(entry, source_repo)

        assert count == 2
        assert (source_repo / "docs" / "post" / "2024-01-01-alpha" / "index.md").exists()
        assert (source_repo / "docs" / "post" / "2024-02-01-beta" / "index.md").exists()

    def test_creates_docs_post_dir(self, mock_site_root, tmp_path):
        """Test that docs/post/ is created if missing."""
        source = tmp_path / "no_docs"
        source.mkdir()

        post_dir = mock_site_root / "content" / "post" / "2024-01-01-test"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text(
            '---\ntitle: Test\nseries:\n  - my-series\n---\nContent'
        )

        entry = SeriesEntry(slug="my-series", data={})
        count = copy_posts_to_mkdocs(entry, source)

        assert count == 1
        assert (source / "docs" / "post" / "2024-01-01-test" / "index.md").exists()

    def test_dry_run_no_copy(self, mock_site_root, source_repo):
        """Test dry run does not copy files."""
        post_dir = mock_site_root / "content" / "post" / "2024-01-01-test"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text(
            '---\ntitle: Test\nseries:\n  - test-series\n---\nContent'
        )

        entry = SeriesEntry(slug="test-series", data={})
        count = copy_posts_to_mkdocs(entry, source_repo, dry_run=True)

        assert count == 1  # Counted but not copied
        assert not (source_repo / "docs" / "post" / "2024-01-01-test").exists()

    def test_no_posts_returns_zero(self, mock_site_root, source_repo):
        """Test returns 0 when no posts in series."""
        entry = SeriesEntry(slug="empty-series", data={})
        count = copy_posts_to_mkdocs(entry, source_repo)
        assert count == 0

    def test_overwrites_existing_post(self, mock_site_root, source_repo):
        """Test that existing posts in docs/post/ are overwritten."""
        post_dir = mock_site_root / "content" / "post" / "2024-01-01-test"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text(
            '---\ntitle: Updated\nseries:\n  - test-series\n---\nNew content'
        )

        # Pre-existing file in docs/post/
        old_dir = source_repo / "docs" / "post" / "2024-01-01-test"
        old_dir.mkdir(parents=True)
        (old_dir / "index.md").write_text("Old content")

        entry = SeriesEntry(slug="test-series", data={})
        copy_posts_to_mkdocs(entry, source_repo)

        content = (source_repo / "docs" / "post" / "2024-01-01-test" / "index.md").read_text()
        assert "New content" in content
        assert "Old content" not in content


class TestGenerateLinks:
    """Tests for generate_links_md."""

    def test_generates_all_sections(self, series_entry, paper_db, projects_db):
        """Test generation with papers, projects, and links."""
        md = generate_links_md(series_entry, "https://example.com/", paper_db, projects_db)

        assert md is not None
        assert "# Related Content" in md
        assert "## Papers" in md
        assert "First Paper" in md
        assert "Second Paper" in md
        assert "## Projects" in md
        assert "Project Alpha" in md
        assert "## External Links" in md
        assert "Reference" in md
        assert "https://example.com/ref" in md

    def test_paper_urls(self, series_entry, paper_db, projects_db):
        """Test that paper URLs use the base_url correctly."""
        md = generate_links_md(series_entry, "https://test.com/", paper_db, projects_db)
        assert "https://test.com/papers/paper-one/" in md
        assert "https://test.com/papers/paper-two/" in md

    def test_project_urls(self, series_entry, paper_db, projects_db):
        """Test that project URLs use the base_url correctly."""
        md = generate_links_md(series_entry, "https://test.com/", paper_db, projects_db)
        assert "https://test.com/projects/project-alpha/" in md

    def test_no_associations_returns_none(self, series_entry_no_assoc, paper_db, projects_db):
        """Test returns None when no associations."""
        md = generate_links_md(series_entry_no_assoc, "https://example.com/", paper_db, projects_db)
        assert md is None

    def test_empty_associations_returns_none(self):
        """Test returns None when associations dict is empty."""
        entry = SeriesEntry(slug="test", data={"associations": {}})
        md = generate_links_md(entry, "https://example.com/")
        assert md is None

    def test_missing_paper_slug_warns(self, paper_db, projects_db, capsys):
        """Test that missing paper slugs produce a warning."""
        entry = SeriesEntry(slug="test", data={
            "title": "Test",
            "associations": {"papers": ["nonexistent-paper"]},
        })
        md = generate_links_md(entry, "https://example.com/", paper_db, projects_db)
        # Should still generate (might be empty sections), or None if nothing valid
        # The important thing is it doesn't crash

    def test_missing_project_slug_warns(self, paper_db, projects_db, capsys):
        """Test that missing project slugs produce a warning."""
        entry = SeriesEntry(slug="test", data={
            "title": "Test",
            "associations": {"projects": ["nonexistent-project"]},
        })
        md = generate_links_md(entry, "https://example.com/", paper_db, projects_db)
        # Should not crash

    def test_only_links_section(self):
        """Test generation with only external links."""
        entry = SeriesEntry(slug="test", data={
            "title": "Test",
            "associations": {
                "links": [{"name": "Docs", "url": "https://docs.example.com"}],
            },
        })
        md = generate_links_md(entry, "https://example.com/")

        assert md is not None
        assert "## External Links" in md
        assert "Docs" in md
        assert "## Papers" not in md
        assert "## Projects" not in md

    def test_abstract_truncation(self, projects_db):
        """Test that long abstracts are truncated."""
        long_abstract = "This is a very long abstract. " * 20  # ~600 chars

        entry = SeriesEntry(slug="test", data={
            "title": "Test",
            "associations": {"papers": ["long-paper"]},
        })

        # Create a paper DB with a long abstract
        paper_data = {
            "_comment": "test",
            "_schema_version": "2.0",
            "long-paper": {
                "title": "Long Paper",
                "abstract": long_abstract,
            },
        }
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(paper_data, f)
            db_path = Path(f.name)

        pdb = PaperDatabase(db_path)
        pdb.load()

        md = generate_links_md(entry, "https://example.com/", pdb, projects_db)
        assert md is not None
        # The abstract text in the output should be shorter than the original
        assert len(long_abstract) > 200
        # Check truncation happened (output shouldn't contain the full abstract)
        lines = [l for l in md.split("\n") if l.startswith("  ")]
        for line in lines:
            assert len(line.strip()) <= 250  # some margin for the truncation

        db_path.unlink()

    def test_generated_footer(self, series_entry, paper_db, projects_db):
        """Test that the footer is included."""
        md = generate_links_md(series_entry, "https://example.com/", paper_db, projects_db)
        assert "*Generated by mf series sync*" in md


class TestUpdateMkdocsNav:
    """Tests for update_mkdocs_nav."""

    def test_rebuilds_posts_section(self, source_repo, mock_site_root):
        """Test that Posts nav section is rebuilt from docs/post/ files."""
        # Create posts in docs/post/
        post1 = source_repo / "docs" / "post" / "2024-01-first"
        post1.mkdir(parents=True)
        (post1 / "index.md").write_text(
            '---\ntitle: First Post\ndate: 2024-01-01\nseries_weight: 1\n---\n'
        )

        post2 = source_repo / "docs" / "post" / "2024-02-second"
        post2.mkdir(parents=True)
        (post2 / "index.md").write_text(
            '---\ntitle: Second Post\ndate: 2024-02-01\nseries_weight: 2\n---\n'
        )

        entry = SeriesEntry(slug="test-series", data={"title": "Test Series"})
        update_mkdocs_nav(source_repo, entry, has_links=False)

        config = yaml.safe_load((source_repo / "mkdocs.yml").read_text())
        nav = config["nav"]

        # Find Posts section
        posts_section = None
        for item in nav:
            if isinstance(item, dict) and "Posts" in item:
                posts_section = item["Posts"]

        assert posts_section is not None
        assert len(posts_section) == 2
        # Should be sorted by weight
        assert list(posts_section[0].keys())[0] == "First Post"
        assert list(posts_section[1].keys())[0] == "Second Post"

    def test_adds_links_entry(self, source_repo, mock_site_root):
        """Test that Links entry is added when has_links is True."""
        entry = SeriesEntry(slug="test-series", data={})
        update_mkdocs_nav(source_repo, entry, has_links=True)

        config = yaml.safe_load((source_repo / "mkdocs.yml").read_text())
        nav = config["nav"]

        links_found = any(
            isinstance(item, dict) and "Links" in item
            for item in nav
        )
        assert links_found

    def test_no_links_entry_when_false(self, source_repo, mock_site_root):
        """Test that Links entry is not added when has_links is False."""
        entry = SeriesEntry(slug="test-series", data={})
        update_mkdocs_nav(source_repo, entry, has_links=False)

        config = yaml.safe_load((source_repo / "mkdocs.yml").read_text())
        nav = config["nav"]

        links_found = any(
            isinstance(item, dict) and "Links" in item
            for item in nav
        )
        assert not links_found

    def test_preserves_other_nav_sections(self, source_repo, mock_site_root):
        """Test that non-Posts sections are preserved."""
        entry = SeriesEntry(slug="test-series", data={})
        update_mkdocs_nav(source_repo, entry, has_links=False)

        config = yaml.safe_load((source_repo / "mkdocs.yml").read_text())
        nav = config["nav"]

        home_found = any(
            isinstance(item, dict) and "Home" in item
            for item in nav
        )
        assert home_found

    def test_removes_links_when_not_needed(self, source_repo, mock_site_root):
        """Test that existing Links entry is removed when has_links is False."""
        # First add links
        entry = SeriesEntry(slug="test-series", data={})
        update_mkdocs_nav(source_repo, entry, has_links=True)

        # Verify links added
        config = yaml.safe_load((source_repo / "mkdocs.yml").read_text())
        links_found = any(
            isinstance(item, dict) and "Links" in item
            for item in config["nav"]
        )
        assert links_found

        # Now remove
        update_mkdocs_nav(source_repo, entry, has_links=False)

        config = yaml.safe_load((source_repo / "mkdocs.yml").read_text())
        links_found = any(
            isinstance(item, dict) and "Links" in item
            for item in config["nav"]
        )
        assert not links_found

    def test_dry_run_no_write(self, source_repo, mock_site_root):
        """Test that dry_run does not modify mkdocs.yml."""
        original = (source_repo / "mkdocs.yml").read_text()

        entry = SeriesEntry(slug="test-series", data={})
        update_mkdocs_nav(source_repo, entry, has_links=True, dry_run=True)

        assert (source_repo / "mkdocs.yml").read_text() == original

    def test_handles_missing_mkdocs_yml(self, tmp_path, mock_site_root):
        """Test graceful handling when mkdocs.yml doesn't exist."""
        entry = SeriesEntry(slug="test-series", data={})
        # Should not raise
        update_mkdocs_nav(tmp_path, entry, has_links=False)

    def test_sort_by_weight_then_date(self, source_repo, mock_site_root):
        """Test that posts are sorted by series_weight then date."""
        # Create posts with mixed weights
        for name, title, weight, date in [
            ("post-c", "Third", 3, "2024-03-01"),
            ("post-a", "First", 1, "2024-01-01"),
            ("post-b", "Second", 2, "2024-02-01"),
        ]:
            d = source_repo / "docs" / "post" / name
            d.mkdir(parents=True)
            (d / "index.md").write_text(
                f'---\ntitle: {title}\ndate: {date}\nseries_weight: {weight}\n---\n'
            )

        entry = SeriesEntry(slug="test-series", data={})
        update_mkdocs_nav(source_repo, entry, has_links=False)

        config = yaml.safe_load((source_repo / "mkdocs.yml").read_text())
        posts_section = None
        for item in config["nav"]:
            if isinstance(item, dict) and "Posts" in item:
                posts_section = item["Posts"]

        titles = [list(p.keys())[0] for p in posts_section]
        assert titles == ["First", "Second", "Third"]

    def test_posts_without_weight_sorted_last(self, source_repo, mock_site_root):
        """Test that posts without series_weight sort after weighted ones."""
        post_weighted = source_repo / "docs" / "post" / "weighted"
        post_weighted.mkdir(parents=True)
        (post_weighted / "index.md").write_text(
            '---\ntitle: Weighted\ndate: 2024-01-01\nseries_weight: 1\n---\n'
        )

        post_unweighted = source_repo / "docs" / "post" / "unweighted"
        post_unweighted.mkdir(parents=True)
        (post_unweighted / "index.md").write_text(
            '---\ntitle: Unweighted\ndate: 2024-02-01\n---\n'
        )

        entry = SeriesEntry(slug="test-series", data={})
        update_mkdocs_nav(source_repo, entry, has_links=False)

        config = yaml.safe_load((source_repo / "mkdocs.yml").read_text())
        posts_section = None
        for item in config["nav"]:
            if isinstance(item, dict) and "Posts" in item:
                posts_section = item["Posts"]

        titles = [list(p.keys())[0] for p in posts_section]
        assert titles == ["Weighted", "Unweighted"]


class TestExecuteMkdocsSync:
    """Tests for execute_mkdocs_sync orchestrator."""

    def test_full_sync(self, mock_site_root, source_repo, series_entry, paper_db, projects_db):
        """Test full orchestration: copies posts, generates links, updates nav."""
        # Create a post in metafunctor
        post_dir = mock_site_root / "content" / "post" / "2024-01-01-test"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text(
            '---\ntitle: Test Post\ndate: 2024-01-01\nseries:\n  - test-series\nseries_weight: 1\n---\nContent'
        )

        execute_mkdocs_sync(
            series_entry,
            source_repo,
            paper_db=paper_db,
            projects_db=projects_db,
            dry_run=False,
        )

        # Verify post was copied
        assert (source_repo / "docs" / "post" / "2024-01-01-test" / "index.md").exists()

        # Verify links.md was generated
        links_path = source_repo / "docs" / "links.md"
        assert links_path.exists()
        links_content = links_path.read_text()
        assert "First Paper" in links_content
        assert "Project Alpha" in links_content

        # Verify mkdocs.yml was updated
        config = yaml.safe_load((source_repo / "mkdocs.yml").read_text())
        nav = config["nav"]

        posts_found = any(isinstance(item, dict) and "Posts" in item for item in nav)
        links_found = any(isinstance(item, dict) and "Links" in item for item in nav)
        assert posts_found
        assert links_found

    def test_dry_run(self, mock_site_root, source_repo, series_entry, paper_db, projects_db):
        """Test dry run does not write files."""
        post_dir = mock_site_root / "content" / "post" / "2024-01-01-test"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text(
            '---\ntitle: Test Post\nseries:\n  - test-series\n---\nContent'
        )

        original_mkdocs = (source_repo / "mkdocs.yml").read_text()

        execute_mkdocs_sync(
            series_entry,
            source_repo,
            paper_db=paper_db,
            projects_db=projects_db,
            dry_run=True,
        )

        # No files should be created
        assert not (source_repo / "docs" / "post" / "2024-01-01-test").exists()
        assert not (source_repo / "docs" / "links.md").exists()
        assert (source_repo / "mkdocs.yml").read_text() == original_mkdocs

    def test_missing_mkdocs_yml_skips(self, mock_site_root, tmp_path, series_entry):
        """Test that missing mkdocs.yml produces a warning and skips."""
        no_mkdocs = tmp_path / "no_mkdocs"
        no_mkdocs.mkdir()

        # Should not raise
        execute_mkdocs_sync(series_entry, no_mkdocs, dry_run=False)

    def test_no_associations_skips_links(self, mock_site_root, source_repo, series_entry_no_assoc):
        """Test that sync without associations skips links.md."""
        execute_mkdocs_sync(series_entry_no_assoc, source_repo, dry_run=False)

        assert not (source_repo / "docs" / "links.md").exists()

        # Nav should not have Links
        config = yaml.safe_load((source_repo / "mkdocs.yml").read_text())
        links_found = any(
            isinstance(item, dict) and "Links" in item
            for item in config["nav"]
        )
        assert not links_found


class TestNavPathTraversal:
    """Regression tests for path traversal in nav generation (Fix #4)."""

    def test_nav_rejects_traversal_directory_names(self, source_repo, mock_site_root):
        """Directories with '..' in the name must be skipped."""
        docs_post = source_repo / "docs" / "post"
        docs_post.mkdir(parents=True, exist_ok=True)

        # Create a directory with path-traversal name
        bad_dir = docs_post / "..%2f..%2fetc"
        bad_dir.mkdir(exist_ok=True)
        (bad_dir / "index.md").write_text("---\ntitle: Evil\n---\n")

        # Create a normal directory
        good_dir = docs_post / "good-post"
        good_dir.mkdir(exist_ok=True)
        (good_dir / "index.md").write_text("---\ntitle: Good\ndate: 2024-01-01\n---\n")

        entry = SeriesEntry(slug="test-series", data={})
        update_mkdocs_nav(source_repo, entry, has_links=False)

        config = yaml.safe_load((source_repo / "mkdocs.yml").read_text())
        posts_section = None
        for item in config["nav"]:
            if isinstance(item, dict) and "Posts" in item:
                posts_section = item["Posts"]

        # Only the good post should be in nav
        assert posts_section is not None
        titles = [list(p.keys())[0] for p in posts_section]
        assert "Good" in titles
        assert "Evil" not in titles


class TestSyncCommandMkdocsFlag:
    """Tests for --add-mkdocs flag in the sync CLI command."""

    def test_add_mkdocs_requires_push(self, series_with_mkdocs):
        """Test that --add-mkdocs errors without --push."""
        from click.testing import CliRunner
        from mf.series.commands import series

        runner = CliRunner()
        result = runner.invoke(series, [
            "sync", "test-series", "--add-mkdocs",
        ])

        assert result.exit_code == 0
        assert "--add-mkdocs can only be used with --push" in result.output

    def test_add_mkdocs_with_push_runs(self, series_with_mkdocs):
        """Test that --add-mkdocs with --push runs mkdocs sync."""
        from click.testing import CliRunner
        from mf.series.commands import series

        runner = CliRunner()
        result = runner.invoke(series, [
            "sync", "test-series", "--push", "--add-mkdocs", "--dry-run",
        ])

        assert result.exit_code == 0
        assert "MkDocs sync" in result.output


@pytest.fixture
def series_with_mkdocs(tmp_path, mock_site_root):
    """Create a series with source repo that has mkdocs.yml."""
    source_dir = tmp_path / "source_repo"
    source_dir.mkdir()
    (source_dir / "post").mkdir()
    (source_dir / "docs").mkdir()

    # Create mkdocs.yml
    mkdocs_config = {"site_name": "Test", "nav": [{"Home": "index.md"}]}
    (source_dir / "mkdocs.yml").write_text(
        yaml.dump(mkdocs_config, sort_keys=False),
        encoding="utf-8",
    )
    (source_dir / "docs" / "index.md").write_text("# Home\n")

    # Create a post in source
    post_dir = source_dir / "post" / "2024-01-01-test"
    post_dir.mkdir()
    (post_dir / "index.md").write_text(
        '---\ntitle: Test Post\ndate: 2024-01-01\nseries:\n  - test-series\n---\nContent'
    )

    # Create landing page
    (source_dir / "docs" / "index.md").write_text("---\ntitle: Test\n---\nLanding")

    # Create series database
    data = {
        "_comment": "Test",
        "_schema_version": "1.2",
        "test-series": {
            "title": "Test Series",
            "description": "A test series",
            "status": "active",
            "source_dir": str(source_dir),
            "posts_subdir": "post",
            "landing_page": "docs/index.md",
            "associations": {
                "papers": ["paper-one"],
                "links": [{"name": "Ref", "url": "https://example.com"}],
            },
        },
    }
    db_path = mock_site_root / ".mf" / "series_db.json"
    db_path.write_text(json.dumps(data, indent=2))

    # Create paper_db and projects_db
    paper_data = {
        "_comment": "Test",
        "_schema_version": "2.0",
        "paper-one": {"title": "Test Paper", "abstract": "An abstract."},
    }
    (mock_site_root / ".mf" / "paper_db.json").write_text(json.dumps(paper_data, indent=2))

    proj_data = {"_comment": "Test", "_schema_version": "2.0"}
    (mock_site_root / ".mf" / "projects_db.json").write_text(json.dumps(proj_data, indent=2))

    return {
        "source_dir": source_dir,
        "site_root": mock_site_root,
    }

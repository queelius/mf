"""Tests for series CLI commands."""

import json
import pytest
from click.testing import CliRunner
from pathlib import Path

from mf.series.commands import series


@pytest.fixture
def series_with_landing(tmp_path, mock_site_root):
    """Create a series database with source_dir and landing page configured."""
    # Create source repo structure
    source_dir = tmp_path / "source_repo"
    source_dir.mkdir()
    (source_dir / "post").mkdir()
    (source_dir / "docs").mkdir()

    # Create landing page
    (source_dir / "docs" / "index.md").write_text("""---
title: Test Series Landing
description: A landing page for testing
---

## Welcome

This is the **landing page** content with _markdown_ formatting.

### Features

- Feature 1
- Feature 2
- Feature 3
""")

    # Create series database
    data = {
        "_comment": "Test series",
        "_schema_version": "1.2",
        "test-series": {
            "title": "Test Series",
            "description": "A test series with landing page",
            "status": "active",
            "source_dir": str(source_dir),
            "posts_subdir": "post",
            "landing_page": "docs/index.md",
        },
        "no-landing-series": {
            "title": "No Landing Series",
            "description": "A series without landing page configured",
            "status": "active",
            "source_dir": str(source_dir),
            "posts_subdir": "post",
            "landing_page": None,
        },
        "inline-series": {
            "title": "Inline Series",
            "description": "A series without external source",
            "status": "active",
        },
    }
    db_path = mock_site_root / ".mf" / "series_db.json"
    db_path.write_text(json.dumps(data, indent=2))

    return {
        "db_path": db_path,
        "source_dir": source_dir,
        "site_root": mock_site_root,
    }


class TestShowCommand:
    """Tests for the series show command."""

    def test_show_basic(self, series_with_landing):
        """Test basic show command displays series details."""
        runner = CliRunner()
        result = runner.invoke(series, ["show", "test-series"])

        assert result.exit_code == 0
        assert "Test Series" in result.output
        assert "active" in result.output

    def test_show_nonexistent_series(self, series_with_landing):
        """Test show command with nonexistent series."""
        runner = CliRunner()
        result = runner.invoke(series, ["show", "nonexistent"])

        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    def test_show_landing_flag_displays_content(self, series_with_landing):
        """Test --landing flag displays landing page content."""
        runner = CliRunner()
        result = runner.invoke(series, ["show", "test-series", "--landing"])

        assert result.exit_code == 0
        # Should show the landing page content
        assert "Welcome" in result.output
        assert "Feature 1" in result.output
        # Should show title in panel
        assert "Landing" in result.output

    def test_show_landing_no_source_dir_no_local(self, series_with_landing):
        """Test --landing flag with series that has no source_dir and no local _index.md."""
        runner = CliRunner()
        result = runner.invoke(series, ["show", "inline-series", "--landing"])

        assert result.exit_code == 0
        assert "No landing page found" in result.output
        assert "No source_dir configured" in result.output

    def test_show_landing_local_fallback(self, series_with_landing):
        """Test --landing flag falls back to local _index.md when no source_dir."""
        site_root = series_with_landing["site_root"]

        # Create local _index.md for the inline series
        series_dir = site_root / "content" / "series" / "inline-series"
        series_dir.mkdir(parents=True, exist_ok=True)
        (series_dir / "_index.md").write_text("""---
title: "Inline Series"
description: "A local series"
---

## Local Landing Content

This is **local** content from the Hugo site.

- Point A
- Point B
""")

        runner = CliRunner()
        result = runner.invoke(series, ["show", "inline-series", "--landing"])

        assert result.exit_code == 0
        # Should show the body content (front matter stripped)
        assert "Local Landing Content" in result.output
        assert "Point A" in result.output
        # Should indicate local source
        assert "(local)" in result.output
        # Front matter should be stripped - title line from YAML should not appear as raw text
        assert 'title: "Inline Series"' not in result.output

    def test_show_landing_external_priority(self, series_with_landing):
        """Test --landing prefers external source over local _index.md."""
        site_root = series_with_landing["site_root"]

        # Create local _index.md for test-series (which also has source_dir)
        series_dir = site_root / "content" / "series" / "test-series"
        series_dir.mkdir(parents=True, exist_ok=True)
        (series_dir / "_index.md").write_text("""---
title: "Test Series"
---

## LOCAL content - should NOT be shown
""")

        runner = CliRunner()
        result = runner.invoke(series, ["show", "test-series", "--landing"])

        assert result.exit_code == 0
        # Should show external content, not local
        assert "Welcome" in result.output
        assert "Feature 1" in result.output
        assert "LOCAL content" not in result.output
        # Should NOT say "(local)"
        assert "(local)" not in result.output

    def test_show_landing_strips_frontmatter(self, series_with_landing):
        """Test that local _index.md front matter is stripped from display."""
        site_root = series_with_landing["site_root"]

        series_dir = site_root / "content" / "series" / "inline-series"
        series_dir.mkdir(parents=True, exist_ok=True)
        (series_dir / "_index.md").write_text("""---
title: "Inline Series"
description: "Should not appear"
tags:
  - test
  - sample
---

## Visible Content Only
""")

        runner = CliRunner()
        result = runner.invoke(series, ["show", "inline-series", "--landing"])

        assert result.exit_code == 0
        assert "Visible Content Only" in result.output
        # YAML front matter should be stripped
        assert "Should not appear" not in result.output
        assert "tags:" not in result.output

    def test_show_landing_no_landing_configured_falls_back(self, series_with_landing):
        """Test --landing with no landing_page config falls back to local when available."""
        site_root = series_with_landing["site_root"]

        # Create local _index.md for no-landing-series
        series_dir = site_root / "content" / "series" / "no-landing-series"
        series_dir.mkdir(parents=True, exist_ok=True)
        (series_dir / "_index.md").write_text("""---
title: "No Landing Series"
---

## Fallback Content

This should appear since landing_page is None but local file exists.
""")

        runner = CliRunner()
        result = runner.invoke(series, ["show", "no-landing-series", "--landing"])

        assert result.exit_code == 0
        assert "Fallback Content" in result.output
        assert "(local)" in result.output

    def test_show_landing_external_file_missing_falls_back(self, series_with_landing):
        """Test --landing falls back to local when external landing file doesn't exist."""
        source_dir = series_with_landing["source_dir"]
        site_root = series_with_landing["site_root"]

        # Remove the external landing page file
        (source_dir / "docs" / "index.md").unlink()

        # Create local _index.md as fallback
        series_dir = site_root / "content" / "series" / "test-series"
        series_dir.mkdir(parents=True, exist_ok=True)
        (series_dir / "_index.md").write_text("""---
title: "Test Series"
---

## Fallback Local Content
""")

        runner = CliRunner()
        result = runner.invoke(series, ["show", "test-series", "--landing"])

        assert result.exit_code == 0
        assert "Fallback Local Content" in result.output
        assert "(local)" in result.output

    def test_show_landing_no_content_anywhere(self, series_with_landing):
        """Test --landing when external file missing and no local file."""
        source_dir = series_with_landing["source_dir"]

        # Remove the external landing page
        (source_dir / "docs" / "index.md").unlink()

        runner = CliRunner()
        result = runner.invoke(series, ["show", "test-series", "--landing"])

        assert result.exit_code == 0
        assert "No landing page found" in result.output


class TestDeleteCommand:
    """Tests for the series delete command."""

    def test_delete_removes_db_entry(self, series_with_landing):
        """Test default delete removes only the database entry."""
        runner = CliRunner()
        result = runner.invoke(series, ["delete", "inline-series", "-y"])

        assert result.exit_code == 0
        assert "Deleted from series_db.json" in result.output

        # Verify it's gone from the database
        result = runner.invoke(series, ["show", "inline-series"])
        assert "not found" in result.output.lower()

    def test_delete_nonexistent_series(self, series_with_landing):
        """Test deleting a series that doesn't exist."""
        runner = CliRunner()
        result = runner.invoke(series, ["delete", "nonexistent", "-y"])

        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    def test_delete_without_purge_keeps_dir_and_refs(self, series_with_landing):
        """Test that without --purge, content dir and post refs are kept."""
        site_root = series_with_landing["site_root"]

        # Create local content directory
        series_dir = site_root / "content" / "series" / "inline-series"
        series_dir.mkdir(parents=True, exist_ok=True)
        (series_dir / "_index.md").write_text("---\ntitle: Test\n---\nContent")

        runner = CliRunner()
        result = runner.invoke(series, ["delete", "inline-series", "-y"])

        assert result.exit_code == 0
        assert "Deleted from series_db.json" in result.output
        # Content directory should still exist
        assert series_dir.exists()

    def test_delete_without_purge_warns_about_posts(self, series_with_landing):
        """Test that without --purge, delete warns about referencing posts."""
        site_root = series_with_landing["site_root"]

        # Create a post that references test-series
        post_dir = site_root / "content" / "post" / "2024-01-01-test"
        post_dir.mkdir(parents=True, exist_ok=True)
        (post_dir / "index.md").write_text(
            '---\ntitle: "A Post"\ndate: 2024-01-01\nseries:\n  - test-series\n---\nContent'
        )

        runner = CliRunner()
        result = runner.invoke(series, ["delete", "test-series", "-y"])

        assert result.exit_code == 0
        assert "1 post(s) reference this series" in result.output
        assert "--purge" in result.output

    def test_purge_deletes_content_dir(self, series_with_landing):
        """Test --purge deletes the local content directory."""
        site_root = series_with_landing["site_root"]

        series_dir = site_root / "content" / "series" / "inline-series"
        series_dir.mkdir(parents=True, exist_ok=True)
        (series_dir / "_index.md").write_text("---\ntitle: Test\n---\nContent")

        assert series_dir.exists()

        runner = CliRunner()
        result = runner.invoke(series, ["delete", "inline-series", "--purge", "-y"])

        assert result.exit_code == 0
        assert "Deleted content directory" in result.output
        assert not series_dir.exists()

    def test_purge_strips_series_from_posts(self, series_with_landing):
        """Test --purge strips the series reference from post frontmatter."""
        import frontmatter

        site_root = series_with_landing["site_root"]

        # Create a post referencing test-series
        post_dir = site_root / "content" / "post" / "2024-01-01-test"
        post_dir.mkdir(parents=True, exist_ok=True)
        post_file = post_dir / "index.md"
        post_file.write_text(
            '---\ntitle: "A Post"\ndate: 2024-01-01\nseries:\n  - test-series\n---\nContent'
        )

        runner = CliRunner()
        result = runner.invoke(series, ["delete", "test-series", "--purge", "-y"])

        assert result.exit_code == 0
        assert "Stripped series reference from 1 post(s)" in result.output

        # Verify the post no longer has the series reference
        post = frontmatter.load(post_file)
        assert "series" not in post.metadata or "test-series" not in post.get("series", [])

    def test_purge_keeps_other_series_in_post(self, series_with_landing):
        """Test --purge only strips the target series, not other series refs."""
        import frontmatter

        site_root = series_with_landing["site_root"]

        # Create a post referencing both test-series and another series
        post_dir = site_root / "content" / "post" / "2024-01-01-test"
        post_dir.mkdir(parents=True, exist_ok=True)
        post_file = post_dir / "index.md"
        post_file.write_text(
            '---\ntitle: "A Post"\ndate: 2024-01-01\nseries:\n  - test-series\n  - other-series\n---\nContent'
        )

        runner = CliRunner()
        result = runner.invoke(series, ["delete", "test-series", "--purge", "-y"])

        assert result.exit_code == 0

        # Verify only test-series was removed, other-series remains
        post = frontmatter.load(post_file)
        assert post.get("series") == ["other-series"]

    def test_delete_prompts_for_confirmation(self, series_with_landing):
        """Test that delete prompts when -y is not given."""
        runner = CliRunner()
        # Send 'n' to abort
        result = runner.invoke(series, ["delete", "inline-series"], input="n\n")

        assert result.exit_code != 0  # Aborted

        # Verify it's still in the database
        result = runner.invoke(series, ["show", "inline-series"])
        assert "Inline Series" in result.output

    def test_dry_run_makes_no_changes(self, series_with_landing):
        """Test --dry-run previews deletion without making changes."""
        site_root = series_with_landing["site_root"]

        # Create local content directory
        series_dir = site_root / "content" / "series" / "inline-series"
        series_dir.mkdir(parents=True, exist_ok=True)
        (series_dir / "_index.md").write_text("---\ntitle: Test\n---\nContent")

        runner = CliRunner()
        result = runner.invoke(series, ["delete", "inline-series", "--purge", "--dry-run"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "nothing was deleted" in result.output

        # Verify series still exists
        result = runner.invoke(series, ["show", "inline-series"])
        assert "Inline Series" in result.output

        # Verify content directory still exists
        assert series_dir.exists()


class TestListCommand:
    """Tests for the series list command."""

    def test_list_shows_all_series(self, series_with_landing):
        """Test list command shows all series."""
        runner = CliRunner()
        result = runner.invoke(series, ["list"])

        assert result.exit_code == 0
        assert "test-series" in result.output
        assert "inline-series" in result.output

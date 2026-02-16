"""Tests for mf posts commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from mf.cli import main


@pytest.fixture
def runner():
    return CliRunner()


# ---- helpers ---------------------------------------------------------------


def _load_fm(path: Path) -> dict:
    """Parse front matter from a markdown file."""
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) >= 3, f"Bad front matter in {path}"
    return yaml.safe_load(parts[1])


# ---- TestPostsList ---------------------------------------------------------


class TestPostsList:
    """Tests for ``mf posts list``."""

    def test_list_all(self, runner, create_content_file):
        create_content_file(slug="2024-01-01-alpha", title="Alpha")
        create_content_file(slug="2024-02-01-beta", title="Beta")

        result = runner.invoke(main, ["posts", "list", "--include-drafts"])
        assert result.exit_code == 0
        assert "Alpha" in result.output
        assert "Beta" in result.output

    def test_list_excludes_drafts_by_default(self, runner, create_content_file):
        create_content_file(slug="2024-01-01-pub", title="Published", draft=False)
        create_content_file(slug="2024-01-02-draft", title="Drafted", draft=True)

        result = runner.invoke(main, ["posts", "list"])
        assert result.exit_code == 0
        assert "Published" in result.output
        assert "Drafted" not in result.output

    def test_list_with_drafts(self, runner, create_content_file):
        create_content_file(slug="2024-01-01-pub", title="Published", draft=False)
        create_content_file(slug="2024-01-02-draft", title="Drafted", draft=True)

        result = runner.invoke(main, ["posts", "list", "--include-drafts"])
        assert result.exit_code == 0
        assert "Published" in result.output
        assert "Drafted" in result.output

    def test_filter_by_tag(self, runner, create_content_file):
        create_content_file(
            slug="2024-01-01-tagged",
            title="Tagged Post",
            extra_fm={"tags": ["python", "ml"]},
        )
        create_content_file(
            slug="2024-01-02-other",
            title="Other Post",
            extra_fm={"tags": ["rust"]},
        )

        result = runner.invoke(main, ["posts", "list", "-t", "python"])
        assert result.exit_code == 0
        assert "Tagged Post" in result.output
        assert "Other Post" not in result.output

    def test_filter_by_series(self, runner, create_content_file):
        create_content_file(
            slug="2024-01-01-in-series",
            title="Series Post",
            extra_fm={"series": ["stepanov"]},
        )
        create_content_file(slug="2024-01-02-standalone", title="Standalone")

        result = runner.invoke(main, ["posts", "list", "--series", "stepanov"])
        assert result.exit_code == 0
        assert "Series Post" in result.output
        assert "Standalone" not in result.output

    def test_filter_featured(self, runner, create_content_file):
        create_content_file(
            slug="2024-01-01-featured",
            title="Featured",
            extra_fm={"featured": True},
        )
        create_content_file(slug="2024-01-02-normal", title="Normal")

        result = runner.invoke(main, ["posts", "list", "--featured"])
        assert result.exit_code == 0
        assert "Featured" in result.output
        assert "Normal" not in result.output

    def test_json_output(self, runner, create_content_file):
        create_content_file(slug="2024-01-01-hello", title="Hello World")

        result = runner.invoke(main, ["posts", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Hello World"
        assert data[0]["slug"] == "2024-01-01-hello"

    def test_filter_by_query(self, runner, create_content_file):
        create_content_file(
            slug="2024-01-01-crypto",
            title="Cryptographic Hash Functions",
        )
        create_content_file(slug="2024-01-02-bloom", title="Bloom Filters")

        result = runner.invoke(main, ["posts", "list", "-q", "cryptographic"])
        assert result.exit_code == 0
        assert "Cryptographic" in result.output
        assert "Bloom" not in result.output

    def test_filter_by_category(self, runner, create_content_file):
        create_content_file(
            slug="2024-01-01-cat",
            title="Categorized",
            extra_fm={"categories": ["research"]},
        )
        create_content_file(
            slug="2024-01-02-other",
            title="Uncategorized",
        )

        result = runner.invoke(main, ["posts", "list", "-c", "research"])
        assert result.exit_code == 0
        assert "Categorized" in result.output
        assert "Uncategorized" not in result.output

    def test_empty_listing(self, runner, mock_site_root):
        result = runner.invoke(main, ["posts", "list"])
        assert result.exit_code == 0
        assert "No posts found" in result.output


# ---- TestPostsCreate -------------------------------------------------------


class TestPostsCreate:
    """Tests for ``mf posts create``."""

    def test_basic_create(self, runner, mock_site_root):
        result = runner.invoke(
            main,
            ["posts", "create", "--title", "My New Post", "--date", "2025-06-15"],
        )
        assert result.exit_code == 0
        assert "Created" in result.output

        # Verify the file
        index_file = mock_site_root / "content" / "post" / "2025-06-15-my-new-post" / "index.md"
        assert index_file.exists()
        fm = _load_fm(index_file)
        assert fm["title"] == "My New Post"
        assert fm["draft"] is True

    def test_create_with_metadata(self, runner, mock_site_root):
        result = runner.invoke(
            main,
            [
                "posts",
                "create",
                "--title",
                "Rich Post",
                "--date",
                "2025-03-01",
                "-t",
                "python",
                "-t",
                "ml",
                "-c",
                "research",
                "-s",
                "stepanov",
                "--featured",
            ],
        )
        assert result.exit_code == 0

        index_file = (
            mock_site_root / "content" / "post" / "2025-03-01-rich-post" / "index.md"
        )
        fm = _load_fm(index_file)
        assert fm["tags"] == ["python", "ml"]
        assert fm["categories"] == ["research"]
        assert fm["series"] == ["stepanov"]
        assert fm["featured"] is True
        assert fm["draft"] is True

    def test_auto_slug_from_title(self, runner, mock_site_root):
        result = runner.invoke(
            main,
            [
                "posts",
                "create",
                "--title",
                "Hello, World! This is Great",
                "--date",
                "2025-01-01",
            ],
        )
        assert result.exit_code == 0
        expected_dir = (
            mock_site_root
            / "content"
            / "post"
            / "2025-01-01-hello-world-this-is-great"
        )
        assert expected_dir.exists()

    def test_duplicate_slug_rejection(self, runner, mock_site_root):
        # First create
        runner.invoke(
            main,
            ["posts", "create", "--title", "Dup", "--date", "2025-01-01", "--slug", "dup"],
        )
        # Second with same slug + date should fail
        result = runner.invoke(
            main,
            ["posts", "create", "--title", "Dup2", "--date", "2025-01-01", "--slug", "dup"],
        )
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_create_with_description(self, runner, mock_site_root):
        result = runner.invoke(
            main,
            [
                "posts",
                "create",
                "--title",
                "Described",
                "--date",
                "2025-02-01",
                "--description",
                "A short preview",
            ],
        )
        assert result.exit_code == 0
        index_file = (
            mock_site_root / "content" / "post" / "2025-02-01-described" / "index.md"
        )
        fm = _load_fm(index_file)
        assert fm["description"] == "A short preview"

    def test_create_with_explicit_slug(self, runner, mock_site_root):
        result = runner.invoke(
            main,
            [
                "posts",
                "create",
                "--title",
                "Some Long Title",
                "--date",
                "2025-04-01",
                "--slug",
                "short",
            ],
        )
        assert result.exit_code == 0
        index_file = (
            mock_site_root / "content" / "post" / "2025-04-01-short" / "index.md"
        )
        assert index_file.exists()
        fm = _load_fm(index_file)
        assert fm["title"] == "Some Long Title"


# ---- TestPostsSet ----------------------------------------------------------


class TestPostsSet:
    """Tests for ``mf posts set`` and ``mf posts unset``."""

    def test_set_field(self, runner, create_content_file):
        create_content_file(slug="2024-01-01-target", title="Target")
        result = runner.invoke(main, ["posts", "set", "target", "author", "Alex"])
        assert result.exit_code == 0
        assert "Set" in result.output

        from mf.core.config import get_paths

        path = get_paths().posts / "2024-01-01-target" / "index.md"
        fm = _load_fm(path)
        assert fm["author"] == "Alex"

    def test_set_boolean(self, runner, create_content_file):
        create_content_file(slug="2024-01-01-target", title="Target")
        result = runner.invoke(main, ["posts", "set", "target", "featured", "true"])
        assert result.exit_code == 0

        from mf.core.config import get_paths

        path = get_paths().posts / "2024-01-01-target" / "index.md"
        fm = _load_fm(path)
        assert fm["featured"] is True

    def test_set_integer(self, runner, create_content_file):
        create_content_file(slug="2024-01-01-target", title="Target")
        result = runner.invoke(main, ["posts", "set", "target", "series_weight", "5"])
        assert result.exit_code == 0

        from mf.core.config import get_paths

        path = get_paths().posts / "2024-01-01-target" / "index.md"
        fm = _load_fm(path)
        assert fm["series_weight"] == 5

    def test_nonexistent_post(self, runner, mock_site_root):
        result = runner.invoke(main, ["posts", "set", "no-such-post", "x", "1"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_unset_field(self, runner, create_content_file):
        create_content_file(
            slug="2024-01-01-target",
            title="Target",
            extra_fm={"custom": "value"},
        )

        result = runner.invoke(main, ["posts", "unset", "target", "custom"])
        assert result.exit_code == 0
        assert "Removed" in result.output

        from mf.core.config import get_paths

        path = get_paths().posts / "2024-01-01-target" / "index.md"
        fm = _load_fm(path)
        assert "custom" not in fm

    def test_unset_missing_field(self, runner, create_content_file):
        create_content_file(slug="2024-01-01-target", title="Target")
        result = runner.invoke(main, ["posts", "unset", "target", "nonexistent"])
        assert result.exit_code == 0
        assert "not present" in result.output


# ---- TestPostsTag ----------------------------------------------------------


class TestPostsTag:
    """Tests for ``mf posts tag``."""

    def test_add_tag(self, runner, create_content_file):
        create_content_file(
            slug="2024-01-01-target",
            title="Target",
            extra_fm={"tags": ["existing"]},
        )

        result = runner.invoke(main, ["posts", "tag", "target", "--add", "new-tag"])
        assert result.exit_code == 0
        assert "Updated tags" in result.output

        from mf.core.config import get_paths

        path = get_paths().posts / "2024-01-01-target" / "index.md"
        fm = _load_fm(path)
        assert "existing" in fm["tags"]
        assert "new-tag" in fm["tags"]

    def test_remove_tag(self, runner, create_content_file):
        create_content_file(
            slug="2024-01-01-target",
            title="Target",
            extra_fm={"tags": ["keep", "remove-me"]},
        )

        result = runner.invoke(
            main, ["posts", "tag", "target", "--remove", "remove-me"]
        )
        assert result.exit_code == 0

        from mf.core.config import get_paths

        path = get_paths().posts / "2024-01-01-target" / "index.md"
        fm = _load_fm(path)
        assert "keep" in fm["tags"]
        assert "remove-me" not in fm["tags"]

    def test_set_tags(self, runner, create_content_file):
        create_content_file(
            slug="2024-01-01-target",
            title="Target",
            extra_fm={"tags": ["old1", "old2"]},
        )

        result = runner.invoke(
            main, ["posts", "tag", "target", "--set", "new1, new2, new3"]
        )
        assert result.exit_code == 0

        from mf.core.config import get_paths

        path = get_paths().posts / "2024-01-01-target" / "index.md"
        fm = _load_fm(path)
        assert fm["tags"] == ["new1", "new2", "new3"]

    def test_add_duplicate_tag(self, runner, create_content_file):
        create_content_file(
            slug="2024-01-01-target",
            title="Target",
            extra_fm={"tags": ["python"]},
        )

        result = runner.invoke(main, ["posts", "tag", "target", "--add", "python"])
        assert result.exit_code == 0

        from mf.core.config import get_paths

        path = get_paths().posts / "2024-01-01-target" / "index.md"
        fm = _load_fm(path)
        # Should not duplicate
        assert fm["tags"].count("python") == 1

    def test_tag_nonexistent_post(self, runner, mock_site_root):
        result = runner.invoke(main, ["posts", "tag", "ghost", "--add", "x"])
        assert result.exit_code != 0
        assert "not found" in result.output


# ---- TestPostsFeature ------------------------------------------------------


class TestPostsFeature:
    """Tests for ``mf posts feature``."""

    def test_feature_post(self, runner, create_content_file):
        create_content_file(slug="2024-01-01-target", title="Target")

        result = runner.invoke(main, ["posts", "feature", "target"])
        assert result.exit_code == 0
        assert "Featured" in result.output

        from mf.core.config import get_paths

        path = get_paths().posts / "2024-01-01-target" / "index.md"
        fm = _load_fm(path)
        assert fm["featured"] is True

    def test_unfeature_post(self, runner, create_content_file):
        create_content_file(
            slug="2024-01-01-target",
            title="Target",
            extra_fm={"featured": True},
        )

        result = runner.invoke(main, ["posts", "feature", "target", "--off"])
        assert result.exit_code == 0
        assert "Unfeatured" in result.output

        from mf.core.config import get_paths

        path = get_paths().posts / "2024-01-01-target" / "index.md"
        fm = _load_fm(path)
        assert "featured" not in fm

    def test_feature_nonexistent_post(self, runner, mock_site_root):
        result = runner.invoke(main, ["posts", "feature", "ghost"])
        assert result.exit_code != 0
        assert "not found" in result.output

"""Tests for health CLI commands."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from mf.health.commands import health


@pytest.fixture
def runner():
    return CliRunner()


class TestHealthLinks:
    """Test mf health links."""

    def test_reports_broken_links(self, runner, create_content_file):
        create_content_file(
            slug="post-a",
            body="See [missing](/post/nonexistent/) link.",
        )
        result = runner.invoke(health, ["links"])
        assert result.exit_code == 0
        assert "nonexistent" in result.output

    def test_links_json(self, runner, create_content_file):
        create_content_file(
            slug="post-a",
            body="Link to [bad](/post/nope/).",
        )
        result = runner.invoke(health, ["links", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_no_broken_links(self, runner, create_content_file):
        create_content_file(slug="post-a", body="No links here.")
        result = runner.invoke(health, ["links"])
        assert result.exit_code == 0
        assert "No broken" in result.output


class TestHealthDescriptions:
    """Test mf health descriptions."""

    def test_finds_missing(self, runner, create_content_file):
        create_content_file(slug="post-a")
        result = runner.invoke(health, ["descriptions"])
        assert result.exit_code == 0
        assert "post-a" in result.output

    def test_descriptions_json(self, runner, create_content_file):
        create_content_file(slug="post-a")
        result = runner.invoke(health, ["descriptions", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1


class TestHealthImages:
    """Test mf health images."""

    def test_finds_missing(self, runner, create_content_file):
        create_content_file(slug="post-a")
        result = runner.invoke(health, ["images"])
        assert result.exit_code == 0
        assert "post-a" in result.output

    def test_images_json(self, runner, create_content_file):
        create_content_file(slug="post-a")
        result = runner.invoke(health, ["images", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1


class TestHealthDrafts:
    """Test mf health drafts."""

    def test_lists_drafts(self, runner, create_content_file):
        create_content_file(slug="my-draft", draft=True)
        result = runner.invoke(health, ["drafts"])
        assert result.exit_code == 0
        assert "my-draft" in result.output

    def test_drafts_json(self, runner, create_content_file):
        create_content_file(slug="my-draft", draft=True)
        result = runner.invoke(health, ["drafts", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1

    def test_no_drafts(self, runner, create_content_file):
        create_content_file(slug="published")
        result = runner.invoke(health, ["drafts"])
        assert result.exit_code == 0
        assert "No drafts" in result.output


class TestHealthStale:
    """Test mf health stale."""

    def test_stale_json(self, runner, mock_site_root):
        result = runner.invoke(health, ["stale", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

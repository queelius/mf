"""Tests for taxonomy CLI commands."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from mf.taxonomy.commands import taxonomy


@pytest.fixture
def runner():
    return CliRunner()


class TestTaxonomyAudit:
    """Test mf taxonomy audit."""

    def test_detects_case_mismatch(self, runner, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["Python"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["python"]})
        result = runner.invoke(taxonomy, ["audit"])
        assert result.exit_code == 0
        assert "case_mismatch" in result.output or "Python" in result.output

    def test_audit_json_output(self, runner, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["Python"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["python"]})
        result = runner.invoke(taxonomy, ["audit", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_audit_clean(self, runner, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["python"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["rust"]})
        result = runner.invoke(taxonomy, ["audit"])
        assert result.exit_code == 0
        assert "No near-duplicate" in result.output


class TestTaxonomyOrphans:
    """Test mf taxonomy orphans."""

    def test_finds_orphan_tags(self, runner, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["python", "rare"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["python"]})
        result = runner.invoke(taxonomy, ["orphans"])
        assert result.exit_code == 0
        assert "rare" in result.output

    def test_orphans_json_output(self, runner, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["python", "rare"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["python"]})
        result = runner.invoke(taxonomy, ["orphans", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "tags" in data
        assert "rare" in data["tags"]

    def test_orphans_min_count(self, runner, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["a", "b"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["a", "b"]})
        create_content_file(slug="post-c", extra_fm={"tags": ["a"]})
        result = runner.invoke(taxonomy, ["orphans", "--min-count", "3"])
        assert result.exit_code == 0
        assert "b" in result.output


class TestTaxonomyStats:
    """Test mf taxonomy stats."""

    def test_shows_tag_frequency(self, runner, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["python", "ml"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["python"]})
        result = runner.invoke(taxonomy, ["stats"])
        assert result.exit_code == 0
        assert "python" in result.output

    def test_stats_json_output(self, runner, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["python"]})
        result = runner.invoke(taxonomy, ["stats", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_tags" in data

    def test_stats_limit(self, runner, create_content_file):
        for i in range(5):
            create_content_file(
                slug=f"post-{i}",
                extra_fm={"tags": [f"tag-{j}" for j in range(i + 1)]},
            )
        result = runner.invoke(taxonomy, ["stats", "--limit", "3"])
        assert result.exit_code == 0


class TestTaxonomyNormalize:
    """Test mf taxonomy normalize."""

    def test_normalize_dry_run(self, runner, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["Python"]})
        create_content_file(slug="post-b", extra_fm={"tags": ["python"]})
        result = runner.invoke(taxonomy, ["normalize", "--from", "Python", "--to", "python", "--dry-run"])
        assert result.exit_code == 0
        assert "Would" in result.output

    def test_normalize_renames_to_target(self, runner, create_content_file):
        f1 = create_content_file(slug="post-a", extra_fm={"tags": ["Python"]})
        result = runner.invoke(
            taxonomy,
            ["normalize", "--from", "Python", "--to", "python", "--yes"],
        )
        assert result.exit_code == 0
        assert "Updated" in result.output
        # Verify the file was updated
        content = f1.read_text()
        assert "python" in content

    def test_normalize_requires_from_to(self, runner, create_content_file):
        create_content_file(slug="post-a", extra_fm={"tags": ["Python"]})
        result = runner.invoke(taxonomy, ["normalize"])
        assert result.exit_code != 0

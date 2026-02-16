"""Tests for content CLI commands."""

import json

import pytest
from click.testing import CliRunner

from mf.content.commands import content


# ---------------------------------------------------------------------------
# Helper to set up a mock site with projects DB for the content commands
# ---------------------------------------------------------------------------

@pytest.fixture
def content_site(mock_site_root, create_content_file):
    """Set up a mock site with projects DB, cache, and sample content."""
    # Projects database
    db_data = {
        "_comment": "test",
        "_schema_version": "2.0",
        "_example": {},
        "ctk": {"title": "CTK", "tags": ["python"]},
        "alpha-lib": {"title": "Alpha Library", "tags": ["python", "testing"]},
    }
    (mock_site_root / ".mf" / "projects_db.json").write_text(
        json.dumps(db_data, indent=2)
    )

    # Projects cache
    cache_data = {
        "ctk": {"name": "CTK", "topics": ["python"]},
        "alpha-lib": {"name": "Alpha Library", "topics": ["python"]},
    }
    (mock_site_root / ".mf" / "cache" / "projects.json").write_text(
        json.dumps(cache_data, indent=2)
    )

    # Create some content files
    create_content_file(
        content_type="post", slug="ctk-intro",
        title="Introduction to CTK",
        body="The ctk library provides conversation toolkit features. "
             "See https://github.com/queelius/ctk for more.",
        extra_fm={"tags": ["python"]},
    )
    create_content_file(
        content_type="post", slug="unrelated-post",
        title="Cooking Tips",
        body="Today we make pasta.",
        extra_fm={"tags": ["food"]},
    )
    create_content_file(
        content_type="papers", slug="alpha-paper",
        title="Alpha Methods Paper",
        body="This paper describes the alpha-lib library.",
        extra_fm={"tags": ["python", "testing"]},
    )

    return mock_site_root


# ---------------------------------------------------------------------------
# Tests for "content about" command
# ---------------------------------------------------------------------------

def test_about_project_finds_content(content_site):
    """Test 'content about' finds content referencing a project."""
    runner = CliRunner()
    result = runner.invoke(content, ["about", "ctk"])

    assert result.exit_code == 0
    assert "ctk-intro" in result.output or "Introduction to CTK" in result.output


def test_about_project_json_output(content_site):
    """Test 'content about --json' returns valid JSON."""
    runner = CliRunner()
    result = runner.invoke(content, ["about", "ctk", "--json"])

    assert result.exit_code == 0
    # Should be parseable as JSON
    output = result.output.strip()
    data = json.loads(output)
    assert isinstance(data, list)


def test_about_nonexistent_project(content_site):
    """Test 'content about' with a project that has no mentions."""
    runner = CliRunner()
    result = runner.invoke(content, ["about", "zzz-no-match"])

    assert result.exit_code == 0
    assert "No content found" in result.output or "[]" in result.output


def test_about_project_json_empty(content_site):
    """Test 'content about --json' returns empty list when no matches."""
    runner = CliRunner()
    result = runner.invoke(content, ["about", "zzz-no-match", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output.strip())
    assert data == []


# ---------------------------------------------------------------------------
# Tests for "content audit" command
# ---------------------------------------------------------------------------

def test_audit_runs_without_error(content_site):
    """Test 'content audit' basic invocation."""
    runner = CliRunner()
    result = runner.invoke(content, ["audit"])

    assert result.exit_code == 0
    # Should display some form of summary output
    assert "Audit" in result.output or "audit" in result.output


def test_audit_summary_only(content_site):
    """Test 'content audit --summary-only' flag."""
    runner = CliRunner()
    result = runner.invoke(content, ["audit", "--summary-only"])

    assert result.exit_code == 0


def test_audit_json_output(content_site):
    """Test 'content audit --json' returns JSON output."""
    runner = CliRunner()
    result = runner.invoke(content, ["audit", "--json"])

    assert result.exit_code == 0
    # Output should be parseable JSON
    output = result.output.strip()
    data = json.loads(output)
    assert isinstance(data, dict)


def test_audit_with_type_filter(content_site):
    """Test 'content audit --type post' filters to specific type."""
    runner = CliRunner()
    result = runner.invoke(content, ["audit", "--type", "post"])

    assert result.exit_code == 0


def test_audit_list_checks(content_site):
    """Test 'content audit --list-checks' displays available checks."""
    runner = CliRunner()
    result = runner.invoke(content, ["audit", "--list-checks"])

    assert result.exit_code == 0
    # Should show at least one check name
    assert "Name" in result.output or "name" in result.output or "Available" in result.output


def test_audit_extended(content_site):
    """Test 'content audit --extended' runs extended checks."""
    runner = CliRunner()
    result = runner.invoke(content, ["audit", "--extended"])

    assert result.exit_code == 0
    assert "Extended" in result.output or "extended" in result.output or "Audit" in result.output


# ---------------------------------------------------------------------------
# Tests for "content list-projects" command
# ---------------------------------------------------------------------------

def test_list_projects_runs(content_site):
    """Test 'content list-projects' command runs successfully."""
    runner = CliRunner()
    result = runner.invoke(content, ["list-projects"])

    assert result.exit_code == 0
    # Should mention at least one project from the DB
    assert "ctk" in result.output or "alpha-lib" in result.output

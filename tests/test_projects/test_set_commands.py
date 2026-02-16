"""CLI integration tests for project field override commands."""

import json
import pytest
from click.testing import CliRunner

from mf.projects.commands import projects


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    """Set up a projects database and mock site root for CLI tests."""
    # Create .mf/ directory structure
    mf_dir = tmp_path / ".mf"
    mf_dir.mkdir()
    (mf_dir / "cache").mkdir()
    (mf_dir / "backups" / "projects").mkdir(parents=True)

    # Create projects_db.json
    db_data = {
        "_comment": "test",
        "_schema_version": "2.0",
        "test-project": {
            "title": "Test Project",
            "stars": 3,
            "tags": ["python", "test"],
            "category": "library",
            "featured": True,
            "packages": {"pypi": "test-pkg"},
        },
        "hidden-project": {
            "title": "Hidden",
            "hide": True,
        },
    }
    db_path = mf_dir / "projects_db.json"
    db_path.write_text(json.dumps(db_data, indent=2))

    # Create empty cache
    cache_path = mf_dir / "cache" / "projects.json"
    cache_path.write_text("{}")

    # Mock get_site_root
    from mf.core import config
    config.get_site_root.cache_clear()
    monkeypatch.setattr(config, "get_site_root", lambda: tmp_path)

    return tmp_path


def _read_db(tmp_path):
    """Read the projects_db.json from the temp directory."""
    db_path = tmp_path / ".mf" / "projects_db.json"
    return json.loads(db_path.read_text())


class TestFieldsCommand:
    """Tests for 'mf projects fields'."""

    def test_lists_fields(self, runner, db_env):
        result = runner.invoke(projects, ["fields"])
        assert result.exit_code == 0
        assert "stars" in result.output
        assert "tags" in result.output
        assert "featured" in result.output

    def test_shows_types(self, runner, db_env):
        result = runner.invoke(projects, ["fields"])
        assert "int" in result.output
        assert "bool" in result.output
        assert "string_list" in result.output


class TestSetCommand:
    """Tests for 'mf projects set'."""

    def test_set_int_field(self, runner, db_env):
        result = runner.invoke(projects, ["set", "test-project", "stars", "5"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        assert "5" in result.output
        db = _read_db(db_env)
        assert db["test-project"]["stars"] == 5

    def test_set_string_field(self, runner, db_env):
        result = runner.invoke(projects, ["set", "test-project", "title", "New Title"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-project"]["title"] == "New Title"

    def test_set_bool_field(self, runner, db_env):
        result = runner.invoke(projects, ["set", "test-project", "hide", "true"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-project"]["hide"] is True

    def test_set_list_field(self, runner, db_env):
        result = runner.invoke(projects, ["set", "test-project", "tags", "a,b,c"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-project"]["tags"] == ["a", "b", "c"]

    def test_set_dot_notation(self, runner, db_env):
        result = runner.invoke(projects, ["set", "test-project", "packages.npm", "my-npm"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-project"]["packages"]["npm"] == "my-npm"
        # pypi should still be there
        assert db["test-project"]["packages"]["pypi"] == "test-pkg"

    def test_set_invalid_field(self, runner, db_env):
        result = runner.invoke(projects, ["set", "test-project", "bogus_field", "val"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0  # Click doesn't fail, we print error
        assert "Unknown field" in result.output

    def test_set_invalid_int(self, runner, db_env):
        result = runner.invoke(projects, ["set", "test-project", "stars", "abc"], obj=type("Ctx", (), {"dry_run": False})())
        assert "Expected integer" in result.output

    def test_set_out_of_range(self, runner, db_env):
        result = runner.invoke(projects, ["set", "test-project", "stars", "10"], obj=type("Ctx", (), {"dry_run": False})())
        assert "above maximum" in result.output

    def test_set_invalid_choice(self, runner, db_env):
        result = runner.invoke(projects, ["set", "test-project", "category", "banana"], obj=type("Ctx", (), {"dry_run": False})())
        assert "not a valid choice" in result.output

    def test_set_dry_run(self, runner, db_env):
        result = runner.invoke(projects, ["set", "test-project", "stars", "5"], obj=type("Ctx", (), {"dry_run": True})())
        assert result.exit_code == 0
        assert "Dry run" in result.output
        db = _read_db(db_env)
        assert db["test-project"]["stars"] == 3  # Unchanged

    def test_set_creates_new_project(self, runner, db_env):
        result = runner.invoke(projects, ["set", "brand-new", "stars", "4"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["brand-new"]["stars"] == 4


class TestUnsetCommand:
    """Tests for 'mf projects unset'."""

    def test_unset_field(self, runner, db_env):
        result = runner.invoke(projects, ["unset", "test-project", "stars"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert "stars" not in db["test-project"]

    def test_unset_dot_notation(self, runner, db_env):
        result = runner.invoke(projects, ["unset", "test-project", "packages.pypi"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert "pypi" not in db["test-project"].get("packages", {})

    def test_unset_nonexistent_field(self, runner, db_env):
        result = runner.invoke(projects, ["unset", "test-project", "license"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        assert "was not set" in result.output

    def test_unset_nonexistent_project(self, runner, db_env):
        result = runner.invoke(projects, ["unset", "no-such-project", "stars"], obj=type("Ctx", (), {"dry_run": False})())
        assert "not found" in result.output

    def test_unset_unknown_field(self, runner, db_env):
        result = runner.invoke(projects, ["unset", "test-project", "bogus"], obj=type("Ctx", (), {"dry_run": False})())
        assert "Unknown field" in result.output

    def test_unset_dry_run(self, runner, db_env):
        result = runner.invoke(projects, ["unset", "test-project", "stars"], obj=type("Ctx", (), {"dry_run": True})())
        assert "Dry run" in result.output
        db = _read_db(db_env)
        assert db["test-project"]["stars"] == 3  # Unchanged


class TestFeatureCommand:
    """Tests for 'mf projects feature'."""

    def test_feature_on(self, runner, db_env):
        result = runner.invoke(projects, ["feature", "hidden-project"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["hidden-project"]["featured"] is True

    def test_feature_off(self, runner, db_env):
        result = runner.invoke(projects, ["feature", "test-project", "--off"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-project"]["featured"] is False

    def test_feature_dry_run(self, runner, db_env):
        result = runner.invoke(projects, ["feature", "hidden-project"], obj=type("Ctx", (), {"dry_run": True})())
        assert "Dry run" in result.output
        db = _read_db(db_env)
        assert "featured" not in db["hidden-project"]


class TestHideCommand:
    """Tests for 'mf projects hide'."""

    def test_hide_on(self, runner, db_env):
        result = runner.invoke(projects, ["hide", "test-project"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-project"]["hide"] is True

    def test_hide_off(self, runner, db_env):
        result = runner.invoke(projects, ["hide", "hidden-project", "--off"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["hidden-project"]["hide"] is False

    def test_hide_dry_run(self, runner, db_env):
        result = runner.invoke(projects, ["hide", "test-project"], obj=type("Ctx", (), {"dry_run": True})())
        assert "Dry run" in result.output


class TestTagCommand:
    """Tests for 'mf projects tag'."""

    def test_add_tags(self, runner, db_env):
        result = runner.invoke(
            projects, ["tag", "test-project", "--add", "ml", "--add", "ai"],
            obj=type("Ctx", (), {"dry_run": False})(),
        )
        assert result.exit_code == 0
        db = _read_db(db_env)
        tags = db["test-project"]["tags"]
        assert "ml" in tags
        assert "ai" in tags
        assert "python" in tags  # Original still there

    def test_remove_tags(self, runner, db_env):
        result = runner.invoke(
            projects, ["tag", "test-project", "--remove", "test"],
            obj=type("Ctx", (), {"dry_run": False})(),
        )
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert "test" not in db["test-project"]["tags"]
        assert "python" in db["test-project"]["tags"]

    def test_set_tags(self, runner, db_env):
        result = runner.invoke(
            projects, ["tag", "test-project", "--set", "a,b,c"],
            obj=type("Ctx", (), {"dry_run": False})(),
        )
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-project"]["tags"] == ["a", "b", "c"]

    def test_tag_no_options(self, runner, db_env):
        result = runner.invoke(
            projects, ["tag", "test-project"],
            obj=type("Ctx", (), {"dry_run": False})(),
        )
        assert "Specify --add, --remove, or --set" in result.output

    def test_tag_dry_run(self, runner, db_env):
        result = runner.invoke(
            projects, ["tag", "test-project", "--add", "new"],
            obj=type("Ctx", (), {"dry_run": True})(),
        )
        assert "Dry run" in result.output
        db = _read_db(db_env)
        assert "new" not in db["test-project"]["tags"]

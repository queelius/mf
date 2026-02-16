"""CLI integration tests for series field override commands."""

import json
import pytest
from click.testing import CliRunner

from mf.series.commands import series


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    """Set up a series database and mock site root for CLI tests."""
    # Create .mf/ directory structure
    mf_dir = tmp_path / ".mf"
    mf_dir.mkdir()
    (mf_dir / "cache").mkdir()
    (mf_dir / "backups" / "series").mkdir(parents=True)

    # Create series_db.json
    db_data = {
        "_comment": "test",
        "_schema_version": "1.3",
        "test-series": {
            "title": "Test Series",
            "status": "active",
            "featured": True,
            "tags": ["math", "computing"],
            "color": "#667eea",
        },
        "other-series": {
            "title": "Other Series",
        },
    }
    db_path = mf_dir / "series_db.json"
    db_path.write_text(json.dumps(db_data, indent=2))

    # Mock get_site_root
    from mf.core import config
    config.get_site_root.cache_clear()
    monkeypatch.setattr(config, "get_site_root", lambda: tmp_path)

    return tmp_path


def _read_db(tmp_path):
    """Read the series_db.json from the temp directory."""
    db_path = tmp_path / ".mf" / "series_db.json"
    return json.loads(db_path.read_text())


class TestFieldsCommand:
    def test_lists_fields(self, runner, db_env):
        result = runner.invoke(series, ["fields"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "tags" in result.output
        assert "featured" in result.output

    def test_shows_types(self, runner, db_env):
        result = runner.invoke(series, ["fields"])
        assert "bool" in result.output
        assert "string_list" in result.output


class TestSetCommand:
    def test_set_string_field(self, runner, db_env):
        result = runner.invoke(series, ["set", "test-series", "status", "completed"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-series"]["status"] == "completed"

    def test_set_color(self, runner, db_env):
        result = runner.invoke(series, ["set", "test-series", "color", "#ff0000"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-series"]["color"] == "#ff0000"

    def test_set_list_field(self, runner, db_env):
        result = runner.invoke(series, ["set", "test-series", "tags", "a,b,c"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-series"]["tags"] == ["a", "b", "c"]

    def test_set_invalid_field(self, runner, db_env):
        result = runner.invoke(series, ["set", "test-series", "bogus_field", "val"], obj=type("Ctx", (), {"dry_run": False})())
        assert "Unknown field" in result.output

    def test_set_invalid_choice(self, runner, db_env):
        result = runner.invoke(series, ["set", "test-series", "status", "banana"], obj=type("Ctx", (), {"dry_run": False})())
        assert "not a valid choice" in result.output

    def test_set_dry_run(self, runner, db_env):
        result = runner.invoke(series, ["set", "test-series", "status", "completed"], obj=type("Ctx", (), {"dry_run": True})())
        assert "Dry run" in result.output
        db = _read_db(db_env)
        assert db["test-series"]["status"] == "active"  # Unchanged


class TestUnsetCommand:
    def test_unset_field(self, runner, db_env):
        result = runner.invoke(series, ["unset", "test-series", "color"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert "color" not in db["test-series"]

    def test_unset_nonexistent_field(self, runner, db_env):
        result = runner.invoke(series, ["unset", "test-series", "icon"], obj=type("Ctx", (), {"dry_run": False})())
        assert "was not set" in result.output

    def test_unset_nonexistent_series(self, runner, db_env):
        result = runner.invoke(series, ["unset", "no-such-series", "status"], obj=type("Ctx", (), {"dry_run": False})())
        assert "not found" in result.output

    def test_unset_unknown_field(self, runner, db_env):
        result = runner.invoke(series, ["unset", "test-series", "bogus"], obj=type("Ctx", (), {"dry_run": False})())
        assert "Unknown field" in result.output

    def test_unset_dry_run(self, runner, db_env):
        result = runner.invoke(series, ["unset", "test-series", "color"], obj=type("Ctx", (), {"dry_run": True})())
        assert "Dry run" in result.output
        db = _read_db(db_env)
        assert db["test-series"]["color"] == "#667eea"  # Unchanged


class TestFeatureCommand:
    def test_feature_on(self, runner, db_env):
        result = runner.invoke(series, ["feature", "other-series"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["other-series"]["featured"] is True

    def test_feature_off(self, runner, db_env):
        result = runner.invoke(series, ["feature", "test-series", "--off"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-series"]["featured"] is False

    def test_feature_dry_run(self, runner, db_env):
        result = runner.invoke(series, ["feature", "other-series"], obj=type("Ctx", (), {"dry_run": True})())
        assert "Dry run" in result.output
        db = _read_db(db_env)
        assert "featured" not in db["other-series"]


class TestTagCommand:
    def test_add_tags(self, runner, db_env):
        result = runner.invoke(
            series, ["tag", "test-series", "--add", "philosophy", "--add", "logic"],
            obj=type("Ctx", (), {"dry_run": False})(),
        )
        assert result.exit_code == 0
        db = _read_db(db_env)
        tags = db["test-series"]["tags"]
        assert "philosophy" in tags
        assert "logic" in tags
        assert "math" in tags  # Original still there

    def test_remove_tags(self, runner, db_env):
        result = runner.invoke(
            series, ["tag", "test-series", "--remove", "computing"],
            obj=type("Ctx", (), {"dry_run": False})(),
        )
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert "computing" not in db["test-series"]["tags"]
        assert "math" in db["test-series"]["tags"]

    def test_set_tags(self, runner, db_env):
        result = runner.invoke(
            series, ["tag", "test-series", "--set", "a,b,c"],
            obj=type("Ctx", (), {"dry_run": False})(),
        )
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-series"]["tags"] == ["a", "b", "c"]

    def test_tag_no_options(self, runner, db_env):
        result = runner.invoke(
            series, ["tag", "test-series"],
            obj=type("Ctx", (), {"dry_run": False})(),
        )
        assert "Specify --add, --remove, or --set" in result.output

    def test_tag_dry_run(self, runner, db_env):
        result = runner.invoke(
            series, ["tag", "test-series", "--add", "new"],
            obj=type("Ctx", (), {"dry_run": True})(),
        )
        assert "Dry run" in result.output
        db = _read_db(db_env)
        assert "new" not in db["test-series"]["tags"]

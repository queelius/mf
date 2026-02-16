"""CLI integration tests for paper field override commands."""

import json
import pytest
from click.testing import CliRunner

from mf.papers.commands import papers


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    """Set up a paper database and mock site root for CLI tests."""
    # Create .mf/ directory structure
    mf_dir = tmp_path / ".mf"
    mf_dir.mkdir()
    (mf_dir / "cache").mkdir()
    (mf_dir / "backups" / "papers").mkdir(parents=True)

    # Create paper_db.json
    db_data = {
        "_comment": "test",
        "_schema_version": "2.0",
        "test-paper": {
            "title": "Test Paper",
            "stars": 3,
            "tags": ["stats", "ml"],
            "status": "preprint",
            "featured": True,
        },
        "other-paper": {
            "title": "Other Paper",
        },
    }
    db_path = mf_dir / "paper_db.json"
    db_path.write_text(json.dumps(db_data, indent=2))

    # Mock get_site_root
    from mf.core import config
    config.get_site_root.cache_clear()
    monkeypatch.setattr(config, "get_site_root", lambda: tmp_path)

    return tmp_path


def _read_db(tmp_path):
    """Read the paper_db.json from the temp directory."""
    db_path = tmp_path / ".mf" / "paper_db.json"
    return json.loads(db_path.read_text())


class TestFieldsCommand:
    def test_lists_fields(self, runner, db_env):
        result = runner.invoke(papers, ["fields"])
        assert result.exit_code == 0
        assert "stars" in result.output
        assert "tags" in result.output
        assert "venue" in result.output

    def test_shows_types(self, runner, db_env):
        result = runner.invoke(papers, ["fields"])
        assert "int" in result.output
        assert "bool" in result.output
        assert "string_list" in result.output


class TestSetCommand:
    def test_set_int_field(self, runner, db_env):
        result = runner.invoke(papers, ["set", "test-paper", "stars", "5"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        assert "5" in result.output
        db = _read_db(db_env)
        assert db["test-paper"]["stars"] == 5

    def test_set_string_field(self, runner, db_env):
        result = runner.invoke(papers, ["set", "test-paper", "venue", "NeurIPS"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-paper"]["venue"] == "NeurIPS"

    def test_set_list_field(self, runner, db_env):
        result = runner.invoke(papers, ["set", "test-paper", "tags", "a,b,c"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-paper"]["tags"] == ["a", "b", "c"]

    def test_set_invalid_field(self, runner, db_env):
        result = runner.invoke(papers, ["set", "test-paper", "bogus_field", "val"], obj=type("Ctx", (), {"dry_run": False})())
        assert "Unknown field" in result.output

    def test_set_invalid_int(self, runner, db_env):
        result = runner.invoke(papers, ["set", "test-paper", "stars", "abc"], obj=type("Ctx", (), {"dry_run": False})())
        assert "Expected integer" in result.output

    def test_set_out_of_range(self, runner, db_env):
        result = runner.invoke(papers, ["set", "test-paper", "stars", "10"], obj=type("Ctx", (), {"dry_run": False})())
        assert "above maximum" in result.output

    def test_set_invalid_choice(self, runner, db_env):
        result = runner.invoke(papers, ["set", "test-paper", "status", "banana"], obj=type("Ctx", (), {"dry_run": False})())
        assert "not a valid choice" in result.output

    def test_set_dry_run(self, runner, db_env):
        result = runner.invoke(papers, ["set", "test-paper", "stars", "5"], obj=type("Ctx", (), {"dry_run": True})())
        assert "Dry run" in result.output
        db = _read_db(db_env)
        assert db["test-paper"]["stars"] == 3  # Unchanged


class TestUnsetCommand:
    def test_unset_field(self, runner, db_env):
        result = runner.invoke(papers, ["unset", "test-paper", "stars"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert "stars" not in db["test-paper"]

    def test_unset_nonexistent_field(self, runner, db_env):
        result = runner.invoke(papers, ["unset", "test-paper", "venue"], obj=type("Ctx", (), {"dry_run": False})())
        assert "was not set" in result.output

    def test_unset_nonexistent_paper(self, runner, db_env):
        result = runner.invoke(papers, ["unset", "no-such-paper", "stars"], obj=type("Ctx", (), {"dry_run": False})())
        assert "not found" in result.output

    def test_unset_unknown_field(self, runner, db_env):
        result = runner.invoke(papers, ["unset", "test-paper", "bogus"], obj=type("Ctx", (), {"dry_run": False})())
        assert "Unknown field" in result.output

    def test_unset_dry_run(self, runner, db_env):
        result = runner.invoke(papers, ["unset", "test-paper", "stars"], obj=type("Ctx", (), {"dry_run": True})())
        assert "Dry run" in result.output
        db = _read_db(db_env)
        assert db["test-paper"]["stars"] == 3


class TestFeatureCommand:
    def test_feature_on(self, runner, db_env):
        result = runner.invoke(papers, ["feature", "other-paper"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["other-paper"]["featured"] is True

    def test_feature_off(self, runner, db_env):
        result = runner.invoke(papers, ["feature", "test-paper", "--off"], obj=type("Ctx", (), {"dry_run": False})())
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-paper"]["featured"] is False

    def test_feature_dry_run(self, runner, db_env):
        result = runner.invoke(papers, ["feature", "other-paper"], obj=type("Ctx", (), {"dry_run": True})())
        assert "Dry run" in result.output
        db = _read_db(db_env)
        assert "featured" not in db["other-paper"]


class TestTagCommand:
    def test_add_tags(self, runner, db_env):
        result = runner.invoke(
            papers, ["tag", "test-paper", "--add", "ai", "--add", "deep-learning"],
            obj=type("Ctx", (), {"dry_run": False})(),
        )
        assert result.exit_code == 0
        db = _read_db(db_env)
        tags = db["test-paper"]["tags"]
        assert "ai" in tags
        assert "deep-learning" in tags
        assert "stats" in tags  # Original still there

    def test_remove_tags(self, runner, db_env):
        result = runner.invoke(
            papers, ["tag", "test-paper", "--remove", "ml"],
            obj=type("Ctx", (), {"dry_run": False})(),
        )
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert "ml" not in db["test-paper"]["tags"]
        assert "stats" in db["test-paper"]["tags"]

    def test_set_tags(self, runner, db_env):
        result = runner.invoke(
            papers, ["tag", "test-paper", "--set", "a,b,c"],
            obj=type("Ctx", (), {"dry_run": False})(),
        )
        assert result.exit_code == 0
        db = _read_db(db_env)
        assert db["test-paper"]["tags"] == ["a", "b", "c"]

    def test_tag_no_options(self, runner, db_env):
        result = runner.invoke(
            papers, ["tag", "test-paper"],
            obj=type("Ctx", (), {"dry_run": False})(),
        )
        assert "Specify --add, --remove, or --set" in result.output

    def test_tag_dry_run(self, runner, db_env):
        result = runner.invoke(
            papers, ["tag", "test-paper", "--add", "new"],
            obj=type("Ctx", (), {"dry_run": True})(),
        )
        assert "Dry run" in result.output
        db = _read_db(db_env)
        assert "new" not in db["test-paper"]["tags"]

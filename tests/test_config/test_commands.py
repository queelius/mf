"""Tests for mf.config.commands CLI module."""

import json

import pytest
import yaml
from click.testing import CliRunner

from mf.config.commands import (
    config,
    get_cmd,
    get_config_value,
    load_config,
    path_cmd,
    reset_cmd,
    save_config,
    set_cmd,
    set_config_value,
    show_cmd,
)


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


# ---------------------------------------------------------------------------
# load_config / save_config tests
# ---------------------------------------------------------------------------


def test_load_config_no_file(mock_site_root):
    """Test loading config when no config file exists."""
    cfg = load_config()
    assert cfg == {}


def test_load_config_yaml(mock_site_root):
    """Test loading a YAML config file."""
    config_path = mock_site_root / ".mf" / "config.yaml"
    config_path.write_text("backup:\n  keep_days: 14\n")

    cfg = load_config()
    assert cfg["backup"]["keep_days"] == 14


def test_load_config_json(mock_site_root):
    """Test loading a JSON config file (backwards compat)."""
    config_path = mock_site_root / ".mf" / "config.yaml"
    config_path.write_text(json.dumps({"backup": {"keep_days": 7}}))

    cfg = load_config()
    assert cfg["backup"]["keep_days"] == 7


def test_load_config_empty_file(mock_site_root):
    """Test loading an empty config file."""
    config_path = mock_site_root / ".mf" / "config.yaml"
    config_path.write_text("")

    cfg = load_config()
    assert cfg == {}


def test_save_config_creates_yaml(mock_site_root):
    """Test that save_config writes YAML format."""
    save_config({"backup": {"keep_days": 14}})

    config_path = mock_site_root / ".mf" / "config.yaml"
    assert config_path.exists()
    content = config_path.read_text()
    parsed = yaml.safe_load(content)
    assert parsed["backup"]["keep_days"] == 14


# ---------------------------------------------------------------------------
# get_config_value / set_config_value tests
# ---------------------------------------------------------------------------


def test_get_config_value_default(mock_site_root):
    """Test getting a config value that falls back to default."""
    value = get_config_value("backup.keep_days", 30)
    assert value == 30


def test_set_and_get_config_value(mock_site_root):
    """Test setting and then getting a config value."""
    set_config_value("backup.keep_days", 14)
    value = get_config_value("backup.keep_days")
    assert value == 14


def test_set_config_value_nested(mock_site_root):
    """Test setting a deeply nested config value."""
    set_config_value("github.default_user", "testuser")
    value = get_config_value("github.default_user")
    assert value == "testuser"


# ---------------------------------------------------------------------------
# CLI: config group tests
# ---------------------------------------------------------------------------


def test_config_group_help(runner):
    """Test that config group shows help."""
    result = runner.invoke(config, ["--help"])
    assert result.exit_code == 0
    assert "Manage mf configuration" in result.output


# ---------------------------------------------------------------------------
# CLI: config show tests
# ---------------------------------------------------------------------------


def test_config_show_no_custom(runner, mock_site_root):
    """Test config show when no custom settings exist."""
    result = runner.invoke(show_cmd, [])
    assert result.exit_code == 0
    assert "No custom configuration" in result.output or "Using defaults" in result.output


def test_config_show_all(runner, mock_site_root):
    """Test config show --all displays all settings."""
    result = runner.invoke(show_cmd, ["--all"])
    assert result.exit_code == 0
    assert "Configuration" in result.output


# ---------------------------------------------------------------------------
# CLI: config get tests
# ---------------------------------------------------------------------------


def test_config_get_known_key(runner, mock_site_root):
    """Test getting a known config key."""
    result = runner.invoke(get_cmd, ["backup.keep_days"])
    assert result.exit_code == 0
    assert "backup.keep_days" in result.output


def test_config_get_unknown_key(runner, mock_site_root):
    """Test getting an unknown config key."""
    result = runner.invoke(get_cmd, ["nonexistent.key"])
    assert result.exit_code == 0
    assert "Unknown setting" in result.output


# ---------------------------------------------------------------------------
# CLI: config set tests
# ---------------------------------------------------------------------------


def test_config_set_int_value(runner, mock_site_root):
    """Test setting an integer config value."""
    result = runner.invoke(set_cmd, ["backup.keep_days", "14"])
    assert result.exit_code == 0
    assert "Set backup.keep_days = 14" in result.output

    # Verify the value was saved
    value = get_config_value("backup.keep_days")
    assert value == 14


def test_config_set_unknown_key(runner, mock_site_root):
    """Test setting an unknown config key is rejected."""
    result = runner.invoke(set_cmd, ["nonexistent.key", "value"])
    assert result.exit_code == 0
    assert "Unknown setting" in result.output


# ---------------------------------------------------------------------------
# CLI: config reset tests
# ---------------------------------------------------------------------------


def test_config_reset_single_key(runner, mock_site_root):
    """Test resetting a single config key."""
    # First set a value
    set_config_value("backup.keep_days", 7)

    result = runner.invoke(reset_cmd, ["backup.keep_days"])
    assert result.exit_code == 0
    assert "Reset" in result.output


def test_config_reset_all(runner, mock_site_root):
    """Test resetting all config values."""
    set_config_value("backup.keep_days", 7)

    result = runner.invoke(reset_cmd, ["--all", "--force"])
    assert result.exit_code == 0
    assert "All settings reset" in result.output

    # Config file should be deleted
    config_path = mock_site_root / ".mf" / "config.yaml"
    assert not config_path.exists()


def test_config_reset_no_args(runner, mock_site_root):
    """Test reset without key or --all shows error."""
    result = runner.invoke(reset_cmd, [])
    assert result.exit_code == 0
    assert "Specify a key or use --all" in result.output


def test_config_reset_unknown_key(runner, mock_site_root):
    """Test resetting an unknown key is rejected."""
    result = runner.invoke(reset_cmd, ["nonexistent.key"])
    assert result.exit_code == 0
    assert "Unknown setting" in result.output


# ---------------------------------------------------------------------------
# CLI: config path tests
# ---------------------------------------------------------------------------


def test_config_path(runner, mock_site_root):
    """Test config path command shows config file path."""
    result = runner.invoke(path_cmd, [])
    assert result.exit_code == 0
    assert "config.yaml" in result.output

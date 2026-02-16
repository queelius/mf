"""Tests for Claude CLI commands."""

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_site_with_mf(tmp_path, monkeypatch):
    """Create a mock site structure with .mf/ directory."""
    # Create .mf/ directory structure
    mf_dir = tmp_path / ".mf"
    mf_dir.mkdir()
    (mf_dir / "cache").mkdir()
    (mf_dir / "backups" / "papers").mkdir(parents=True)
    (mf_dir / "backups" / "projects").mkdir(parents=True)

    # Create .claude/skills directory
    (tmp_path / ".claude" / "skills").mkdir(parents=True)

    # Mock get_site_root - need to patch both the original and the import in installer
    from mf.core import config
    from mf.claude import installer

    config.get_site_root.cache_clear()
    monkeypatch.setattr(config, "get_site_root", lambda: tmp_path)
    monkeypatch.setattr(installer, "get_site_root", lambda: tmp_path)

    return tmp_path


class TestClaudeInstallCommand:
    """Tests for mf claude install command."""

    def test_install_success(self, runner, mock_site_with_mf):
        """Test successful installation."""
        from mf.cli import main

        result = runner.invoke(main, ["claude", "install"])

        assert result.exit_code == 0
        assert "installed" in result.output.lower()

    def test_install_already_installed(self, runner, mock_site_with_mf):
        """Test install when already installed."""
        from mf.cli import main

        # First install
        runner.invoke(main, ["claude", "install"])

        # Second install
        result = runner.invoke(main, ["claude", "install"])

        assert result.exit_code == 0
        assert "already installed" in result.output.lower()

    def test_install_force(self, runner, mock_site_with_mf):
        """Test force reinstall."""
        from mf.cli import main

        # First install
        runner.invoke(main, ["claude", "install"])

        # Force reinstall
        result = runner.invoke(main, ["claude", "install", "--force"])

        assert result.exit_code == 0
        assert "installed" in result.output.lower()


class TestClaudeUninstallCommand:
    """Tests for mf claude uninstall command."""

    def test_uninstall_not_installed(self, runner, mock_site_with_mf):
        """Test uninstall when not installed."""
        from mf.cli import main

        result = runner.invoke(main, ["claude", "uninstall"])

        assert result.exit_code == 0
        assert "not installed" in result.output.lower()

    def test_uninstall_with_force(self, runner, mock_site_with_mf):
        """Test uninstall with force flag."""
        from mf.cli import main

        # Install first
        runner.invoke(main, ["claude", "install"])

        # Uninstall with force (skip confirmation)
        result = runner.invoke(main, ["claude", "uninstall", "--force"])

        assert result.exit_code == 0
        assert "uninstalled" in result.output.lower()


class TestClaudeStatusCommand:
    """Tests for mf claude status command."""

    def test_status_not_installed(self, runner, mock_site_with_mf):
        """Test status when not installed."""
        from mf.cli import main

        result = runner.invoke(main, ["claude", "status"])

        assert result.exit_code == 0
        assert "not installed" in result.output.lower()

    def test_status_installed(self, runner, mock_site_with_mf):
        """Test status when installed."""
        from mf.cli import main

        # Install first
        runner.invoke(main, ["claude", "install"])

        result = runner.invoke(main, ["claude", "status"])

        assert result.exit_code == 0
        assert "installed" in result.output.lower()
        assert "SKILL.md" in result.output

"""Tests for skill installer."""

import pytest
from pathlib import Path


@pytest.fixture
def mock_site_with_mf(tmp_path, monkeypatch):
    """Create a mock site structure with .mf/ directory."""
    # Create .mf/ directory structure
    mf_dir = tmp_path / ".mf"
    mf_dir.mkdir()
    (mf_dir / "cache").mkdir()
    (mf_dir / "backups" / "papers").mkdir(parents=True)
    (mf_dir / "backups" / "projects").mkdir(parents=True)

    # Create .claude/skills directory (parent for skill)
    (tmp_path / ".claude" / "skills").mkdir(parents=True)

    # Mock get_site_root - need to patch both the original and the import in installer
    from mf.core import config
    from mf.claude import installer

    config.get_site_root.cache_clear()
    monkeypatch.setattr(config, "get_site_root", lambda: tmp_path)
    monkeypatch.setattr(installer, "get_site_root", lambda: tmp_path)

    return tmp_path


class TestGetSkillDir:
    """Tests for get_skill_dir function."""

    def test_returns_correct_path(self, mock_site_with_mf):
        """Test skill directory path resolution."""
        from mf.claude.installer import get_skill_dir

        skill_dir = get_skill_dir(mock_site_with_mf)
        assert skill_dir == mock_site_with_mf / ".claude" / "skills" / "mf"


class TestGetSkillFiles:
    """Tests for get_skill_files function."""

    def test_returns_skill_files(self):
        """Test that skill files are returned."""
        from mf.claude.installer import get_skill_files

        files = get_skill_files()

        assert "SKILL.md" in files
        assert "COMMANDS.md" in files
        assert "WORKFLOWS.md" in files

    def test_files_have_content(self):
        """Test that skill files have content."""
        from mf.claude.installer import get_skill_files

        files = get_skill_files()

        for filename, content in files.items():
            assert len(content) > 0, f"{filename} should have content"


class TestCheckStatus:
    """Tests for check_status function."""

    def test_not_installed(self, mock_site_with_mf):
        """Test status when not installed."""
        from mf.claude.installer import check_status

        status = check_status(mock_site_with_mf)

        assert not status.installed
        assert len(status.files_present) == 0
        assert len(status.files_missing) > 0

    def test_installed(self, mock_site_with_mf):
        """Test status when installed."""
        from mf.claude.installer import install_skill, check_status

        install_skill(site_root=mock_site_with_mf)
        status = check_status(mock_site_with_mf)

        assert status.installed
        assert "SKILL.md" in status.files_present
        assert len(status.files_missing) == 0

    def test_detects_outdated(self, mock_site_with_mf):
        """Test status detects outdated files."""
        from mf.claude.installer import install_skill, check_status, get_skill_dir

        # Install
        install_skill(site_root=mock_site_with_mf)

        # Modify a file
        skill_dir = get_skill_dir(mock_site_with_mf)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("modified content")

        # Check status
        status = check_status(mock_site_with_mf)
        assert "SKILL.md" in status.files_outdated


class TestInstallSkill:
    """Tests for install_skill function."""

    def test_install_creates_files(self, mock_site_with_mf):
        """Test skill installation creates files."""
        from mf.claude.installer import install_skill, get_skill_dir

        success, actions = install_skill(site_root=mock_site_with_mf)

        assert success
        assert len(actions) > 0

        skill_dir = get_skill_dir(mock_site_with_mf)
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "COMMANDS.md").exists()
        assert (skill_dir / "WORKFLOWS.md").exists()

    def test_install_dry_run(self, mock_site_with_mf):
        """Test dry run doesn't create files."""
        from mf.claude.installer import install_skill, get_skill_dir

        success, actions = install_skill(
            site_root=mock_site_with_mf,
            dry_run=True,
        )

        assert success
        assert len(actions) > 0

        skill_dir = get_skill_dir(mock_site_with_mf)
        assert not (skill_dir / "SKILL.md").exists()

    def test_install_already_installed(self, mock_site_with_mf):
        """Test install when already installed without force."""
        from mf.claude.installer import install_skill

        # First install
        install_skill(site_root=mock_site_with_mf)

        # Second install without force
        success, actions = install_skill(site_root=mock_site_with_mf)
        assert not success
        assert "already installed" in actions[0].lower()

    def test_install_force(self, mock_site_with_mf):
        """Test force reinstall."""
        from mf.claude.installer import install_skill

        # First install
        install_skill(site_root=mock_site_with_mf)

        # Force reinstall
        success, actions = install_skill(
            site_root=mock_site_with_mf,
            force=True,
        )
        assert success


class TestUninstallSkill:
    """Tests for uninstall_skill function."""

    def test_uninstall_removes_files(self, mock_site_with_mf):
        """Test skill uninstallation removes files."""
        from mf.claude.installer import install_skill, uninstall_skill, get_skill_dir

        # Install first
        install_skill(site_root=mock_site_with_mf)

        # Uninstall
        success, actions = uninstall_skill(site_root=mock_site_with_mf)

        assert success
        assert len(actions) > 0

        skill_dir = get_skill_dir(mock_site_with_mf)
        assert not skill_dir.exists()

    def test_uninstall_not_installed(self, mock_site_with_mf):
        """Test uninstall when not installed."""
        from mf.claude.installer import uninstall_skill

        success, actions = uninstall_skill(site_root=mock_site_with_mf)

        assert not success
        assert "not installed" in actions[0].lower()

    def test_uninstall_dry_run(self, mock_site_with_mf):
        """Test dry run doesn't remove files."""
        from mf.claude.installer import install_skill, uninstall_skill, get_skill_dir

        # Install first
        install_skill(site_root=mock_site_with_mf)

        # Dry run uninstall
        success, actions = uninstall_skill(
            site_root=mock_site_with_mf,
            dry_run=True,
        )

        assert success
        assert len(actions) > 0

        # Files should still exist
        skill_dir = get_skill_dir(mock_site_with_mf)
        assert (skill_dir / "SKILL.md").exists()

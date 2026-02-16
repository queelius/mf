"""Skill installation and management logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from mf.core.config import get_site_root


@dataclass
class SkillStatus:
    """Status of the mf skill installation."""

    installed: bool
    skill_dir: Path
    files_present: list[str] = field(default_factory=list)
    files_missing: list[str] = field(default_factory=list)
    files_outdated: list[str] = field(default_factory=list)


def get_skill_dir(site_root: Path | None = None) -> Path:
    """Get the skill installation directory.

    Args:
        site_root: Project root (uses default if not provided)

    Returns:
        Path to .claude/skills/mf/
    """
    if site_root is None:
        site_root = get_site_root()
    return site_root / ".claude" / "skills" / "mf"


def get_skill_files() -> dict[str, str]:
    """Get skill file contents from package data.

    Returns:
        Dict mapping filename to content
    """
    files = {}
    data_path = resources.files("mf.claude") / "data"
    for item in data_path.iterdir():
        if item.name.endswith(".md"):
            files[item.name] = item.read_text()
    return files


def check_status(site_root: Path | None = None) -> SkillStatus:
    """Check the status of the skill installation.

    Args:
        site_root: Project root (uses default if not provided)

    Returns:
        SkillStatus with installation details
    """
    skill_dir = get_skill_dir(site_root)
    package_files = get_skill_files()

    files_present = []
    files_missing = []
    files_outdated = []

    for filename, package_content in package_files.items():
        installed_path = skill_dir / filename
        if installed_path.exists():
            files_present.append(filename)
            installed_content = installed_path.read_text()
            if installed_content != package_content:
                files_outdated.append(filename)
        else:
            files_missing.append(filename)

    return SkillStatus(
        installed=skill_dir.exists() and len(files_missing) == 0,
        skill_dir=skill_dir,
        files_present=files_present,
        files_missing=files_missing,
        files_outdated=files_outdated,
    )


def install_skill(
    site_root: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[bool, list[str]]:
    """Install the mf skill.

    Args:
        site_root: Project root (uses default if not provided)
        force: Overwrite existing files
        dry_run: Preview only, don't write files

    Returns:
        Tuple of (success, list of actions taken)
    """
    skill_dir = get_skill_dir(site_root)
    package_files = get_skill_files()
    actions = []

    # Check if already installed
    if skill_dir.exists() and not force:
        status = check_status(site_root)
        if status.installed and not status.files_outdated:
            return False, ["Skill already installed (use --force to reinstall)"]

    # Create directory
    if not dry_run:
        skill_dir.mkdir(parents=True, exist_ok=True)
    actions.append(f"Created {skill_dir}")

    # Write files
    for filename, content in sorted(package_files.items()):
        file_path = skill_dir / filename
        if not dry_run:
            file_path.write_text(content)
        actions.append(f"Wrote {filename}")

    return True, actions


def uninstall_skill(
    site_root: Path | None = None,
    dry_run: bool = False,
) -> tuple[bool, list[str]]:
    """Uninstall the mf skill.

    Args:
        site_root: Project root
        dry_run: Preview only

    Returns:
        Tuple of (success, list of actions taken)
    """
    skill_dir = get_skill_dir(site_root)
    actions = []

    if not skill_dir.exists():
        return False, ["Skill not installed"]

    # Remove files
    for file_path in sorted(skill_dir.iterdir()):
        if file_path.is_file():
            if not dry_run:
                file_path.unlink()
            actions.append(f"Removed {file_path.name}")

    # Remove directory
    if not dry_run:
        skill_dir.rmdir()
    actions.append(f"Removed {skill_dir}")

    return True, actions

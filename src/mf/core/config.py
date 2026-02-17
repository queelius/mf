"""
Configuration and path management.

Provides site root detection and standard paths for the Hugo site.
Uses .mf/ directory for mf-specific data (databases, cache, backups).

Resolution order for site root:
  1. MF_SITE_ROOT environment variable (highest priority)
  2. Walk up from cwd looking for .mf/ directory
  3. Global config file (~/.config/mf/config.yaml) site_root key
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SitePaths:
    """Standard paths for the Hugo site and mf data."""

    root: Path
    mf_dir: Path
    content: Path
    static: Path

    # Content directories
    papers: Path
    projects: Path
    publications: Path
    posts: Path

    # Static directories
    latex: Path

    # Data files (in .mf/)
    paper_db: Path
    projects_db: Path
    projects_cache: Path
    config_file: Path

    # Backup directories (in .mf/)
    paper_backups: Path
    projects_backups: Path
    series_backups: Path

    # Series database
    series_db: Path

    # Packages
    packages: Path
    packages_db: Path
    packages_backups: Path


def get_global_config_path() -> Path:
    """Return the path to the global mf config file.

    Respects XDG_CONFIG_HOME if set, otherwise defaults to ~/.config/mf/config.yaml.

    Returns:
        Path to global config file (may not exist).
    """
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        base = Path(xdg_config_home)
    else:
        base = Path.home() / ".config"
    return base / "mf" / "config.yaml"


def load_global_config() -> dict:
    """Load the global mf configuration.

    Returns:
        Configuration dict, or empty dict if file is missing or invalid.
    """
    config_path = get_global_config_path()
    if not config_path.is_file():
        return {}
    try:
        text = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
        return {}
    except (OSError, yaml.YAMLError):
        return {}


def _walk_up_for_mf(start_path: Path) -> Path | None:
    """Walk up directory tree looking for .mf/ directory.

    Args:
        start_path: Starting path for search.

    Returns:
        Path to directory containing .mf/, or None if not found.
    """
    current = start_path.resolve()
    while current != current.parent:
        if (current / ".mf").is_dir():
            return current
        current = current.parent
    return None


def find_mf_root(start_path: Path | None = None) -> Path:
    """Find project root using 3-tier resolution.

    Resolution order:
      1. MF_SITE_ROOT environment variable (highest priority)
      2. Walk up from start_path (or cwd) looking for .mf/ directory
      3. Global config file site_root key

    Args:
        start_path: Starting path for .mf/ directory walk (defaults to cwd)

    Returns:
        Path to project root

    Raises:
        FileNotFoundError: If .mf/ directory not found by any method
    """
    # Tier 1: MF_SITE_ROOT environment variable
    env_root = os.environ.get("MF_SITE_ROOT")
    if env_root:
        env_path = Path(env_root).resolve()
        if (env_path / ".mf").is_dir():
            return env_path
        raise FileNotFoundError(
            f"MF_SITE_ROOT={env_root} does not contain an .mf/ directory."
        )

    # Tier 2: Walk up from start_path looking for .mf/
    if start_path is None:
        start_path = Path.cwd()
    result = _walk_up_for_mf(Path(start_path))
    if result is not None:
        return result

    # Tier 3: Global config file
    global_config = load_global_config()
    site_root_str = global_config.get("site_root")
    if site_root_str:
        global_path = Path(site_root_str).expanduser().resolve()
        if (global_path / ".mf").is_dir():
            return global_path
        raise FileNotFoundError(
            f"Global config site_root={site_root_str} does not contain an .mf/ directory."
        )

    raise FileNotFoundError(
        f"Could not find .mf/ directory starting from {start_path}. "
        f"Run 'mf init' to initialize, set MF_SITE_ROOT, or configure "
        f"site_root in {get_global_config_path()}."
    )


# Keep old name as alias for compatibility
find_site_root = find_mf_root


@lru_cache(maxsize=1)
def get_site_root() -> Path:
    """Get the cached site root path.

    Returns:
        Path to site root
    """
    return find_mf_root()


def get_paths(site_root: Path | None = None) -> SitePaths:
    """Get all standard paths for the site.

    Args:
        site_root: Site root path (uses cached default if not provided)

    Returns:
        SitePaths dataclass with all paths
    """
    if site_root is None:
        site_root = get_site_root()

    site_root = Path(site_root)
    mf_dir = site_root / ".mf"

    return SitePaths(
        root=site_root,
        mf_dir=mf_dir,
        content=site_root / "content",
        static=site_root / "static",
        # Content directories
        papers=site_root / "content" / "papers",
        projects=site_root / "content" / "projects",
        publications=site_root / "content" / "publications",
        posts=site_root / "content" / "post",
        # Static directories
        latex=site_root / "static" / "latex",
        # Data files in .mf/
        paper_db=mf_dir / "paper_db.json",
        projects_db=mf_dir / "projects_db.json",
        projects_cache=mf_dir / "cache" / "projects.json",
        config_file=mf_dir / "config.yaml",
        # Backup directories in .mf/
        paper_backups=mf_dir / "backups" / "papers",
        projects_backups=mf_dir / "backups" / "projects",
        series_backups=mf_dir / "backups" / "series",
        # Series database
        series_db=mf_dir / "series_db.json",
        # Packages
        packages=site_root / "content" / "packages",
        packages_db=mf_dir / "packages_db.json",
        packages_backups=mf_dir / "backups" / "packages",
    )

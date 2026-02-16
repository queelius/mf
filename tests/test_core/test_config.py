"""Tests for mf.core.config module.

Covers:
  - get_global_config_path() with default and XDG_CONFIG_HOME
  - load_global_config() with missing, valid, and invalid files
  - find_mf_root() 3-tier resolution (env var > local walk > global config)
  - get_paths() including the posts field
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mf.core.config import (
    find_mf_root,
    get_global_config_path,
    get_paths,
    load_global_config,
)


# ---------------------------------------------------------------------------
# get_global_config_path
# ---------------------------------------------------------------------------

class TestGetGlobalConfigPath:
    """Tests for get_global_config_path()."""

    def test_default_path(self, monkeypatch):
        """Without XDG_CONFIG_HOME, returns ~/.config/mf/config.yaml."""
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = get_global_config_path()
        assert result == Path.home() / ".config" / "mf" / "config.yaml"

    def test_xdg_config_home(self, monkeypatch, tmp_path):
        """With XDG_CONFIG_HOME set, uses that directory."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "custom_config"))
        result = get_global_config_path()
        assert result == tmp_path / "custom_config" / "mf" / "config.yaml"

    def test_returns_path_object(self, monkeypatch):
        """Return type is always a Path."""
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = get_global_config_path()
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# load_global_config
# ---------------------------------------------------------------------------

class TestLoadGlobalConfig:
    """Tests for load_global_config()."""

    def test_missing_file_returns_empty(self, monkeypatch, tmp_path):
        """Returns empty dict when config file does not exist."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))
        result = load_global_config()
        assert result == {}

    def test_valid_config(self, monkeypatch, tmp_path):
        """Returns parsed dict from valid YAML config."""
        config_dir = tmp_path / "mf"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"
        config_file.write_text(
            yaml.dump({"site_root": "/some/path", "extra": 42}),
            encoding="utf-8",
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        result = load_global_config()
        assert result == {"site_root": "/some/path", "extra": 42}

    def test_invalid_yaml_returns_empty(self, monkeypatch, tmp_path):
        """Returns empty dict when YAML is invalid."""
        config_dir = tmp_path / "mf"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"
        config_file.write_text("{{{{invalid yaml:::::", encoding="utf-8")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        result = load_global_config()
        assert result == {}

    def test_non_dict_yaml_returns_empty(self, monkeypatch, tmp_path):
        """Returns empty dict when YAML parses to a non-dict (e.g. a list)."""
        config_dir = tmp_path / "mf"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"
        config_file.write_text("- item1\n- item2\n", encoding="utf-8")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        result = load_global_config()
        assert result == {}

    def test_empty_file_returns_empty(self, monkeypatch, tmp_path):
        """Returns empty dict when YAML file is empty."""
        config_dir = tmp_path / "mf"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"
        config_file.write_text("", encoding="utf-8")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        result = load_global_config()
        assert result == {}


# ---------------------------------------------------------------------------
# find_mf_root — 3-tier resolution
# ---------------------------------------------------------------------------

class TestFindMfRoot:
    """Tests for find_mf_root() 3-tier resolution."""

    def _make_site(self, base: Path) -> Path:
        """Create a minimal site with .mf/ directory, return site root."""
        (base / ".mf").mkdir(parents=True)
        return base

    # -- Tier 1: MF_SITE_ROOT env var -----------------------------------------

    def test_env_var_takes_priority(self, monkeypatch, tmp_path):
        """MF_SITE_ROOT env var is the highest priority."""
        site = self._make_site(tmp_path / "env_site")
        monkeypatch.setenv("MF_SITE_ROOT", str(site))
        # start_path has no .mf/, but env var wins
        result = find_mf_root(start_path=tmp_path / "nowhere")
        assert result == site.resolve()

    def test_env_var_without_mf_dir_raises(self, monkeypatch, tmp_path):
        """MF_SITE_ROOT pointing to a dir without .mf/ raises FileNotFoundError."""
        bad_dir = tmp_path / "no_mf"
        bad_dir.mkdir()
        monkeypatch.setenv("MF_SITE_ROOT", str(bad_dir))
        with pytest.raises(FileNotFoundError, match="MF_SITE_ROOT"):
            find_mf_root()

    # -- Tier 2: Local .mf/ walk -----------------------------------------------

    def test_local_walk_finds_mf(self, monkeypatch, tmp_path):
        """Walking up from a subdirectory finds .mf/ in a parent."""
        monkeypatch.delenv("MF_SITE_ROOT", raising=False)
        site = self._make_site(tmp_path / "my_site")
        subdir = site / "content" / "post" / "some-post"
        subdir.mkdir(parents=True)
        result = find_mf_root(start_path=subdir)
        assert result == site.resolve()

    def test_local_walk_takes_priority_over_global_config(
        self, monkeypatch, tmp_path
    ):
        """Local .mf/ walk wins over global config site_root."""
        monkeypatch.delenv("MF_SITE_ROOT", raising=False)

        # Set up global config pointing to a different site
        global_site = self._make_site(tmp_path / "global_site")
        config_dir = tmp_path / "xdg" / "mf"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            yaml.dump({"site_root": str(global_site)}), encoding="utf-8"
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        # Local site should win
        local_site = self._make_site(tmp_path / "local_site")
        result = find_mf_root(start_path=local_site)
        assert result == local_site.resolve()

    # -- Tier 3: Global config fallback ----------------------------------------

    def test_global_config_fallback(self, monkeypatch, tmp_path):
        """Falls back to global config site_root when local walk fails."""
        monkeypatch.delenv("MF_SITE_ROOT", raising=False)

        # No .mf/ in start_path hierarchy
        start = tmp_path / "no_mf_here" / "deep" / "path"
        start.mkdir(parents=True)

        # Global config points to valid site
        global_site = self._make_site(tmp_path / "global_site")
        config_dir = tmp_path / "xdg" / "mf"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            yaml.dump({"site_root": str(global_site)}), encoding="utf-8"
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        result = find_mf_root(start_path=start)
        assert result == global_site.resolve()

    def test_global_config_bad_path_raises(self, monkeypatch, tmp_path):
        """Global config site_root without .mf/ raises FileNotFoundError."""
        monkeypatch.delenv("MF_SITE_ROOT", raising=False)

        bad_dir = tmp_path / "bad_global"
        bad_dir.mkdir()

        config_dir = tmp_path / "xdg" / "mf"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            yaml.dump({"site_root": str(bad_dir)}), encoding="utf-8"
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        # Start from path with no .mf/
        start = tmp_path / "nowhere"
        start.mkdir()

        with pytest.raises(FileNotFoundError, match="Global config"):
            find_mf_root(start_path=start)

    def test_no_resolution_raises(self, monkeypatch, tmp_path):
        """Raises FileNotFoundError when none of the 3 tiers work."""
        monkeypatch.delenv("MF_SITE_ROOT", raising=False)
        # Point XDG to empty dir (no config file)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty_xdg"))

        start = tmp_path / "nowhere"
        start.mkdir()

        with pytest.raises(FileNotFoundError, match="Could not find .mf/"):
            find_mf_root(start_path=start)

    def test_global_config_with_tilde_path(self, monkeypatch, tmp_path):
        """Global config site_root with ~ is expanded."""
        monkeypatch.delenv("MF_SITE_ROOT", raising=False)

        # Create site under a fake home
        fake_home = tmp_path / "fakehome"
        site = self._make_site(fake_home / "my_site")
        monkeypatch.setenv("HOME", str(fake_home))

        config_dir = tmp_path / "xdg" / "mf"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            yaml.dump({"site_root": "~/my_site"}), encoding="utf-8"
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        start = tmp_path / "nowhere"
        start.mkdir()

        result = find_mf_root(start_path=start)
        assert result == site.resolve()


# ---------------------------------------------------------------------------
# get_paths
# ---------------------------------------------------------------------------

class TestGetPaths:
    """Tests for get_paths() including the posts field."""

    def test_posts_path(self, tmp_path):
        """get_paths() includes posts pointing to content/post."""
        (tmp_path / ".mf").mkdir()
        paths = get_paths(site_root=tmp_path)
        assert paths.posts == tmp_path / "content" / "post"

    def test_all_content_directories(self, tmp_path):
        """Verify all content directory paths are correct."""
        (tmp_path / ".mf").mkdir()
        paths = get_paths(site_root=tmp_path)
        assert paths.papers == tmp_path / "content" / "papers"
        assert paths.projects == tmp_path / "content" / "projects"
        assert paths.publications == tmp_path / "content" / "publications"
        assert paths.posts == tmp_path / "content" / "post"

    def test_root_and_mf_dir(self, tmp_path):
        """Verify root and mf_dir are correct."""
        (tmp_path / ".mf").mkdir()
        paths = get_paths(site_root=tmp_path)
        assert paths.root == tmp_path
        assert paths.mf_dir == tmp_path / ".mf"

    def test_data_files(self, tmp_path):
        """Verify data file paths."""
        (tmp_path / ".mf").mkdir()
        paths = get_paths(site_root=tmp_path)
        assert paths.paper_db == tmp_path / ".mf" / "paper_db.json"
        assert paths.projects_db == tmp_path / ".mf" / "projects_db.json"
        assert paths.series_db == tmp_path / ".mf" / "series_db.json"
        assert paths.config_file == tmp_path / ".mf" / "config.yaml"

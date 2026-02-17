"""Verify SitePaths includes packages paths."""

from mf.core.config import get_paths


def test_site_paths_has_packages_fields(mock_site_root):
    paths = get_paths(mock_site_root)
    assert paths.packages == mock_site_root / "content" / "packages"
    assert paths.packages_db == mock_site_root / ".mf" / "packages_db.json"
    assert paths.packages_backups == mock_site_root / ".mf" / "backups" / "packages"

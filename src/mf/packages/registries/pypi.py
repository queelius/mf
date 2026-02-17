"""PyPI registry adapter for mf packages.

Fetches package metadata from the PyPI JSON API and download statistics
from pypistats.org.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime

from mf.packages.registries import PackageMetadata

logger = logging.getLogger(__name__)


def _fetch_json(url: str, timeout: int = 10) -> dict | None:
    """Fetch JSON data from a URL.

    Args:
        url: URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON dict, or None on any error.
    """
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.debug("Failed to fetch %s", url, exc_info=True)
        return None


class PyPIAdapter:
    """Registry adapter for PyPI (Python Package Index)."""

    name = "pypi"

    def fetch_metadata(self, package_name: str) -> PackageMetadata | None:
        """Fetch metadata for a Python package from PyPI.

        Args:
            package_name: Name of the package on PyPI.

        Returns:
            PackageMetadata if the package exists, None otherwise.
        """
        data = _fetch_json(f"https://pypi.org/pypi/{package_name}/json")
        if data is None:
            return None

        info = data.get("info", {})

        # Extract versions (last 10 by upload time)
        releases = data.get("releases", {})
        versions = _extract_versions(releases, limit=10)

        # Best-effort download stats from pypistats
        downloads = _fetch_downloads(package_name)

        # Parse last updated from latest release upload time
        last_updated = _parse_last_updated(releases, info.get("version", ""))

        # Determine homepage: prefer home_page, fall back to project_url
        homepage = info.get("home_page") or None
        if not homepage:
            project_urls = info.get("project_urls") or {}
            homepage = (
                project_urls.get("Homepage")
                or project_urls.get("homepage")
                or project_urls.get("Home")
                or None
            )

        return PackageMetadata(
            name=info.get("name", package_name),
            registry="pypi",
            latest_version=info.get("version", "unknown"),
            description=info.get("summary", "") or "",
            homepage=homepage,
            license=info.get("license") or None,
            downloads=downloads,
            versions=versions,
            install_command=f"pip install {package_name}",
            registry_url=f"https://pypi.org/project/{package_name}/",
            last_updated=last_updated,
        )


def _extract_versions(releases: dict, limit: int = 10) -> list[str]:
    """Extract the most recent version strings from PyPI releases.

    Versions are sorted by their earliest upload time (most recent first),
    then limited to the requested count.

    Args:
        releases: Dict mapping version string to list of release file dicts.
        limit: Maximum number of versions to return.

    Returns:
        List of version strings, most recent first.
    """
    version_times: list[tuple[str, str]] = []
    for version, files in releases.items():
        if not files:
            continue
        # Use the earliest upload_time for the version
        upload_times = [
            f.get("upload_time", "") for f in files if f.get("upload_time")
        ]
        if upload_times:
            version_times.append((version, min(upload_times)))

    # Sort by upload time descending (most recent first)
    version_times.sort(key=lambda vt: vt[1], reverse=True)
    return [vt[0] for vt in version_times[:limit]]


def _fetch_downloads(package_name: str) -> int | None:
    """Fetch recent download count from pypistats.org.

    Args:
        package_name: Package name.

    Returns:
        Total recent downloads, or None if unavailable.
    """
    stats = _fetch_json(f"https://pypistats.org/api/packages/{package_name}/recent")
    if stats is None:
        return None
    data = stats.get("data", {})
    return data.get("last_month") or None


def _parse_last_updated(releases: dict, latest_version: str) -> datetime | None:
    """Parse the upload time of the latest version.

    Args:
        releases: PyPI releases dict.
        latest_version: The current latest version string.

    Returns:
        datetime of the latest release upload, or None.
    """
    files = releases.get(latest_version, [])
    if not files:
        return None
    upload_time = files[0].get("upload_time")
    if not upload_time:
        return None
    try:
        return datetime.fromisoformat(upload_time)
    except (ValueError, TypeError):
        return None


adapter = PyPIAdapter()

"""CRAN registry adapter for mf packages.

Fetches R package metadata from the crandb API (https://crandb.r-pkg.org).
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


def _clean_license(license_str: str | None) -> str | None:
    """Clean CRAN license string by removing '+ file LICENSE' suffix.

    Args:
        license_str: Raw license string from CRAN.

    Returns:
        Cleaned license string, or None if input is None/empty.
    """
    if not license_str:
        return None
    cleaned = license_str.replace("+ file LICENSE", "").strip()
    cleaned = cleaned.replace("+ file LICENCE", "").strip()
    return cleaned or None


class CRANAdapter:
    """Registry adapter for CRAN (Comprehensive R Archive Network)."""

    name = "cran"

    def fetch_metadata(self, package_name: str) -> PackageMetadata | None:
        """Fetch metadata for an R package from CRAN.

        Args:
            package_name: Name of the package on CRAN.

        Returns:
            PackageMetadata if the package exists, None otherwise.
        """
        data = _fetch_json(f"https://crandb.r-pkg.org/{package_name}")
        if data is None:
            return None

        # crandb returns an error key for missing packages
        if "error" in data:
            return None

        # Extract homepage from URL field (comma-separated, take first)
        url_field = data.get("URL") or ""
        homepage = None
        if url_field:
            urls = [u.strip() for u in url_field.split(",")]
            homepage = urls[0] if urls else None

        # Parse publication date
        last_updated = None
        date_pub = data.get("Date/Publication")
        if date_pub:
            try:
                # CRAN dates can be in various formats; try ISO first
                last_updated = datetime.fromisoformat(
                    date_pub.replace(" UTC", "+00:00")
                )
            except (ValueError, TypeError):
                try:
                    # Try just the date portion
                    last_updated = datetime.fromisoformat(date_pub[:10])
                except (ValueError, TypeError, IndexError):
                    pass

        # Extract versions list from crandb "versions" field if present
        versions_data = data.get("versions")
        versions = None
        if isinstance(versions_data, dict):
            versions = list(versions_data.keys())

        return PackageMetadata(
            name=data.get("Package", package_name),
            registry="cran",
            latest_version=data.get("Version", "unknown"),
            description=data.get("Title", "") or "",
            homepage=homepage,
            license=_clean_license(data.get("License")),
            downloads=None,  # CRAN doesn't provide download counts via crandb
            versions=versions,
            install_command=f"install.packages('{package_name}')",
            registry_url=f"https://cran.r-project.org/package={package_name}",
            last_updated=last_updated,
        )


adapter = CRANAdapter()

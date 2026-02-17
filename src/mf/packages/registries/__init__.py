"""Registry adapter protocol and discovery for package registries.

Provides a Protocol-based plugin system where built-in .py files ship with mf
and users can override or extend via extra directories (e.g. .mf/registries/).
"""

from __future__ import annotations

import importlib.util
import json
import logging
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


def fetch_json(url: str, timeout: int = 10) -> dict | None:
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


@dataclass
class PackageMetadata:
    """Metadata for a package from a registry.

    Required fields: name, registry, latest_version, description.
    All other fields are optional.
    """

    name: str
    registry: str
    latest_version: str
    description: str

    homepage: str | None = None
    license: str | None = None
    downloads: int | None = None
    versions: list[str] | None = None
    install_command: str | None = None
    registry_url: str | None = None
    last_updated: datetime | None = None


@runtime_checkable
class RegistryAdapter(Protocol):
    """Protocol for registry adapters.

    Each adapter must have a ``name`` attribute and a ``fetch_metadata`` method.
    """

    name: str

    def fetch_metadata(self, package_name: str) -> PackageMetadata | None:
        """Fetch metadata for a package from the registry.

        Args:
            package_name: Name of the package to look up.

        Returns:
            PackageMetadata if found, None otherwise.
        """
        ...


def _load_adapter_from_file(filepath: Path) -> RegistryAdapter | None:
    """Load a registry adapter from a Python file.

    The file must define a module-level ``adapter`` object that has ``name``
    (str) and ``fetch_metadata`` (callable) attributes.

    Args:
        filepath: Path to a .py file containing an adapter.

    Returns:
        The adapter object if valid, None otherwise.
    """
    module_name = f"mf.packages.registries._dynamic.{filepath.stem}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None or spec.loader is None:
            logger.debug("Could not create module spec for %s", filepath)
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        adapter = getattr(module, "adapter", None)
        if adapter is None:
            logger.debug("No 'adapter' attribute in %s", filepath)
            return None

        if not hasattr(adapter, "name") or not hasattr(adapter, "fetch_metadata"):
            logger.debug(
                "Adapter in %s missing 'name' or 'fetch_metadata' attribute",
                filepath,
            )
            return None

        if not callable(adapter.fetch_metadata):
            logger.debug("adapter.fetch_metadata in %s is not callable", filepath)
            return None

        return adapter  # type: ignore[return-value]

    except Exception:
        logger.debug("Failed to load adapter from %s", filepath, exc_info=True)
        return None


def discover_registries(
    extra_dirs: list[Path] | None = None,
) -> dict[str, RegistryAdapter]:
    """Discover registry adapters from built-in and user directories.

    Scans the built-in directory (same directory as this file) first, then
    any extra directories. Files starting with ``_`` are skipped. Last wins,
    so user directories can override built-in adapters.

    Args:
        extra_dirs: Additional directories to scan for adapter files.

    Returns:
        Dict mapping registry name to adapter instance.
    """
    registries: dict[str, RegistryAdapter] = {}

    dirs_to_scan: list[Path] = [Path(__file__).parent]
    if extra_dirs:
        dirs_to_scan.extend(extra_dirs)

    for scan_dir in dirs_to_scan:
        if not scan_dir.is_dir():
            logger.debug("Skipping non-existent directory: %s", scan_dir)
            continue

        for py_file in sorted(scan_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            adapter = _load_adapter_from_file(py_file)
            if adapter is not None:
                registries[adapter.name] = adapter
                logger.debug(
                    "Loaded registry adapter '%s' from %s", adapter.name, py_file
                )

    return registries

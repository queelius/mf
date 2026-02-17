"""Tests for the PyPI registry adapter."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mf.packages.registries import PackageMetadata
from mf.packages.registries.pypi import PyPIAdapter, adapter


# ---------------------------------------------------------------------------
# Sample PyPI API responses
# ---------------------------------------------------------------------------

SAMPLE_PYPI_RESPONSE = {
    "info": {
        "name": "requests",
        "version": "2.31.0",
        "summary": "Python HTTP for Humans.",
        "home_page": "https://requests.readthedocs.io",
        "license": "Apache-2.0",
        "project_urls": {
            "Homepage": "https://requests.readthedocs.io",
            "Source": "https://github.com/psf/requests",
        },
    },
    "releases": {
        "2.31.0": [{"upload_time": "2023-05-22T15:12:44"}],
        "2.30.0": [{"upload_time": "2023-05-03T12:00:00"}],
        "2.29.0": [{"upload_time": "2023-04-26T12:00:00"}],
        "2.28.2": [{"upload_time": "2023-01-12T12:00:00"}],
        "2.28.1": [{"upload_time": "2022-12-20T12:00:00"}],
        "2.28.0": [{"upload_time": "2022-06-29T12:00:00"}],
        "2.27.1": [{"upload_time": "2022-01-05T12:00:00"}],
        "2.27.0": [{"upload_time": "2022-01-03T12:00:00"}],
        "2.26.0": [{"upload_time": "2021-07-13T12:00:00"}],
        "2.25.1": [{"upload_time": "2020-12-16T12:00:00"}],
        "2.25.0": [{"upload_time": "2020-11-15T12:00:00"}],
        "2.24.0": [{"upload_time": "2020-06-17T12:00:00"}],
    },
}

SAMPLE_PYPISTATS_RESPONSE = {
    "data": {
        "last_day": 5000000,
        "last_week": 35000000,
        "last_month": 150000000,
    },
    "package": "requests",
    "type": "recent_downloads",
}


# ---------------------------------------------------------------------------
# Module-level adapter
# ---------------------------------------------------------------------------


class TestModuleLevelAdapter:
    """Tests for the module-level adapter instance."""

    def test_adapter_exists(self):
        """Module-level adapter instance exists."""
        assert adapter is not None

    def test_adapter_name(self):
        """Module-level adapter has correct name."""
        assert adapter.name == "pypi"

    def test_adapter_is_pypi_adapter(self):
        """Module-level adapter is a PyPIAdapter instance."""
        assert isinstance(adapter, PyPIAdapter)

    def test_adapter_has_callable_fetch_metadata(self):
        """Module-level adapter has callable fetch_metadata."""
        assert callable(adapter.fetch_metadata)


# ---------------------------------------------------------------------------
# fetch_metadata success
# ---------------------------------------------------------------------------


class TestFetchMetadataSuccess:
    """Tests for successful metadata fetching."""

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_returns_package_metadata(self, mock_fetch):
        """fetch_metadata returns PackageMetadata on success."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert isinstance(result, PackageMetadata)

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_name_extracted(self, mock_fetch):
        """Package name is extracted from response."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.name == "requests"

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_registry_is_pypi(self, mock_fetch):
        """Registry is always 'pypi'."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.registry == "pypi"

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_version_extracted(self, mock_fetch):
        """Latest version is extracted from response."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.latest_version == "2.31.0"

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_description_extracted(self, mock_fetch):
        """Description comes from the summary field."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.description == "Python HTTP for Humans."

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_homepage_extracted(self, mock_fetch):
        """Homepage is extracted from home_page field."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.homepage == "https://requests.readthedocs.io"

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_license_extracted(self, mock_fetch):
        """License is extracted from response."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.license == "Apache-2.0"

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_install_command(self, mock_fetch):
        """Install command is pip install <name>."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.install_command == "pip install requests"

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_registry_url(self, mock_fetch):
        """Registry URL points to PyPI project page."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.registry_url == "https://pypi.org/project/requests/"

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_last_updated_parsed(self, mock_fetch):
        """last_updated is parsed from latest release upload_time."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.last_updated is not None
        assert result.last_updated.year == 2023
        assert result.last_updated.month == 5
        assert result.last_updated.day == 22


# ---------------------------------------------------------------------------
# Downloads from pypistats
# ---------------------------------------------------------------------------


class TestDownloads:
    """Tests for download statistics."""

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_downloads_from_pypistats(self, mock_fetch):
        """Downloads come from pypistats last_month."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.downloads == 150000000

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_downloads_none_when_pypistats_fails(self, mock_fetch):
        """Downloads are None when pypistats call fails."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, None]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.downloads is None

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_downloads_none_when_pypistats_missing_data(self, mock_fetch):
        """Downloads are None when pypistats response has no data."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, {"data": {}}]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.downloads is None


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


class TestVersions:
    """Tests for version extraction."""

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_versions_limited_to_10(self, mock_fetch):
        """Versions list is limited to 10 entries."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.versions is not None
        assert len(result.versions) == 10

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_versions_sorted_by_upload_time(self, mock_fetch):
        """Versions are sorted by upload time, most recent first."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        result = adapter.fetch_metadata("requests")
        assert result is not None
        assert result.versions is not None
        assert result.versions[0] == "2.31.0"
        assert result.versions[1] == "2.30.0"

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_fewer_than_10_versions(self, mock_fetch):
        """Works correctly with fewer than 10 versions."""
        small_response = {
            "info": {
                "name": "small-pkg",
                "version": "1.0.0",
                "summary": "Small package",
                "home_page": "",
                "license": "MIT",
            },
            "releases": {
                "1.0.0": [{"upload_time": "2024-01-01T00:00:00"}],
                "0.9.0": [{"upload_time": "2023-06-01T00:00:00"}],
            },
        }
        mock_fetch.side_effect = [small_response, None]
        result = adapter.fetch_metadata("small-pkg")
        assert result is not None
        assert result.versions is not None
        assert len(result.versions) == 2


# ---------------------------------------------------------------------------
# Failure cases
# ---------------------------------------------------------------------------


class TestFetchMetadataFailure:
    """Tests for fetch_metadata returning None."""

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_returns_none_when_fetch_fails(self, mock_fetch):
        """fetch_metadata returns None when PyPI API call fails."""
        mock_fetch.return_value = None
        result = adapter.fetch_metadata("nonexistent-package")
        assert result is None

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_pypi_call_is_first(self, mock_fetch):
        """First fetch_json call is to the PyPI API."""
        mock_fetch.return_value = None
        adapter.fetch_metadata("test-pkg")
        assert mock_fetch.call_count >= 1
        first_url = mock_fetch.call_args_list[0][0][0]
        assert "pypi.org/pypi/test-pkg/json" in first_url


# ---------------------------------------------------------------------------
# Homepage fallback
# ---------------------------------------------------------------------------


class TestHomepageFallback:
    """Tests for homepage extraction fallback logic."""

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_homepage_from_project_urls_when_home_page_empty(self, mock_fetch):
        """Falls back to project_urls.Homepage when home_page is empty."""
        response = {
            "info": {
                "name": "test",
                "version": "1.0",
                "summary": "Test",
                "home_page": "",
                "license": "MIT",
                "project_urls": {"Homepage": "https://example.com"},
            },
            "releases": {},
        }
        mock_fetch.side_effect = [response, None]
        result = adapter.fetch_metadata("test")
        assert result is not None
        assert result.homepage == "https://example.com"

    @patch("mf.packages.registries.pypi.fetch_json")
    def test_homepage_none_when_no_urls(self, mock_fetch):
        """Homepage is None when no URL sources are available."""
        response = {
            "info": {
                "name": "test",
                "version": "1.0",
                "summary": "Test",
                "home_page": "",
                "license": "MIT",
                "project_urls": None,
            },
            "releases": {},
        }
        mock_fetch.side_effect = [response, None]
        result = adapter.fetch_metadata("test")
        assert result is not None
        assert result.homepage is None

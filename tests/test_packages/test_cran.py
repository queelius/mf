"""Tests for the CRAN registry adapter."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mf.packages.registries import PackageMetadata
from mf.packages.registries.cran import CRANAdapter, _clean_license, adapter


# ---------------------------------------------------------------------------
# Sample crandb API response
# ---------------------------------------------------------------------------

SAMPLE_CRAN_RESPONSE = {
    "Package": "ggplot2",
    "Version": "3.5.0",
    "Title": "Create Elegant Data Visualisations Using the Grammar of Graphics",
    "License": "MIT + file LICENSE",
    "URL": "https://ggplot2.tidyverse.org, https://github.com/tidyverse/ggplot2",
    "Date/Publication": "2024-02-23 10:20:03 UTC",
    "versions": {
        "3.5.0": {},
        "3.4.4": {},
        "3.4.3": {},
    },
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
        assert adapter.name == "cran"

    def test_adapter_is_cran_adapter(self):
        """Module-level adapter is a CRANAdapter instance."""
        assert isinstance(adapter, CRANAdapter)

    def test_adapter_has_callable_fetch_metadata(self):
        """Module-level adapter has callable fetch_metadata."""
        assert callable(adapter.fetch_metadata)


# ---------------------------------------------------------------------------
# fetch_metadata success
# ---------------------------------------------------------------------------


class TestFetchMetadataSuccess:
    """Tests for successful metadata fetching."""

    @patch("mf.packages.registries.cran.fetch_json")
    def test_returns_package_metadata(self, mock_fetch):
        """fetch_metadata returns PackageMetadata on success."""
        mock_fetch.return_value = SAMPLE_CRAN_RESPONSE
        result = adapter.fetch_metadata("ggplot2")
        assert isinstance(result, PackageMetadata)

    @patch("mf.packages.registries.cran.fetch_json")
    def test_name_extracted(self, mock_fetch):
        """Package name comes from Package field."""
        mock_fetch.return_value = SAMPLE_CRAN_RESPONSE
        result = adapter.fetch_metadata("ggplot2")
        assert result is not None
        assert result.name == "ggplot2"

    @patch("mf.packages.registries.cran.fetch_json")
    def test_registry_is_cran(self, mock_fetch):
        """Registry is always 'cran'."""
        mock_fetch.return_value = SAMPLE_CRAN_RESPONSE
        result = adapter.fetch_metadata("ggplot2")
        assert result is not None
        assert result.registry == "cran"

    @patch("mf.packages.registries.cran.fetch_json")
    def test_version_extracted(self, mock_fetch):
        """Latest version comes from Version field."""
        mock_fetch.return_value = SAMPLE_CRAN_RESPONSE
        result = adapter.fetch_metadata("ggplot2")
        assert result is not None
        assert result.latest_version == "3.5.0"

    @patch("mf.packages.registries.cran.fetch_json")
    def test_description_from_title(self, mock_fetch):
        """Description comes from the Title field."""
        mock_fetch.return_value = SAMPLE_CRAN_RESPONSE
        result = adapter.fetch_metadata("ggplot2")
        assert result is not None
        assert result.description == "Create Elegant Data Visualisations Using the Grammar of Graphics"

    @patch("mf.packages.registries.cran.fetch_json")
    def test_homepage_from_first_url(self, mock_fetch):
        """Homepage is the first comma-separated URL."""
        mock_fetch.return_value = SAMPLE_CRAN_RESPONSE
        result = adapter.fetch_metadata("ggplot2")
        assert result is not None
        assert result.homepage == "https://ggplot2.tidyverse.org"

    @patch("mf.packages.registries.cran.fetch_json")
    def test_install_command(self, mock_fetch):
        """Install command uses install.packages()."""
        mock_fetch.return_value = SAMPLE_CRAN_RESPONSE
        result = adapter.fetch_metadata("ggplot2")
        assert result is not None
        assert result.install_command == "install.packages('ggplot2')"

    @patch("mf.packages.registries.cran.fetch_json")
    def test_registry_url(self, mock_fetch):
        """Registry URL points to CRAN package page."""
        mock_fetch.return_value = SAMPLE_CRAN_RESPONSE
        result = adapter.fetch_metadata("ggplot2")
        assert result is not None
        assert result.registry_url == "https://cran.r-project.org/package=ggplot2"

    @patch("mf.packages.registries.cran.fetch_json")
    def test_downloads_always_none(self, mock_fetch):
        """Downloads are always None (CRAN doesn't provide via crandb)."""
        mock_fetch.return_value = SAMPLE_CRAN_RESPONSE
        result = adapter.fetch_metadata("ggplot2")
        assert result is not None
        assert result.downloads is None

    @patch("mf.packages.registries.cran.fetch_json")
    def test_last_updated_parsed(self, mock_fetch):
        """Date/Publication is parsed into last_updated."""
        mock_fetch.return_value = SAMPLE_CRAN_RESPONSE
        result = adapter.fetch_metadata("ggplot2")
        assert result is not None
        assert result.last_updated is not None
        assert result.last_updated.year == 2024
        assert result.last_updated.month == 2
        assert result.last_updated.day == 23

    @patch("mf.packages.registries.cran.fetch_json")
    def test_versions_extracted(self, mock_fetch):
        """Versions come from the versions dict keys."""
        mock_fetch.return_value = SAMPLE_CRAN_RESPONSE
        result = adapter.fetch_metadata("ggplot2")
        assert result is not None
        assert result.versions is not None
        assert "3.5.0" in result.versions
        assert "3.4.4" in result.versions


# ---------------------------------------------------------------------------
# License cleaning
# ---------------------------------------------------------------------------


class TestLicenseCleaning:
    """Tests for license string cleanup."""

    @patch("mf.packages.registries.cran.fetch_json")
    def test_license_cleaned(self, mock_fetch):
        """'+ file LICENSE' is stripped from license."""
        mock_fetch.return_value = SAMPLE_CRAN_RESPONSE
        result = adapter.fetch_metadata("ggplot2")
        assert result is not None
        assert result.license == "MIT"

    def test_clean_license_removes_file_license(self):
        """_clean_license strips '+ file LICENSE'."""
        assert _clean_license("MIT + file LICENSE") == "MIT"

    def test_clean_license_removes_file_licence(self):
        """_clean_license strips '+ file LICENCE' (British spelling)."""
        assert _clean_license("GPL-3 + file LICENCE") == "GPL-3"

    def test_clean_license_no_suffix(self):
        """_clean_license leaves clean license strings unchanged."""
        assert _clean_license("Apache-2.0") == "Apache-2.0"

    def test_clean_license_none(self):
        """_clean_license returns None for None input."""
        assert _clean_license(None) is None

    def test_clean_license_empty(self):
        """_clean_license returns None for empty string."""
        assert _clean_license("") is None

    @patch("mf.packages.registries.cran.fetch_json")
    def test_license_without_file_suffix(self, mock_fetch):
        """License without '+ file LICENSE' passes through cleanly."""
        response = dict(SAMPLE_CRAN_RESPONSE)
        response["License"] = "GPL-2 | GPL-3"
        mock_fetch.return_value = response
        result = adapter.fetch_metadata("test-pkg")
        assert result is not None
        assert result.license == "GPL-2 | GPL-3"


# ---------------------------------------------------------------------------
# Failure cases
# ---------------------------------------------------------------------------


class TestFetchMetadataFailure:
    """Tests for fetch_metadata returning None."""

    @patch("mf.packages.registries.cran.fetch_json")
    def test_returns_none_when_fetch_fails(self, mock_fetch):
        """fetch_metadata returns None when crandb API call fails."""
        mock_fetch.return_value = None
        result = adapter.fetch_metadata("nonexistent-package")
        assert result is None

    @patch("mf.packages.registries.cran.fetch_json")
    def test_returns_none_when_error_in_response(self, mock_fetch):
        """fetch_metadata returns None when response contains 'error' key."""
        mock_fetch.return_value = {"error": "not_found", "reason": "missing"}
        result = adapter.fetch_metadata("nonexistent-package")
        assert result is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    @patch("mf.packages.registries.cran.fetch_json")
    def test_no_url_field(self, mock_fetch):
        """Homepage is None when URL field is absent."""
        response = dict(SAMPLE_CRAN_RESPONSE)
        del response["URL"]
        mock_fetch.return_value = response
        result = adapter.fetch_metadata("test-pkg")
        assert result is not None
        assert result.homepage is None

    @patch("mf.packages.registries.cran.fetch_json")
    def test_no_date_publication(self, mock_fetch):
        """last_updated is None when Date/Publication is absent."""
        response = dict(SAMPLE_CRAN_RESPONSE)
        del response["Date/Publication"]
        mock_fetch.return_value = response
        result = adapter.fetch_metadata("test-pkg")
        assert result is not None
        assert result.last_updated is None

    @patch("mf.packages.registries.cran.fetch_json")
    def test_no_versions_dict(self, mock_fetch):
        """versions is None when versions field is not a dict."""
        response = dict(SAMPLE_CRAN_RESPONSE)
        del response["versions"]
        mock_fetch.return_value = response
        result = adapter.fetch_metadata("test-pkg")
        assert result is not None
        assert result.versions is None

    @patch("mf.packages.registries.cran.fetch_json")
    def test_crandb_url_constructed_correctly(self, mock_fetch):
        """The crandb URL includes the package name."""
        mock_fetch.return_value = None
        adapter.fetch_metadata("dplyr")
        mock_fetch.assert_called_once_with("https://crandb.r-pkg.org/dplyr")

    @patch("mf.packages.registries.cran.fetch_json")
    def test_date_fallback_to_date_only(self, mock_fetch):
        """Falls back to date-only parsing when full datetime fails."""
        response = dict(SAMPLE_CRAN_RESPONSE)
        response["Date/Publication"] = "2024-03-15"
        mock_fetch.return_value = response
        result = adapter.fetch_metadata("test-pkg")
        assert result is not None
        assert result.last_updated is not None
        assert result.last_updated.year == 2024
        assert result.last_updated.month == 3

    @patch("mf.packages.registries.cran.fetch_json")
    def test_date_completely_unparseable(self, mock_fetch):
        """last_updated is None when date is completely invalid."""
        response = dict(SAMPLE_CRAN_RESPONSE)
        response["Date/Publication"] = "not-a-date-at-all"
        mock_fetch.return_value = response
        result = adapter.fetch_metadata("test-pkg")
        assert result is not None
        assert result.last_updated is None

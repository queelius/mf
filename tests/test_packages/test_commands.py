"""Tests for packages CLI commands."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from mf.cli import main


@pytest.fixture
def pkg_db_file(mock_site_root):
    """Create a packages_db.json with sample entries."""
    data = {
        "_comment": "Package metadata database.",
        "_schema_version": "1.0",
        "_example": {"name": "example"},
        "requests": {
            "name": "requests",
            "registry": "pypi",
            "description": "HTTP for Humans",
            "latest_version": "2.31.0",
            "featured": True,
            "tags": ["python", "http"],
            "project": "requests-project",
            "install_command": "pip install requests",
            "registry_url": "https://pypi.org/project/requests/",
            "license": "Apache-2.0",
            "downloads": 5000000,
            "last_synced": "2026-01-15T10:00:00",
        },
        "reliabilitytheory": {
            "name": "ReliabilityTheory",
            "registry": "cran",
            "description": "Reliability theory tools for R",
            "latest_version": "0.3.0",
            "featured": False,
            "tags": ["r", "statistics"],
            "project": None,
            "install_command": "install.packages('ReliabilityTheory')",
            "registry_url": "https://cran.r-project.org/package=ReliabilityTheory",
            "license": "GPL-2",
            "downloads": 1200,
            "last_synced": "2026-01-10T08:00:00",
        },
    }
    db_path = mock_site_root / ".mf" / "packages_db.json"
    db_path.write_text(json.dumps(data, indent=2))
    return db_path


@pytest.fixture
def empty_pkg_db(mock_site_root):
    """Create an empty packages_db.json."""
    data = {
        "_comment": "Package metadata database.",
        "_schema_version": "1.0",
        "_example": {"name": "example"},
    }
    db_path = mock_site_root / ".mf" / "packages_db.json"
    db_path.write_text(json.dumps(data, indent=2))
    return db_path


class TestPackagesList:
    """Tests for the packages list command."""

    def test_list_empty(self, empty_pkg_db):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "list"])
        assert result.exit_code == 0
        assert "No packages found" in result.output

    def test_list_with_packages(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "list"])
        assert result.exit_code == 0
        assert "requests" in result.output
        assert "ReliabilityTheory" in result.output
        assert "2 found" in result.output

    def test_list_json(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2
        slugs = {item["slug"] for item in data}
        assert "requests" in slugs
        assert "reliabilitytheory" in slugs

    def test_list_filter_by_registry(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "list", "--registry", "pypi"])
        assert result.exit_code == 0
        assert "requests" in result.output
        assert "ReliabilityTheory" not in result.output

    def test_list_filter_by_tag(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "list", "-t", "statistics"])
        assert result.exit_code == 0
        assert "ReliabilityTheory" in result.output
        assert "1 found" in result.output

    def test_list_featured(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "list", "--featured"])
        assert result.exit_code == 0
        assert "requests" in result.output
        assert "1 found" in result.output


class TestPackagesShow:
    """Tests for the packages show command."""

    def test_show_existing(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "show", "requests"])
        assert result.exit_code == 0
        assert "requests" in result.output
        assert "HTTP for Humans" in result.output
        assert "pypi" in result.output

    def test_show_not_found(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "show", "nonexistent"])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestPackagesAdd:
    """Tests for the packages add command."""

    def test_add_no_sync(self, empty_pkg_db, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "add", "my-pkg", "--registry", "pypi", "--no-sync"]
        )
        assert result.exit_code == 0
        assert "Added package" in result.output
        assert "my-pkg" in result.output

        # Verify it's in the database
        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert "my-pkg" in db_data
        assert db_data["my-pkg"]["registry"] == "pypi"

    def test_add_with_project(self, empty_pkg_db, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "packages", "add", "my-pkg",
                "--registry", "pypi",
                "--project", "my-project",
                "--no-sync",
            ],
        )
        assert result.exit_code == 0
        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert db_data["my-pkg"]["project"] == "my-project"

    def test_add_already_exists(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "add", "requests", "--registry", "pypi", "--no-sync"]
        )
        assert result.exit_code == 0
        assert "already exists" in result.output.lower()


class TestPackagesRemove:
    """Tests for the packages remove command."""

    def test_remove_existing(self, pkg_db_file, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "remove", "requests", "-y"])
        assert result.exit_code == 0
        assert "Removed package" in result.output

        # Verify it's gone from the database
        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert "requests" not in db_data

    def test_remove_not_found(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "remove", "nonexistent", "-y"])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestPackagesSetUnset:
    """Tests for the packages set and unset commands."""

    def test_set_field(self, pkg_db_file, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "set", "requests", "description", "A new description"]
        )
        assert result.exit_code == 0
        assert "Saved to packages_db.json" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert db_data["requests"]["description"] == "A new description"

    def test_unset_field(self, pkg_db_file, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "unset", "requests", "license"]
        )
        assert result.exit_code == 0
        assert "Saved to packages_db.json" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert "license" not in db_data["requests"]

    def test_set_unknown_field(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "set", "requests", "nonexistent_field", "value"]
        )
        assert result.exit_code == 0
        assert "Unknown field" in result.output


class TestPackagesGenerate:
    """Tests for the packages generate command."""

    def test_generate_all(self, pkg_db_file, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "generate"])
        assert result.exit_code == 0
        assert "Generated" in result.output

        # Verify content files were created
        requests_content = mock_site_root / "content" / "packages" / "requests" / "index.md"
        assert requests_content.exists()

        content = requests_content.read_text()
        assert 'title: "requests"' in content
        assert 'registry: "pypi"' in content

    def test_generate_single(self, pkg_db_file, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "generate", "requests"])
        assert result.exit_code == 0

        requests_content = mock_site_root / "content" / "packages" / "requests" / "index.md"
        assert requests_content.exists()

        # The other package should NOT be generated
        other_content = (
            mock_site_root / "content" / "packages" / "reliabilitytheory" / "index.md"
        )
        assert not other_content.exists()

    def test_generate_not_found(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "generate", "nonexistent"])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestPackagesFeature:
    """Tests for the packages feature command."""

    def test_feature_on(self, pkg_db_file, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "feature", "reliabilitytheory"]
        )
        assert result.exit_code == 0
        assert "Saved to packages_db.json" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert db_data["reliabilitytheory"]["featured"] is True

    def test_feature_off(self, pkg_db_file, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "feature", "requests", "--off"]
        )
        assert result.exit_code == 0
        assert "Saved to packages_db.json" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert db_data["requests"]["featured"] is False


class TestPackagesTag:
    """Tests for the packages tag command."""

    def test_tag_add(self, pkg_db_file, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "tag", "requests", "--add", "networking"]
        )
        assert result.exit_code == 0
        assert "Saved to packages_db.json" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert "networking" in db_data["requests"]["tags"]

    def test_tag_remove(self, pkg_db_file, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "tag", "requests", "--remove", "http"]
        )
        assert result.exit_code == 0

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert "http" not in db_data["requests"]["tags"]

    def test_tag_set(self, pkg_db_file, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "tag", "requests", "--set", "a,b,c"]
        )
        assert result.exit_code == 0

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert db_data["requests"]["tags"] == ["a", "b", "c"]

    def test_tag_no_options(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "tag", "requests"])
        assert result.exit_code == 0
        assert "Specify --add, --remove, or --set" in result.output


class TestPackagesFields:
    """Tests for the packages fields command."""

    def test_fields_list(self, mock_site_root):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "fields"])
        assert result.exit_code == 0
        assert "name" in result.output
        assert "registry" in result.output
        assert "description" in result.output
        assert "featured" in result.output
        assert "tags" in result.output


class TestPackagesStats:
    """Tests for the packages stats command."""

    def test_stats(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "stats"])
        assert result.exit_code == 0
        assert "2" in result.output  # total
        assert "1" in result.output  # featured
        assert "pypi" in result.output
        assert "cran" in result.output


class TestPackagesSync:
    """Tests for the packages sync command."""

    def test_sync_single(self, pkg_db_file, mock_site_root):
        """Test syncing a single package with mocked adapter."""
        from mf.packages.registries import PackageMetadata

        fake_metadata = PackageMetadata(
            name="requests",
            registry="pypi",
            latest_version="2.32.0",
            description="HTTP for Humans - Updated",
            install_command="pip install requests",
            registry_url="https://pypi.org/project/requests/",
            license="Apache-2.0",
            downloads=6000000,
        )

        mock_adapter = MagicMock()
        mock_adapter.name = "pypi"
        mock_adapter.fetch_metadata.return_value = fake_metadata

        with patch(
            "mf.packages.registries.discover_registries",
            return_value={"pypi": mock_adapter, "cran": MagicMock()},
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["packages", "sync", "requests"])

        assert result.exit_code == 0
        assert "Updated" in result.output or "No version change" in result.output
        mock_adapter.fetch_metadata.assert_called_once_with("requests")

        # Verify the db was updated
        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert db_data["requests"]["latest_version"] == "2.32.0"

    def test_sync_all(self, pkg_db_file, mock_site_root):
        """Test syncing all packages with mocked adapters."""
        from mf.packages.registries import PackageMetadata

        pypi_meta = PackageMetadata(
            name="requests",
            registry="pypi",
            latest_version="2.31.0",
            description="HTTP for Humans",
        )
        cran_meta = PackageMetadata(
            name="ReliabilityTheory",
            registry="cran",
            latest_version="0.4.0",
            description="Reliability theory tools for R",
        )

        mock_pypi = MagicMock()
        mock_pypi.name = "pypi"
        mock_pypi.fetch_metadata.return_value = pypi_meta

        mock_cran = MagicMock()
        mock_cran.name = "cran"
        mock_cran.fetch_metadata.return_value = cran_meta

        with patch(
            "mf.packages.registries.discover_registries",
            return_value={"pypi": mock_pypi, "cran": mock_cran},
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["packages", "sync"])

        assert result.exit_code == 0
        assert "2 synced" in result.output

    def test_sync_not_found(self, pkg_db_file):
        runner = CliRunner()
        result = runner.invoke(main, ["packages", "sync", "nonexistent"])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()

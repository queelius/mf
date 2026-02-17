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

    def test_add_with_sync_success(self, empty_pkg_db, mock_site_root):
        """Add with registry sync fetches and stores metadata."""
        from mf.packages.registries import PackageMetadata

        fake_metadata = PackageMetadata(
            name="requests",
            registry="pypi",
            latest_version="2.31.0",
            description="HTTP for Humans.",
            install_command="pip install requests",
            registry_url="https://pypi.org/project/requests/",
            license="Apache-2.0",
            downloads=150000000,
        )
        mock_adapter = MagicMock()
        mock_adapter.name = "pypi"
        mock_adapter.fetch_metadata.return_value = fake_metadata

        with patch(
            "mf.packages.registries.discover_registries",
            return_value={"pypi": mock_adapter},
        ):
            runner = CliRunner()
            result = runner.invoke(
                main, ["packages", "add", "requests", "--registry", "pypi"]
            )

        assert result.exit_code == 0
        assert "Fetched metadata" in result.output
        assert "Added package" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert db_data["requests"]["description"] == "HTTP for Humans."
        assert db_data["requests"]["latest_version"] == "2.31.0"
        assert db_data["requests"]["license"] == "Apache-2.0"
        assert db_data["requests"]["downloads"] == 150000000
        assert "last_synced" in db_data["requests"]

    def test_add_with_sync_not_found(self, empty_pkg_db, mock_site_root):
        """Add when registry returns None still adds minimal entry."""
        mock_adapter = MagicMock()
        mock_adapter.name = "pypi"
        mock_adapter.fetch_metadata.return_value = None

        with patch(
            "mf.packages.registries.discover_registries",
            return_value={"pypi": mock_adapter},
        ):
            runner = CliRunner()
            result = runner.invoke(
                main, ["packages", "add", "nonexistent-pkg", "--registry", "pypi"]
            )

        assert result.exit_code == 0
        assert "not found on pypi" in result.output.lower()
        assert "Added package" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert "nonexistent-pkg" in db_data
        assert db_data["nonexistent-pkg"]["registry"] == "pypi"

    def test_add_with_sync_exception(self, empty_pkg_db, mock_site_root):
        """Add when adapter raises exception still adds minimal entry."""
        mock_adapter = MagicMock()
        mock_adapter.name = "pypi"
        mock_adapter.fetch_metadata.side_effect = ConnectionError("network error")

        with patch(
            "mf.packages.registries.discover_registries",
            return_value={"pypi": mock_adapter},
        ):
            runner = CliRunner()
            result = runner.invoke(
                main, ["packages", "add", "my-pkg", "--registry", "pypi"]
            )

        assert result.exit_code == 0
        assert "could not fetch metadata" in result.output.lower()
        assert "Added package" in result.output

    def test_add_no_adapter_for_registry(self, empty_pkg_db, mock_site_root):
        """Add with no matching adapter prints warning."""
        with patch(
            "mf.packages.registries.discover_registries",
            return_value={},
        ):
            runner = CliRunner()
            result = runner.invoke(
                main, ["packages", "add", "my-pkg", "--registry", "pypi"]
            )

        assert result.exit_code == 0
        assert "No adapter available" in result.output
        assert "Added package" in result.output

    def test_add_dry_run(self, empty_pkg_db, mock_site_root):
        """Add with --dry-run does not save to database."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--dry-run", "packages", "add", "my-pkg", "--registry", "pypi", "--no-sync"],
        )
        assert result.exit_code == 0
        assert "Dry run" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert "my-pkg" not in db_data


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

    def test_remove_with_confirmation(self, pkg_db_file, mock_site_root):
        """Remove with confirmation prompt (user confirms 'y')."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "remove", "requests"], input="y\n"
        )
        assert result.exit_code == 0
        assert "Removed package" in result.output

    def test_remove_dry_run(self, pkg_db_file, mock_site_root):
        """Remove with --dry-run does not delete from database."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["--dry-run", "packages", "remove", "requests", "-y"]
        )
        assert result.exit_code == 0
        assert "Dry run" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert "requests" in db_data


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

    def test_set_coercion_error(self, pkg_db_file):
        """Set with invalid value type shows coercion error."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "set", "requests", "stars", "not-a-number"]
        )
        assert result.exit_code == 0
        # Should fail on coercion (stars is INT)
        assert "invalid" in result.output.lower() or "cannot" in result.output.lower() or "not" in result.output.lower()

    def test_set_validation_error(self, pkg_db_file):
        """Set with out-of-range value shows validation error."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "set", "requests", "stars", "10"]
        )
        assert result.exit_code == 0
        # stars has max_val=5
        assert "5" in result.output or "max" in result.output.lower()

    def test_set_dry_run(self, pkg_db_file, mock_site_root):
        """Set with --dry-run does not save to database."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--dry-run", "packages", "set", "requests", "description", "New desc"],
        )
        assert result.exit_code == 0
        assert "Dry run" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert db_data["requests"]["description"] == "HTTP for Humans"

    def test_unset_unknown_field(self, pkg_db_file):
        """Unset with unknown field name shows error."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "unset", "requests", "nonexistent_field"]
        )
        assert result.exit_code == 0
        assert "Unknown field" in result.output

    def test_unset_not_found_package(self, pkg_db_file):
        """Unset on nonexistent package shows error."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "unset", "nonexistent", "description"]
        )
        assert result.exit_code == 0
        # Should hit KeyError path
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_unset_field_not_set(self, pkg_db_file):
        """Unset on a field that was not set shows informational message."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["packages", "unset", "requests", "stars"]
        )
        assert result.exit_code == 0
        assert "was not set" in result.output

    def test_unset_dry_run(self, pkg_db_file, mock_site_root):
        """Unset with --dry-run does not save to database."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["--dry-run", "packages", "unset", "requests", "license"]
        )
        assert result.exit_code == 0
        assert "Dry run" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert "license" in db_data["requests"]


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

    def test_feature_dry_run(self, pkg_db_file, mock_site_root):
        """Feature with --dry-run does not save to database."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["--dry-run", "packages", "feature", "reliabilitytheory"]
        )
        assert result.exit_code == 0
        assert "Dry run" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert db_data["reliabilitytheory"]["featured"] is False


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

    def test_tag_dry_run(self, pkg_db_file, mock_site_root):
        """Tag with --dry-run does not save to database."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["--dry-run", "packages", "tag", "requests", "--add", "new-tag"]
        )
        assert result.exit_code == 0
        assert "Dry run" in result.output

        db_data = json.loads(
            (mock_site_root / ".mf" / "packages_db.json").read_text()
        )
        assert "new-tag" not in db_data["requests"]["tags"]


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

    def test_sync_empty_database(self, empty_pkg_db):
        """Syncing an empty database shows 'No packages to sync'."""
        from mf.packages.registries import PackageMetadata

        with patch(
            "mf.packages.registries.discover_registries",
            return_value={"pypi": MagicMock()},
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["packages", "sync"])

        assert result.exit_code == 0
        assert "No packages to sync" in result.output

    def test_sync_no_registry_set(self, mock_site_root):
        """Package with no registry field is skipped during sync."""
        import json as json_module

        data = {
            "_comment": "test",
            "_schema_version": "1.0",
            "_example": {"name": "example"},
            "no-reg": {"name": "no-reg"},
        }
        db_path = mock_site_root / ".mf" / "packages_db.json"
        db_path.write_text(json_module.dumps(data))

        with patch(
            "mf.packages.registries.discover_registries",
            return_value={"pypi": MagicMock()},
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["packages", "sync", "no-reg"])

        assert result.exit_code == 0
        assert "no registry set" in result.output

    def test_sync_no_adapter_for_registry(self, mock_site_root):
        """Package with unknown registry is skipped during sync."""
        import json as json_module

        data = {
            "_comment": "test",
            "_schema_version": "1.0",
            "_example": {"name": "example"},
            "mypkg": {"name": "mypkg", "registry": "homebrew"},
        }
        db_path = mock_site_root / ".mf" / "packages_db.json"
        db_path.write_text(json_module.dumps(data))

        with patch(
            "mf.packages.registries.discover_registries",
            return_value={"pypi": MagicMock()},
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["packages", "sync", "mypkg"])

        assert result.exit_code == 0
        assert "no adapter for registry" in result.output

    def test_sync_registry_returns_none(self, pkg_db_file):
        """Package not found on registry during sync counts as failed."""
        mock_adapter = MagicMock()
        mock_adapter.name = "pypi"
        mock_adapter.fetch_metadata.return_value = None

        with patch(
            "mf.packages.registries.discover_registries",
            return_value={"pypi": mock_adapter, "cran": MagicMock()},
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["packages", "sync", "requests"])

        assert result.exit_code == 0
        assert "Not found on" in result.output

    def test_sync_adapter_raises_exception(self, pkg_db_file):
        """Exception during fetch counts as failed."""
        mock_adapter = MagicMock()
        mock_adapter.name = "pypi"
        mock_adapter.fetch_metadata.side_effect = ConnectionError("timeout")

        with patch(
            "mf.packages.registries.discover_registries",
            return_value={"pypi": mock_adapter, "cran": MagicMock()},
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["packages", "sync", "requests"])

        assert result.exit_code == 0
        assert "Error" in result.output
        assert "1 failed" in result.output

    def test_sync_dry_run_no_mutation(self, pkg_db_file, mock_site_root):
        """Dry-run sync does not mutate the database file."""
        from mf.packages.registries import PackageMetadata

        original_data = (mock_site_root / ".mf" / "packages_db.json").read_text()

        fake_metadata = PackageMetadata(
            name="requests",
            registry="pypi",
            latest_version="99.0.0",
            description="Updated",
        )
        mock_adapter = MagicMock()
        mock_adapter.name = "pypi"
        mock_adapter.fetch_metadata.return_value = fake_metadata

        with patch(
            "mf.packages.registries.discover_registries",
            return_value={"pypi": mock_adapter, "cran": MagicMock()},
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["--dry-run", "packages", "sync", "requests"])

        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "Would update" in result.output

        # Database file should be unchanged
        assert (mock_site_root / ".mf" / "packages_db.json").read_text() == original_data

    def test_sync_dry_run_no_version_change(self, pkg_db_file, mock_site_root):
        """Dry-run sync shows 'No version change' when version matches."""
        from mf.packages.registries import PackageMetadata

        fake_metadata = PackageMetadata(
            name="requests",
            registry="pypi",
            latest_version="2.31.0",
            description="HTTP for Humans",
        )
        mock_adapter = MagicMock()
        mock_adapter.name = "pypi"
        mock_adapter.fetch_metadata.return_value = fake_metadata

        with patch(
            "mf.packages.registries.discover_registries",
            return_value={"pypi": mock_adapter, "cran": MagicMock()},
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["--dry-run", "packages", "sync", "requests"])

        assert result.exit_code == 0
        assert "No version change" in result.output

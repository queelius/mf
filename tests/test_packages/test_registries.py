"""Tests for registry adapter protocol and discovery."""

from datetime import datetime
from pathlib import Path

import pytest

from mf.packages.registries import (
    PackageMetadata,
    RegistryAdapter,
    _load_adapter_from_file,
    discover_registries,
)


# ---------------------------------------------------------------------------
# PackageMetadata dataclass
# ---------------------------------------------------------------------------


class TestPackageMetadata:
    """Tests for the PackageMetadata dataclass."""

    def test_required_fields(self):
        """PackageMetadata requires name, registry, latest_version, description."""
        meta = PackageMetadata(
            name="requests",
            registry="pypi",
            latest_version="2.31.0",
            description="HTTP library",
        )
        assert meta.name == "requests"
        assert meta.registry == "pypi"
        assert meta.latest_version == "2.31.0"
        assert meta.description == "HTTP library"

    def test_optional_fields_default_to_none(self):
        """All optional fields default to None."""
        meta = PackageMetadata(
            name="test",
            registry="pypi",
            latest_version="1.0",
            description="A test",
        )
        assert meta.homepage is None
        assert meta.license is None
        assert meta.downloads is None
        assert meta.versions is None
        assert meta.install_command is None
        assert meta.registry_url is None
        assert meta.last_updated is None

    def test_optional_fields_can_be_set(self):
        """Optional fields accept values."""
        now = datetime(2025, 1, 15, 12, 0, 0)
        meta = PackageMetadata(
            name="click",
            registry="pypi",
            latest_version="8.1.7",
            description="CLI framework",
            homepage="https://click.palletsprojects.com",
            license="BSD-3-Clause",
            downloads=50000000,
            versions=["8.1.7", "8.1.6", "8.1.5"],
            install_command="pip install click",
            registry_url="https://pypi.org/project/click/",
            last_updated=now,
        )
        assert meta.homepage == "https://click.palletsprojects.com"
        assert meta.license == "BSD-3-Clause"
        assert meta.downloads == 50000000
        assert meta.versions == ["8.1.7", "8.1.6", "8.1.5"]
        assert meta.install_command == "pip install click"
        assert meta.registry_url == "https://pypi.org/project/click/"
        assert meta.last_updated == now

    def test_missing_required_field_raises(self):
        """Omitting a required field raises TypeError."""
        with pytest.raises(TypeError):
            PackageMetadata(  # type: ignore[call-arg]
                name="test",
                registry="pypi",
                latest_version="1.0",
                # description is missing
            )


# ---------------------------------------------------------------------------
# RegistryAdapter Protocol
# ---------------------------------------------------------------------------


class TestRegistryAdapterProtocol:
    """Tests for the RegistryAdapter protocol."""

    def test_protocol_is_runtime_checkable(self):
        """RegistryAdapter can be used with isinstance checks."""

        class ValidAdapter:
            name = "test"

            def fetch_metadata(self, package_name: str) -> PackageMetadata | None:
                return None

        adapter = ValidAdapter()
        assert isinstance(adapter, RegistryAdapter)

    def test_missing_name_fails_isinstance(self):
        """Object without name attribute is not a RegistryAdapter."""

        class NoName:
            def fetch_metadata(self, package_name: str) -> PackageMetadata | None:
                return None

        assert not isinstance(NoName(), RegistryAdapter)

    def test_missing_fetch_metadata_fails_isinstance(self):
        """Object without fetch_metadata is not a RegistryAdapter."""

        class NoFetch:
            name = "test"

        assert not isinstance(NoFetch(), RegistryAdapter)


# ---------------------------------------------------------------------------
# _load_adapter_from_file
# ---------------------------------------------------------------------------


class TestLoadAdapterFromFile:
    """Tests for loading adapters from .py files."""

    def test_loads_valid_adapter(self, tmp_path):
        """Valid adapter file is loaded correctly."""
        adapter_file = tmp_path / "test_reg.py"
        adapter_file.write_text(
            'class MyAdapter:\n'
            '    name = "test_reg"\n'
            '    def fetch_metadata(self, package_name):\n'
            '        return None\n'
            '\n'
            'adapter = MyAdapter()\n'
        )
        result = _load_adapter_from_file(adapter_file)
        assert result is not None
        assert result.name == "test_reg"
        assert callable(result.fetch_metadata)

    def test_returns_none_for_no_adapter_attribute(self, tmp_path):
        """File without 'adapter' attribute returns None."""
        adapter_file = tmp_path / "no_adapter.py"
        adapter_file.write_text("x = 42\n")
        assert _load_adapter_from_file(adapter_file) is None

    def test_returns_none_for_missing_name(self, tmp_path):
        """Adapter without 'name' attribute returns None."""
        adapter_file = tmp_path / "no_name.py"
        adapter_file.write_text(
            'class Bad:\n'
            '    def fetch_metadata(self, pkg):\n'
            '        return None\n'
            '\n'
            'adapter = Bad()\n'
        )
        assert _load_adapter_from_file(adapter_file) is None

    def test_returns_none_for_missing_fetch_metadata(self, tmp_path):
        """Adapter without 'fetch_metadata' returns None."""
        adapter_file = tmp_path / "no_fetch.py"
        adapter_file.write_text(
            'class Bad:\n'
            '    name = "bad"\n'
            '\n'
            'adapter = Bad()\n'
        )
        assert _load_adapter_from_file(adapter_file) is None

    def test_returns_none_for_syntax_error(self, tmp_path):
        """File with syntax error returns None gracefully."""
        adapter_file = tmp_path / "broken.py"
        adapter_file.write_text("def broken(\n")
        assert _load_adapter_from_file(adapter_file) is None

    def test_returns_none_for_non_callable_fetch_metadata(self, tmp_path):
        """Adapter with non-callable fetch_metadata returns None."""
        adapter_file = tmp_path / "not_callable.py"
        adapter_file.write_text(
            'class Bad:\n'
            '    name = "bad"\n'
            '    fetch_metadata = "not a function"\n'
            '\n'
            'adapter = Bad()\n'
        )
        assert _load_adapter_from_file(adapter_file) is None


# ---------------------------------------------------------------------------
# discover_registries
# ---------------------------------------------------------------------------


class TestDiscoverRegistries:
    """Tests for registry discovery."""

    def test_discovers_builtin_pypi(self):
        """Built-in pypi adapter is discovered."""
        regs = discover_registries()
        assert "pypi" in regs
        assert regs["pypi"].name == "pypi"
        assert callable(regs["pypi"].fetch_metadata)

    def test_discovers_builtin_cran(self):
        """Built-in cran adapter is discovered."""
        regs = discover_registries()
        assert "cran" in regs
        assert regs["cran"].name == "cran"
        assert callable(regs["cran"].fetch_metadata)

    def test_user_dir_overrides_builtin(self, tmp_path):
        """User directory adapter overrides built-in with same name."""
        custom_pypi = tmp_path / "pypi.py"
        custom_pypi.write_text(
            'class CustomPyPI:\n'
            '    name = "pypi"\n'
            '    custom = True\n'
            '    def fetch_metadata(self, package_name):\n'
            '        return None\n'
            '\n'
            'adapter = CustomPyPI()\n'
        )
        regs = discover_registries(extra_dirs=[tmp_path])
        assert "pypi" in regs
        # The user adapter should have the custom attribute
        assert getattr(regs["pypi"], "custom", False) is True

    def test_user_dir_adds_new_registry(self, tmp_path):
        """User directory can add new registries."""
        homebrew_file = tmp_path / "homebrew.py"
        homebrew_file.write_text(
            'class HomebrewAdapter:\n'
            '    name = "homebrew"\n'
            '    def fetch_metadata(self, package_name):\n'
            '        return None\n'
            '\n'
            'adapter = HomebrewAdapter()\n'
        )
        regs = discover_registries(extra_dirs=[tmp_path])
        assert "homebrew" in regs
        assert regs["homebrew"].name == "homebrew"
        # Built-ins should still be present
        assert "pypi" in regs
        assert "cran" in regs

    def test_init_files_are_skipped(self, tmp_path):
        """Files starting with _ (like __init__.py) are skipped."""
        init_file = tmp_path / "__init__.py"
        init_file.write_text(
            'class InitAdapter:\n'
            '    name = "init_adapter"\n'
            '    def fetch_metadata(self, package_name):\n'
            '        return None\n'
            '\n'
            'adapter = InitAdapter()\n'
        )
        # Use only the tmp_path (no built-in dir) to isolate the test
        regs = discover_registries(extra_dirs=[tmp_path])
        assert "init_adapter" not in regs

    def test_nonexistent_extra_dir_is_skipped(self, tmp_path):
        """Non-existent extra directories are skipped without error."""
        nonexistent = tmp_path / "does_not_exist"
        regs = discover_registries(extra_dirs=[nonexistent])
        # Should still have built-ins
        assert "pypi" in regs
        assert "cran" in regs

    def test_invalid_files_in_user_dir_are_skipped(self, tmp_path):
        """Invalid adapter files are skipped without affecting others."""
        # Valid adapter
        valid = tmp_path / "valid.py"
        valid.write_text(
            'class ValidAdapter:\n'
            '    name = "valid"\n'
            '    def fetch_metadata(self, package_name):\n'
            '        return None\n'
            '\n'
            'adapter = ValidAdapter()\n'
        )
        # Invalid adapter (syntax error)
        broken = tmp_path / "broken.py"
        broken.write_text("def broken(\n")

        regs = discover_registries(extra_dirs=[tmp_path])
        assert "valid" in regs
        assert "pypi" in regs  # Built-ins still present

    def test_each_builtin_adapter_is_valid(self):
        """Each built-in adapter has name (str) and callable fetch_metadata."""
        regs = discover_registries()
        for reg_name, adapter in regs.items():
            assert isinstance(adapter.name, str), f"{reg_name}: name is not str"
            assert callable(
                adapter.fetch_metadata
            ), f"{reg_name}: fetch_metadata not callable"
            assert adapter.name == reg_name, f"adapter.name '{adapter.name}' != key '{reg_name}'"

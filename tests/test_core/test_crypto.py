"""Tests for mf.core.crypto module."""

import pytest
from pathlib import Path

from mf.core.crypto import compute_file_hash, verify_file_hash, compute_directory_hash


class TestComputeFileHash:
    """Tests for compute_file_hash function."""

    def test_computes_sha256_hash(self, tmp_path):
        """Test SHA256 hash computation."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = compute_file_hash(test_file)

        # Known SHA256 of "Hello, World!"
        expected = "sha256:dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        assert result == expected

    def test_hash_without_prefix(self, tmp_path):
        """Test hash without algorithm prefix."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = compute_file_hash(test_file, prefix=False)

        assert not result.startswith("sha256:")
        assert len(result) == 64  # SHA256 hex length

    def test_different_content_different_hash(self, tmp_path):
        """Test that different content produces different hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content A")
        file2.write_text("Content B")

        hash1 = compute_file_hash(file1)
        hash2 = compute_file_hash(file2)

        assert hash1 != hash2

    def test_same_content_same_hash(self, tmp_path):
        """Test that same content produces same hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        content = "Same content"
        file1.write_text(content)
        file2.write_text(content)

        hash1 = compute_file_hash(file1)
        hash2 = compute_file_hash(file2)

        assert hash1 == hash2

    def test_raises_for_nonexistent_file(self, tmp_path):
        """Test that FileNotFoundError is raised for missing file."""
        with pytest.raises(FileNotFoundError):
            compute_file_hash(tmp_path / "nonexistent.txt")

    def test_raises_for_invalid_algorithm(self, tmp_path):
        """Test that ValueError is raised for unsupported algorithm."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        with pytest.raises(ValueError):
            compute_file_hash(test_file, algorithm="invalid_algo")


class TestVerifyFileHash:
    """Tests for verify_file_hash function."""

    def test_verifies_correct_hash(self, tmp_path):
        """Test verification with correct hash."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        expected_hash = "sha256:dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        result = verify_file_hash(test_file, expected_hash)

        assert result is True

    def test_fails_for_wrong_hash(self, tmp_path):
        """Test verification fails with wrong hash."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        wrong_hash = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        result = verify_file_hash(test_file, wrong_hash)

        assert result is False

    def test_verifies_hash_without_prefix(self, tmp_path):
        """Test verification with hash without prefix."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        # Hash without prefix (assumes SHA256)
        expected_hash = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        result = verify_file_hash(test_file, expected_hash)

        assert result is True


class TestComputeDirectoryHash:
    """Tests for compute_directory_hash function."""

    def test_computes_hash_for_directory(self, tmp_path):
        """Test hash computation for directory."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        (test_dir / "file1.txt").write_text("Content 1")
        (test_dir / "file2.txt").write_text("Content 2")

        result = compute_directory_hash(test_dir)

        assert result.startswith("sha256:")
        assert len(result) == 7 + 64  # "sha256:" + 64 hex chars

    def test_same_content_same_hash(self, tmp_path):
        """Test that directories with same content have same hash."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        (dir1 / "file.txt").write_text("Same content")
        (dir2 / "file.txt").write_text("Same content")

        hash1 = compute_directory_hash(dir1)
        hash2 = compute_directory_hash(dir2)

        assert hash1 == hash2

    def test_different_content_different_hash(self, tmp_path):
        """Test that directories with different content have different hash."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        (dir1 / "file.txt").write_text("Content A")
        (dir2 / "file.txt").write_text("Content B")

        hash1 = compute_directory_hash(dir1)
        hash2 = compute_directory_hash(dir2)

        assert hash1 != hash2

    def test_different_filenames_different_hash(self, tmp_path):
        """Test that same content but different filenames produce different hash."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        (dir1 / "a.txt").write_text("Same content")
        (dir2 / "b.txt").write_text("Same content")

        hash1 = compute_directory_hash(dir1)
        hash2 = compute_directory_hash(dir2)

        assert hash1 != hash2

    def test_handles_nested_directories(self, tmp_path):
        """Test hash computation with nested directories."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        (test_dir / "subdir").mkdir()
        (test_dir / "file.txt").write_text("Root file")
        (test_dir / "subdir" / "nested.txt").write_text("Nested file")

        result = compute_directory_hash(test_dir)

        assert result.startswith("sha256:")

    def test_raises_for_nonexistent_directory(self, tmp_path):
        """Test that FileNotFoundError is raised for missing directory."""
        with pytest.raises(FileNotFoundError):
            compute_directory_hash(tmp_path / "nonexistent")

    def test_raises_for_file_path(self, tmp_path):
        """Test that ValueError is raised when path is a file."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("Not a directory")

        with pytest.raises(ValueError):
            compute_directory_hash(test_file)

    def test_hash_without_prefix(self, tmp_path):
        """Test hash without algorithm prefix."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("Content")

        result = compute_directory_hash(test_dir, prefix=False)

        assert not result.startswith("sha256:")
        assert len(result) == 64

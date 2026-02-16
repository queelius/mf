"""
Cryptographic utilities.

Provides hash computation for file integrity checking.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_file_hash(
    file_path: Path,
    algorithm: str = "sha256",
    chunk_size: int = 8192,
    prefix: bool = True,
) -> str:
    """Compute hash of a file using chunked reading.

    Args:
        file_path: Path to file to hash
        algorithm: Hash algorithm (sha256, sha1, md5, etc.)
        chunk_size: Size of chunks to read at a time
        prefix: Include algorithm prefix (e.g., "sha256:abc123...")

    Returns:
        Hash string, optionally prefixed with algorithm name

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If algorithm is not supported
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Cannot hash non-existent file: {file_path}")

    try:
        hasher = hashlib.new(algorithm)
    except ValueError as e:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}") from e

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hasher.update(chunk)

    digest = hasher.hexdigest()
    return f"{algorithm}:{digest}" if prefix else digest


def verify_file_hash(file_path: Path, expected_hash: str) -> bool:
    """Verify a file's hash matches an expected value.

    Args:
        file_path: Path to file to verify
        expected_hash: Expected hash (with or without algorithm prefix)

    Returns:
        True if hash matches, False otherwise
    """
    # Parse expected hash to extract algorithm
    if ":" in expected_hash:
        algorithm, expected_digest = expected_hash.split(":", 1)
    else:
        algorithm = "sha256"
        expected_digest = expected_hash

    actual_hash = compute_file_hash(file_path, algorithm=algorithm, prefix=False)
    return actual_hash == expected_digest


def compute_directory_hash(
    dir_path: Path,
    algorithm: str = "sha256",
    prefix: bool = True,
) -> str:
    """Compute a combined hash for all files in a directory.

    Hashes all files recursively, sorted by path, to get a deterministic
    hash representing the directory's contents.

    Args:
        dir_path: Path to directory to hash
        algorithm: Hash algorithm (sha256, sha1, md5, etc.)
        prefix: Include algorithm prefix (e.g., "sha256:abc123...")

    Returns:
        Hash string representing directory contents

    Raises:
        FileNotFoundError: If directory doesn't exist
        ValueError: If path is not a directory
    """
    dir_path = Path(dir_path)
    if not dir_path.exists():
        raise FileNotFoundError(f"Cannot hash non-existent directory: {dir_path}")
    if not dir_path.is_dir():
        raise ValueError(f"Path is not a directory: {dir_path}")

    try:
        hasher = hashlib.new(algorithm)
    except ValueError as e:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}") from e

    # Get all files sorted by relative path for deterministic ordering
    all_files = sorted(dir_path.rglob("*"))

    for file_path in all_files:
        if file_path.is_file():
            # Include the relative path in the hash to detect renames
            rel_path = file_path.relative_to(dir_path)
            hasher.update(str(rel_path).encode("utf-8"))

            # Include file contents
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)

    digest = hasher.hexdigest()
    return f"{algorithm}:{digest}" if prefix else digest

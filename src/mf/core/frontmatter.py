"""Generic frontmatter parsing, hashing, and equality.

Lifted out of mf.series.frontmatter so non-series modules (notably the
render-drift engine in mf.core.drift) can compare a post's body and metadata
without importing series-specific ownership logic. The series module
re-exports these names for backward compatibility and layers its
ownership-tier logic on top.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import frontmatter


def parse_post(path: Path) -> tuple[dict[str, Any], str]:
    """Parse an index.md into (frontmatter_dict, body_text).

    Args:
        path: A post directory (containing index.md) or a path to a markdown
            file directly.

    Raises:
        FileNotFoundError: if the index.md is missing.
    """
    index_file = path / "index.md" if path.is_dir() else path
    if not index_file.exists():
        raise FileNotFoundError(f"No index.md at {index_file}")
    post = frontmatter.load(index_file)
    return dict(post.metadata), post.content


def parse_text(text: str) -> tuple[dict[str, Any], str]:
    """Parse an in-memory markdown string into (frontmatter_dict, body_text)."""
    post = frontmatter.loads(text)
    return dict(post.metadata), post.content


def compute_body_hash(path: Path) -> str:
    """SHA256 of only the body of a post, ignoring frontmatter."""
    _, body = parse_post(path)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def frontmatter_equal(source_fm: dict[str, Any], target_fm: dict[str, Any]) -> bool:
    """Strict semantic equality of parsed frontmatter dicts (key order irrelevant)."""
    return source_fm == target_fm

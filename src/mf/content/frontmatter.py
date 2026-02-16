"""
Safe front matter editing.

Provides tools for modifying YAML front matter without corrupting content.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

console = Console()


class FrontMatterEditor:
    """Safely edit front matter in Hugo content files."""

    def __init__(self, path: Path):
        """Initialize editor.

        Args:
            path: Path to the markdown file
        """
        self.path = Path(path)
        self._original_content: str = ""
        self._front_matter: dict[str, Any] = {}
        self._body: str = ""
        self._loaded = False

    def load(self) -> bool:
        """Load and parse the file.

        Returns:
            True if successful, False if file has no front matter
        """
        if not self.path.exists():
            console.print(f"[red]File not found: {self.path}[/red]")
            return False

        self._original_content = self.path.read_text(encoding="utf-8")

        if not self._original_content.startswith("---"):
            console.print(f"[yellow]No front matter in: {self.path}[/yellow]")
            return False

        try:
            # Find the closing ---
            # Use regex to find the second --- that closes front matter
            match = re.match(r"^---\n(.*?)\n---\n?(.*)$", self._original_content, re.DOTALL)
            if not match:
                console.print(f"[yellow]Invalid front matter format: {self.path}[/yellow]")
                return False

            fm_text = match.group(1)
            self._body = match.group(2)

            # Parse YAML
            self._front_matter = yaml.safe_load(fm_text) or {}
            self._loaded = True
            return True

        except yaml.YAMLError as e:
            console.print(f"[red]YAML error in {self.path}: {e}[/red]")
            return False

    @property
    def front_matter(self) -> dict[str, Any]:
        """Get the current front matter."""
        return self._front_matter

    @property
    def body(self) -> str:
        """Get the body content."""
        return self._body

    def get(self, key: str, default: Any = None) -> Any:
        """Get a front matter value."""
        return self._front_matter.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a front matter value."""
        if not self._loaded:
            raise RuntimeError("File not loaded. Call load() first.")
        self._front_matter[key] = value

    def add_to_list(self, key: str, value: str) -> bool:
        """Add a value to a list field if not present.

        Args:
            key: Front matter key (e.g., 'projects', 'tags')
            value: Value to add

        Returns:
            True if value was added, False if already present
        """
        if not self._loaded:
            raise RuntimeError("File not loaded. Call load() first.")

        current = self._front_matter.get(key, [])
        if not isinstance(current, list):
            current = [current] if current else []

        if value in current:
            return False

        current.append(value)
        self._front_matter[key] = current
        return True

    def remove_from_list(self, key: str, value: str) -> bool:
        """Remove a value from a list field.

        Args:
            key: Front matter key
            value: Value to remove

        Returns:
            True if value was removed, False if not present
        """
        if not self._loaded:
            raise RuntimeError("File not loaded. Call load() first.")

        current = self._front_matter.get(key, [])
        if not isinstance(current, list):
            return False

        if value not in current:
            return False

        current.remove(value)
        self._front_matter[key] = current
        return True

    def save(self, dry_run: bool = False) -> bool:
        """Save changes to the file.

        Args:
            dry_run: If True, don't actually write

        Returns:
            True if saved successfully
        """
        if not self._loaded:
            raise RuntimeError("File not loaded. Call load() first.")

        # Generate new content
        new_content = self._generate_content()

        if dry_run:
            console.print(f"[dim]Would update: {self.path}[/dim]")
            return True

        try:
            # Write to a temp file in the same directory then atomically replace,
            # so a crash mid-write cannot corrupt the original.
            fd, tmp_path = tempfile.mkstemp(
                dir=self.path.parent, suffix=".tmp", prefix=".mf_"
            )
            try:
                os.write(fd, new_content.encode("utf-8"))
                os.close(fd)
                fd = -1  # mark closed
                os.replace(tmp_path, self.path)
            except Exception:
                if fd >= 0:
                    os.close(fd)
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
                raise
            return True
        except Exception as e:
            console.print(f"[red]Error writing {self.path}: {e}[/red]")
            return False

    def _generate_content(self) -> str:
        """Generate the new file content."""
        # Use custom YAML dumper for nicer output
        yaml_str = yaml.dump(
            self._front_matter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )

        # Ensure body starts with newline if not empty
        body = self._body
        if body and not body.startswith("\n"):
            body = "\n" + body

        return f"---\n{yaml_str}---{body}"

    def preview_changes(self) -> str:
        """Get a preview of what would change."""
        if not self._loaded:
            return "File not loaded"

        new_content = self._generate_content()

        if new_content == self._original_content:
            return "No changes"

        # Simple diff showing just the front matter changes
        original_fm = self._extract_front_matter(self._original_content)
        new_fm = yaml.dump(
            self._front_matter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        return f"Original:\n{original_fm}\n\nNew:\n{new_fm}"

    def _extract_front_matter(self, content: str) -> str:
        """Extract just the front matter YAML from content."""
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        return match.group(1) if match else ""


def add_projects_to_content(
    path: Path,
    projects: list[str],
    dry_run: bool = False,
) -> bool:
    """Add project taxonomy terms to a content file.

    Args:
        path: Path to the markdown file
        projects: Project slugs to add
        dry_run: Preview only

    Returns:
        True if changes were made (or would be made in dry run)
    """
    editor = FrontMatterEditor(path)
    if not editor.load():
        return False

    changed = False
    for project in projects:
        if editor.add_to_list("linked_project", project):
            changed = True

    if changed:
        return editor.save(dry_run=dry_run)

    return False


def batch_add_projects(
    updates: list[tuple[Path, list[str]]],
    dry_run: bool = False,
) -> tuple[int, int, list[Path]]:
    """Batch update multiple files with project taxonomies.

    Args:
        updates: List of (path, projects) tuples
        dry_run: Preview only

    Returns:
        Tuple of (success_count, failure_count, failed_paths)
    """
    success = 0
    failure = 0
    failed_paths: list[Path] = []

    for path, projects in updates:
        if add_projects_to_content(path, projects, dry_run=dry_run):
            success += 1
        else:
            failure += 1
            failed_paths.append(path)

    return success, failure, failed_paths

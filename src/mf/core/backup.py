"""
Backup and safe file writing utilities.

Provides atomic JSON writes with automatic backups and rotation.
Supports both count-based and time-based (age) retention policies.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Default retention settings
DEFAULT_KEEP_COUNT = 10
DEFAULT_KEEP_DAYS = 30
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
TIMESTAMP_PATTERN = re.compile(r"_(\d{8}_\d{6})\.")


@dataclass
class BackupInfo:
    """Information about a backup file."""

    path: Path
    timestamp: datetime
    size_bytes: int
    db_name: str

    @property
    def age_days(self) -> float:
        """Age of backup in days."""
        return (datetime.now() - self.timestamp).total_seconds() / 86400

    @property
    def size_human(self) -> str:
        """Human-readable size."""
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f} KB"
        else:
            return f"{self.size_bytes / (1024 * 1024):.1f} MB"


def parse_backup_timestamp(filename: str) -> datetime | None:
    """Extract timestamp from backup filename.

    Args:
        filename: Backup filename like 'paper_db_20251212_144234.json'

    Returns:
        datetime if parseable, None otherwise
    """
    match = TIMESTAMP_PATTERN.search(filename)
    if match:
        try:
            return datetime.strptime(match.group(1), TIMESTAMP_FORMAT)
        except ValueError:
            return None
    return None


def list_backups(
    backup_dir: Path,
    db_name: str | None = None,
) -> list[BackupInfo]:
    """List all backups in a directory with metadata.

    Args:
        backup_dir: Directory containing backups
        db_name: Optional filter by database name (e.g., 'paper_db')

    Returns:
        List of BackupInfo sorted by timestamp (newest first)
    """
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []

    pattern = f"{db_name}_*.json" if db_name else "*_[0-9]*_[0-9]*.json"
    backups = []

    for path in backup_dir.glob(pattern):
        timestamp = parse_backup_timestamp(path.name)
        if timestamp:
            # Extract db_name from filename
            name_match = re.match(r"(.+)_\d{8}_\d{6}\.json$", path.name)
            extracted_name = name_match.group(1) if name_match else "unknown"

            backups.append(
                BackupInfo(
                    path=path,
                    timestamp=timestamp,
                    size_bytes=path.stat().st_size,
                    db_name=extracted_name,
                )
            )

    return sorted(backups, key=lambda b: b.timestamp, reverse=True)


def get_latest_backup(backup_dir: Path, db_name: str) -> BackupInfo | None:
    """Get the most recent backup for a database.

    Args:
        backup_dir: Directory containing backups
        db_name: Database name (e.g., 'paper_db')

    Returns:
        BackupInfo for latest backup, or None
    """
    backups = list_backups(backup_dir, db_name)
    return backups[0] if backups else None


def create_backup(
    file_path: Path,
    backup_dir: Path | None = None,
    timestamp_format: str = TIMESTAMP_FORMAT,
) -> Path:
    """Create a timestamped backup of a file.

    Args:
        file_path: Path to file to backup
        backup_dir: Directory to store backups (defaults to file_path.parent / 'backups')
        timestamp_format: strftime format for timestamp in filename

    Returns:
        Path to created backup file

    Raises:
        FileNotFoundError: If file_path doesn't exist
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Cannot backup non-existent file: {file_path}")

    # Default backup directory is 'backups' subdirectory next to the original file
    if backup_dir is None:
        backup_dir = file_path.parent / "backups"

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Create timestamped backup filename
    timestamp = datetime.now().strftime(timestamp_format)
    backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
    backup_path = backup_dir / backup_name

    # Copy the file preserving metadata
    shutil.copy2(file_path, backup_path)

    return backup_path


def cleanup_old_backups(
    backup_dir: Path,
    pattern: str = "*_[0-9]*_[0-9]*.*",
    keep_last: int = DEFAULT_KEEP_COUNT,
    keep_days: int | None = None,
) -> list[Path]:
    """Remove old backup files based on count and/or age.

    Args:
        backup_dir: Directory containing backups
        pattern: Glob pattern to match backup files
        keep_last: Number of most recent backups to keep (regardless of age)
        keep_days: Remove backups older than this many days (None = no age limit)

    Returns:
        List of removed backup file paths

    Note:
        When both keep_last and keep_days are specified, a backup is kept if it
        satisfies EITHER condition (within count OR within age).
    """
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []

    # Get all backup files matching pattern, sorted by modification time (newest first)
    backups = sorted(
        backup_dir.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    removed = []
    cutoff_time = None
    if keep_days is not None:
        cutoff_time = datetime.now() - timedelta(days=keep_days)

    for i, backup in enumerate(backups):
        # Always keep the first keep_last backups
        if i < keep_last:
            continue

        # If no age limit, remove based on count only
        if cutoff_time is None:
            backup.unlink()
            removed.append(backup)
            continue

        # Check age - parse timestamp from filename
        timestamp = parse_backup_timestamp(backup.name)
        if timestamp and timestamp < cutoff_time:
            backup.unlink()
            removed.append(backup)

    return removed


def cleanup_by_age(
    backup_dir: Path,
    max_age_days: int = DEFAULT_KEEP_DAYS,
    min_keep: int = 1,
) -> list[Path]:
    """Remove backups older than specified days.

    Args:
        backup_dir: Directory containing backups
        max_age_days: Maximum age in days
        min_keep: Minimum number of backups to keep (even if older)

    Returns:
        List of removed backup file paths
    """
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []

    cutoff = datetime.now() - timedelta(days=max_age_days)
    all_backups = list_backups(backup_dir)

    # Group by db_name
    by_db: dict[str, list[BackupInfo]] = {}
    for backup in all_backups:
        by_db.setdefault(backup.db_name, []).append(backup)

    removed = []
    for _db_name, backups in by_db.items():
        # Sort by timestamp (newest first)
        backups = sorted(backups, key=lambda b: b.timestamp, reverse=True)

        for i, backup in enumerate(backups):
            # Always keep min_keep backups
            if i < min_keep:
                continue

            if backup.timestamp < cutoff:
                backup.path.unlink()
                removed.append(backup.path)

    return removed


def rollback_database(
    db_path: Path,
    backup_dir: Path,
    backup_index: int = 0,
) -> Path | None:
    """Restore a database from a backup.

    Args:
        db_path: Path to current database file
        backup_dir: Directory containing backups
        backup_index: Which backup to restore (0 = most recent, 1 = second most recent, etc.)

    Returns:
        Path to the backup that was restored, or None if no backup available

    Raises:
        FileNotFoundError: If no suitable backup exists
    """
    db_name = db_path.stem
    backups = list_backups(backup_dir, db_name)

    if not backups:
        raise FileNotFoundError(f"No backups found for {db_name}")

    if backup_index >= len(backups):
        raise FileNotFoundError(
            f"Backup index {backup_index} out of range (only {len(backups)} backups)"
        )

    backup = backups[backup_index]

    # Create a backup of current state before rollback
    if db_path.exists():
        create_backup(db_path, backup_dir)

    # Restore from backup
    shutil.copy2(backup.path, db_path)

    return backup.path


def safe_write_json(
    file_path: Path,
    data: dict[str, Any],
    create_backup_first: bool = True,
    backup_dir: Path | None = None,
    indent: int = 2,
    ensure_ascii: bool = False,
    keep_backups: int = DEFAULT_KEEP_COUNT,
    keep_days: int | None = DEFAULT_KEEP_DAYS,
) -> Path | None:
    """Safely write JSON data to a file with atomic operation and optional backup.

    This function:
    1. Creates a backup of the existing file (if requested)
    2. Validates the data can be serialized to JSON
    3. Writes to a temporary file first
    4. Atomically replaces the original file
    5. Rotates old backups based on count and age

    Args:
        file_path: Path to JSON file to write
        data: Data to write
        create_backup_first: Create timestamped backup before writing
        backup_dir: Custom backup directory (defaults to file_path.parent / 'backups')
        indent: JSON indentation
        ensure_ascii: Whether to escape non-ASCII characters
        keep_backups: Number of most recent backups to always keep
        keep_days: Remove backups older than this (None = no age limit)

    Returns:
        Path to backup file if created, None otherwise

    Raises:
        ValueError: If data cannot be serialized to JSON
        IOError: If file operations fail
    """
    file_path = Path(file_path)
    backup_path = None

    # Create backup if file exists and backup is requested
    if create_backup_first and file_path.exists():
        backup_path = create_backup(file_path, backup_dir)

        # Rotate old backups based on count and age
        actual_backup_dir = backup_dir or (file_path.parent / "backups")
        cleanup_old_backups(
            actual_backup_dir,
            f"{file_path.stem}_*.json",
            keep_backups,
            keep_days,
        )

    # Validate data can be serialized
    try:
        json_str = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Cannot serialize data to JSON: {e}") from e

    # Write to temporary file in same directory (for atomic move)
    temp_fd, temp_path = tempfile.mkstemp(
        suffix=".json",
        prefix=f".{file_path.name}.",
        dir=file_path.parent,
        text=True,
    )

    try:
        # Write data to temp file
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(json_str)
            f.write("\n")  # Add trailing newline
            f.flush()
            os.fsync(f.fileno())  # Ensure written to disk

        # Atomic move (replace original file)
        temp_path_obj = Path(temp_path)
        temp_path_obj.replace(file_path)

    except Exception as e:
        # Clean up temp file on error
        with contextlib.suppress(OSError):
            Path(temp_path).unlink()
        raise OSError(f"Failed to write {file_path}: {e}") from e

    return backup_path

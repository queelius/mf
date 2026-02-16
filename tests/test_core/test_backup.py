"""Tests for mf.core.backup module."""

import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta

from mf.core.backup import (
    create_backup,
    cleanup_old_backups,
    safe_write_json,
    parse_backup_timestamp,
    list_backups,
    cleanup_by_age,
    rollback_database,
    get_latest_backup,
    BackupInfo,
    TIMESTAMP_FORMAT,
)


class TestCreateBackup:
    """Tests for create_backup function."""

    def test_creates_backup_file(self, sample_json_file, tmp_path):
        """Test that backup file is created."""
        backup_dir = tmp_path / "backups"
        backup_path = create_backup(sample_json_file, backup_dir)

        assert backup_path.exists()
        assert backup_dir.exists()

    def test_backup_preserves_content(self, sample_json_file, tmp_path):
        """Test that backup content matches original."""
        backup_dir = tmp_path / "backups"
        backup_path = create_backup(sample_json_file, backup_dir)

        original = json.loads(sample_json_file.read_text())
        backup = json.loads(backup_path.read_text())

        assert original == backup

    def test_raises_for_nonexistent_file(self, tmp_path):
        """Test that FileNotFoundError is raised for missing file."""
        with pytest.raises(FileNotFoundError):
            create_backup(tmp_path / "nonexistent.json")

    def test_creates_timestamped_filename(self, sample_json_file, tmp_path):
        """Test that backup filename includes timestamp."""
        backup_dir = tmp_path / "backups"
        backup_path = create_backup(sample_json_file, backup_dir)

        # Filename should be like "sample_YYYYMMDD_HHMMSS.json"
        assert backup_path.stem.startswith("sample_")
        assert len(backup_path.stem) > len("sample_")

    def test_default_backup_dir(self, sample_json_file):
        """Test that default backup dir is file.parent/backups."""
        backup_path = create_backup(sample_json_file)
        expected_dir = sample_json_file.parent / "backups"

        assert backup_path.parent == expected_dir


class TestCleanupOldBackups:
    """Tests for cleanup_old_backups function."""

    def test_removes_old_backups(self, tmp_path):
        """Test that old backups are removed."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Create 15 backup files
        for i in range(15):
            f = backup_dir / f"test_{2024010100 + i:08d}_{000000 + i:06d}.json"
            f.write_text("{}")

        # Keep only 10
        removed = cleanup_old_backups(backup_dir, keep_last=10)

        assert len(removed) == 5
        assert len(list(backup_dir.glob("*.json"))) == 10

    def test_does_nothing_if_under_limit(self, tmp_path):
        """Test that no files are removed if under limit."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        for i in range(5):
            f = backup_dir / f"test_{2024010100 + i:08d}_{000000 + i:06d}.json"
            f.write_text("{}")

        removed = cleanup_old_backups(backup_dir, keep_last=10)

        assert len(removed) == 0
        assert len(list(backup_dir.glob("*.json"))) == 5

    def test_handles_nonexistent_dir(self, tmp_path):
        """Test that nonexistent dir returns empty list."""
        result = cleanup_old_backups(tmp_path / "nonexistent")
        assert result == []


class TestSafeWriteJson:
    """Tests for safe_write_json function."""

    def test_writes_json_file(self, tmp_path):
        """Test that JSON file is written correctly."""
        file_path = tmp_path / "output.json"
        data = {"key": "value", "list": [1, 2, 3]}

        safe_write_json(file_path, data, create_backup_first=False)

        assert file_path.exists()
        written = json.loads(file_path.read_text())
        assert written == data

    def test_creates_backup_before_write(self, sample_json_file, tmp_path):
        """Test that backup is created before overwriting."""
        backup_dir = tmp_path / "backups"
        new_data = {"new": "data"}

        safe_write_json(sample_json_file, new_data, create_backup_first=True)

        assert backup_dir.exists()
        assert len(list(backup_dir.glob("*.json"))) == 1

    def test_atomic_write_on_success(self, tmp_path):
        """Test that write is atomic (no temp file left)."""
        file_path = tmp_path / "output.json"
        data = {"key": "value"}

        safe_write_json(file_path, data, create_backup_first=False)

        temp_files = list(tmp_path.glob(".*json*"))
        assert len(temp_files) == 0

    def test_raises_for_invalid_json(self, tmp_path):
        """Test that ValueError is raised for non-serializable data."""
        file_path = tmp_path / "output.json"

        class NotSerializable:
            pass

        with pytest.raises(ValueError):
            safe_write_json(file_path, {"obj": NotSerializable()}, create_backup_first=False)

    def test_adds_trailing_newline(self, tmp_path):
        """Test that file ends with newline."""
        file_path = tmp_path / "output.json"
        data = {"key": "value"}

        safe_write_json(file_path, data, create_backup_first=False)

        content = file_path.read_text()
        assert content.endswith("\n")


class TestParseBackupTimestamp:
    """Tests for parse_backup_timestamp function."""

    def test_parses_valid_timestamp(self):
        """Test parsing a valid backup filename."""
        filename = "paper_db_20251212_143045.json"
        result = parse_backup_timestamp(filename)

        assert result is not None
        assert result.year == 2025
        assert result.month == 12
        assert result.day == 12
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 45

    def test_returns_none_for_invalid(self):
        """Test that invalid filenames return None."""
        assert parse_backup_timestamp("no_timestamp.json") is None
        assert parse_backup_timestamp("wrong_20251212.json") is None
        assert parse_backup_timestamp("") is None

    def test_handles_different_db_names(self):
        """Test parsing works with different database names."""
        assert parse_backup_timestamp("paper_db_20251212_143045.json") is not None
        assert parse_backup_timestamp("projects_db_20251212_143045.json") is not None
        assert parse_backup_timestamp("my_custom_db_20251212_143045.json") is not None


class TestListBackups:
    """Tests for list_backups function."""

    def test_lists_all_backups(self, tmp_path):
        """Test that all backups are listed."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Create some backup files
        timestamps = [
            "20251201_100000",
            "20251202_100000",
            "20251203_100000",
        ]
        for ts in timestamps:
            (backup_dir / f"test_db_{ts}.json").write_text("{}")

        backups = list_backups(backup_dir, "test_db")

        assert len(backups) == 3
        # Should be sorted newest first
        assert backups[0].timestamp > backups[1].timestamp

    def test_filters_by_db_name(self, tmp_path):
        """Test that backups are filtered by database name."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        (backup_dir / "paper_db_20251201_100000.json").write_text("{}")
        (backup_dir / "projects_db_20251201_100000.json").write_text("{}")

        paper_backups = list_backups(backup_dir, "paper_db")
        project_backups = list_backups(backup_dir, "projects_db")

        assert len(paper_backups) == 1
        assert len(project_backups) == 1
        assert paper_backups[0].db_name == "paper_db"

    def test_returns_empty_for_nonexistent_dir(self, tmp_path):
        """Test that nonexistent directory returns empty list."""
        result = list_backups(tmp_path / "nonexistent")
        assert result == []

    def test_backup_info_properties(self, tmp_path):
        """Test BackupInfo properties."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        content = '{"key": "value"}'
        (backup_dir / "test_db_20251215_100000.json").write_text(content)

        backups = list_backups(backup_dir, "test_db")
        backup = backups[0]

        assert backup.size_bytes == len(content)
        assert backup.db_name == "test_db"
        assert "B" in backup.size_human or "KB" in backup.size_human


class TestGetLatestBackup:
    """Tests for get_latest_backup function."""

    def test_returns_newest_backup(self, tmp_path):
        """Test that the newest backup is returned."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        (backup_dir / "test_db_20251201_100000.json").write_text("{}")
        (backup_dir / "test_db_20251215_100000.json").write_text("{}")  # Newest
        (backup_dir / "test_db_20251210_100000.json").write_text("{}")

        latest = get_latest_backup(backup_dir, "test_db")

        assert latest is not None
        assert "20251215" in latest.path.name

    def test_returns_none_for_empty_dir(self, tmp_path):
        """Test that None is returned when no backups exist."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        result = get_latest_backup(backup_dir, "test_db")
        assert result is None


class TestCleanupByAge:
    """Tests for cleanup_by_age function."""

    def test_removes_old_backups(self, tmp_path):
        """Test that old backups are removed."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Create backups with different ages (using timestamps)
        now = datetime.now()
        old_ts = (now - timedelta(days=40)).strftime(TIMESTAMP_FORMAT)
        new_ts = now.strftime(TIMESTAMP_FORMAT)

        (backup_dir / f"test_db_{old_ts}.json").write_text("{}")
        (backup_dir / f"test_db_{new_ts}.json").write_text("{}")

        removed = cleanup_by_age(backup_dir, max_age_days=30)

        assert len(removed) == 1
        assert old_ts in str(removed[0])

    def test_keeps_min_backups(self, tmp_path):
        """Test that min_keep backups are preserved."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Create old backups
        old = datetime.now() - timedelta(days=100)
        for i in range(3):
            ts = (old + timedelta(days=i)).strftime(TIMESTAMP_FORMAT)
            (backup_dir / f"test_db_{ts}.json").write_text("{}")

        # With min_keep=2, should only remove 1
        removed = cleanup_by_age(backup_dir, max_age_days=30, min_keep=2)

        assert len(removed) == 1
        remaining = list(backup_dir.glob("*.json"))
        assert len(remaining) == 2


class TestRollbackDatabase:
    """Tests for rollback_database function."""

    def test_restores_from_backup(self, tmp_path):
        """Test that database is restored from backup."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Current database
        db_path = tmp_path / "test_db.json"
        db_path.write_text('{"current": "data"}')

        # Backup
        backup_content = '{"old": "data"}'
        (backup_dir / "test_db_20251215_100000.json").write_text(backup_content)

        restored = rollback_database(db_path, backup_dir, backup_index=0)

        assert restored is not None
        assert json.loads(db_path.read_text()) == {"old": "data"}

    def test_creates_backup_before_rollback(self, tmp_path):
        """Test that current state is backed up before rollback."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        db_path = tmp_path / "test_db.json"
        db_path.write_text('{"current": "data"}')

        (backup_dir / "test_db_20251215_100000.json").write_text('{"old": "data"}')

        initial_count = len(list(backup_dir.glob("*.json")))
        rollback_database(db_path, backup_dir, backup_index=0)

        # Should have one more backup (the pre-rollback state)
        final_count = len(list(backup_dir.glob("*.json")))
        assert final_count == initial_count + 1

    def test_raises_for_no_backups(self, tmp_path):
        """Test that FileNotFoundError is raised when no backups exist."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        db_path = tmp_path / "test_db.json"
        db_path.write_text('{"current": "data"}')

        with pytest.raises(FileNotFoundError, match="No backups found"):
            rollback_database(db_path, backup_dir)

    def test_raises_for_invalid_index(self, tmp_path):
        """Test that FileNotFoundError is raised for invalid backup index."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        db_path = tmp_path / "test_db.json"
        db_path.write_text('{"current": "data"}')

        (backup_dir / "test_db_20251215_100000.json").write_text('{"old": "data"}')

        with pytest.raises(FileNotFoundError, match="out of range"):
            rollback_database(db_path, backup_dir, backup_index=10)

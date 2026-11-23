import sqlite3
import stat
from datetime import UTC, datetime

from app.database_backup import backup_database


# Confirms a live SQLite database is copied through SQLite and remains readable.
def test_backup_database_creates_a_private_verified_snapshot(tmp_path):
    source = tmp_path / "ask-katy.private.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE approved_facts(value TEXT NOT NULL)")
        connection.execute("INSERT INTO approved_facts VALUES ('grounded fact')")

    backup_dir = tmp_path / "database-backups"
    backup = backup_database(
        source,
        backup_dir,
        keep=30,
        now=datetime(2026, 11, 23, 10, 30, tzinfo=UTC),
    )

    assert backup.name == "ask-katy.private-20261123T103000Z.db"
    assert stat.S_IMODE(backup_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    with sqlite3.connect(f"file:{backup}?mode=ro", uri=True) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT value FROM approved_facts").fetchone()[0] == (
            "grounded fact"
        )


# Confirms automatic retention removes only older matching database snapshots.
def test_backup_database_keeps_the_requested_number_of_snapshots(tmp_path):
    source = tmp_path / "ask-katy.private.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE content(value TEXT NOT NULL)")
    backup_dir = tmp_path / "database-backups"
    backup_dir.mkdir()
    unrelated = backup_dir / "keep-this-note.txt"
    unrelated.write_text("not a database backup")
    for timestamp in ("20261120T020000Z", "20261121T020000Z", "20261122T020000Z"):
        (backup_dir / f"ask-katy.private-{timestamp}.db").write_bytes(b"old")

    newest = backup_database(
        source,
        backup_dir,
        keep=2,
        now=datetime(2026, 11, 23, 2, 0, tzinfo=UTC),
    )

    remaining = sorted(backup_dir.glob("ask-katy.private-*.db"))
    assert [item.name for item in remaining] == [
        "ask-katy.private-20261122T020000Z.db",
        "ask-katy.private-20261123T020000Z.db",
    ]
    assert newest == remaining[-1]
    assert unrelated.read_text() == "not a database backup"

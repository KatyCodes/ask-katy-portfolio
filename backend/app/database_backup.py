"""Create private, verified, retention-limited SQLite database backups."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

BACKUP_PREFIX = "ask-katy.private-"
BACKUP_SUFFIX = ".db"


# Deletes older Ask Katy snapshots while leaving unrelated files untouched.
def prune_database_backups(destination_dir: Path, keep: int) -> None:
    backups = sorted(
        destination_dir.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"),
        reverse=True,
    )
    for old_backup in backups[keep:]:
        old_backup.unlink()


# Uses SQLite's online backup API to create and verify one consistent snapshot.
def backup_database(
    source: Path,
    destination_dir: Path,
    *,
    keep: int = 30,
    now: datetime | None = None,
) -> Path:
    source = source.expanduser().resolve()
    destination_dir = destination_dir.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Database not found: {source}")
    if keep < 1 or keep > 365:
        raise ValueError("keep must be between 1 and 365")
    destination_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination_dir.chmod(0o700)
    timestamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = destination_dir / f"{BACKUP_PREFIX}{timestamp}{BACKUP_SUFFIX}"
    temporary = destination_dir / f".{destination.name}.partial"
    if destination.exists() or temporary.exists():
        raise FileExistsError(f"Backup already exists for this timestamp: {destination}")

    try:
        source_uri = f"{source.as_uri()}?mode=ro"
        with sqlite3.connect(source_uri, uri=True, timeout=10) as source_connection:
            source_connection.execute("PRAGMA busy_timeout = 10000")
            with sqlite3.connect(temporary) as backup_connection:
                source_connection.backup(backup_connection)
                integrity = backup_connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
                if integrity != "ok":
                    raise sqlite3.DatabaseError(
                        f"Backup integrity check failed: {integrity}"
                    )
        temporary.chmod(0o600)
        temporary.replace(destination)
        destination.chmod(0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    prune_database_backups(destination_dir, keep)
    return destination


# Parses the small command-line interface used by the production cron job.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a verified private backup of the Ask Katy SQLite database."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination-dir", required=True, type=Path)
    parser.add_argument("--keep", type=int, default=30)
    return parser.parse_args()


# Runs one backup and prints its exact path for a short private cron log.
def main() -> None:
    arguments = parse_arguments()
    backup = backup_database(
        arguments.source,
        arguments.destination_dir,
        keep=arguments.keep,
    )
    print(f"Created and verified SQLite backup: {backup}")


if __name__ == "__main__":
    main()

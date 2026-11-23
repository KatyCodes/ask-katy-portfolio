#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

REMOTE_HOME="${ASK_KATY_REMOTE_HOME:-$HOME}"
BACKEND_ROOT="$REMOTE_HOME/ask-katy-api/backend"
PYTHON="$BACKEND_ROOT/.venv/bin/python"
PRIVATE_ROOT="$REMOTE_HOME/private/ask-katy"
DATABASE_PATH="${ASK_KATY_BACKUP_DATABASE_PATH:-$PRIVATE_ROOT/ask-katy.private.db}"
BACKUP_ROOT="$PRIVATE_ROOT/database-backups"
LOG_ROOT="$PRIVATE_ROOT/logs"
LOG_PATH="$LOG_ROOT/ask-katy.backup.log"
CRON_MARKER="# ask-katy-database-backup"
CRON_LINE="17 2 * * * cd $BACKEND_ROOT && $PYTHON -m app.database_backup --source $DATABASE_PATH --destination-dir $BACKUP_ROOT --keep 30 >> $LOG_PATH 2>&1 $CRON_MARKER"
CRON_CURRENT="$PRIVATE_ROOT/.crontab-current"
CRON_UPDATED="$PRIVATE_ROOT/.crontab-updated"

# Removes temporary crontab files even if setup stops early.
cleanup() {
  rm -f "$CRON_CURRENT" "$CRON_UPDATED"
}
trap cleanup EXIT

for required in "$PYTHON" "$DATABASE_PATH" "$BACKEND_ROOT/app/database_backup.py"; do
  if [[ ! -e "$required" ]]; then
    echo "Required backup path is missing: $required" >&2
    exit 1
  fi
done

mkdir -p "$BACKUP_ROOT" "$LOG_ROOT"
chmod 700 "$PRIVATE_ROOT" "$BACKUP_ROOT" "$LOG_ROOT"
touch "$LOG_PATH"
chmod 600 "$LOG_PATH"

# Creates and validates a snapshot immediately before trusting the schedule.
(
  cd "$BACKEND_ROOT"
  "$PYTHON" -m app.database_backup \
    --source "$DATABASE_PATH" \
    --destination-dir "$BACKUP_ROOT" \
    --keep 30
)

# Replaces only Ask Katy's marked cron entry so rerunning setup is safe.
crontab -l > "$CRON_CURRENT" 2>/dev/null || true
grep -Fv "$CRON_MARKER" "$CRON_CURRENT" > "$CRON_UPDATED" || true
printf '%s\n' "$CRON_LINE" >> "$CRON_UPDATED"
crontab "$CRON_UPDATED"

if ! crontab -l | grep -Fq "$CRON_MARKER"; then
  echo "The Ask Katy database backup schedule was not installed." >&2
  exit 1
fi

echo "Nightly Ask Katy database backups are installed with 30-snapshot retention."

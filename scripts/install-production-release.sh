#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "Usage: install-production-release.sh RELEASE_ID BACKEND_ZIP FRONTEND_ZIP" >&2
  exit 2
fi

RELEASE_ID="$1"
BACKEND_ARCHIVE="$2"
FRONTEND_ARCHIVE="$3"
REMOTE_HOME="${ASK_KATY_REMOTE_HOME:-$HOME}"
EXPECTED_USER="${ASK_KATY_REMOTE_USER:-$(whoami)}"
BACKEND_ROOT="$REMOTE_HOME/ask-katy-api/backend"
FRONTEND_ROOT="$REMOTE_HOME/katycodes.com/ask-katy"
SUPERVISOR_CONFIG="$REMOTE_HOME/ask-katy-api/supervisord.conf"
BACKUP_ROOT="$REMOTE_HOME/private/ask-katy/deploy-backups"
BACKUP_DIR="$BACKUP_ROOT/$RELEASE_ID"
STAGING_ROOT="$REMOTE_HOME/.ask-katy-stage-$RELEASE_ID"
PYTHON="$BACKEND_ROOT/.venv/bin/python"
SUPERVISORCTL="$BACKEND_ROOT/.venv/bin/supervisorctl"
PUBLIC_API_URL="${ASK_KATY_PUBLIC_API_URL:-https://api.katycodes.com/v1/health}"
PUBLIC_ADMIN_URL="${ASK_KATY_PUBLIC_ADMIN_URL:-https://katycodes.com/admin}"
DEPLOY_STARTED=0
BACKEND_BACKED_UP=0
PYPROJECT_BACKED_UP=0
FRONTEND_BACKED_UP=0

# Restores the previous code and frontend if any post-swap check fails.
rollback_release() {
  local status="$?"
  trap - ERR
  set +e
  if [[ "$DEPLOY_STARTED" -eq 1 ]]; then
    echo "Deployment failed; restoring release $RELEASE_ID." >&2
    if [[ "$BACKEND_BACKED_UP" -eq 1 ]]; then
      if [[ -d "$BACKEND_ROOT/app" ]]; then
        mv "$BACKEND_ROOT/app" "$BACKUP_DIR/failed-backend-app"
      fi
      if [[ -d "$BACKUP_DIR/backend-app" ]]; then
        mv "$BACKUP_DIR/backend-app" "$BACKEND_ROOT/app"
      fi
    fi
    if [[ "$PYPROJECT_BACKED_UP" -eq 1 ]]; then
      if [[ -f "$BACKEND_ROOT/pyproject.toml" ]]; then
        mv "$BACKEND_ROOT/pyproject.toml" "$BACKUP_DIR/failed-pyproject.toml"
      fi
      if [[ -f "$BACKUP_DIR/pyproject.toml" ]]; then
        mv "$BACKUP_DIR/pyproject.toml" "$BACKEND_ROOT/pyproject.toml"
      fi
    fi
    if [[ "$FRONTEND_BACKED_UP" -eq 1 ]]; then
      if [[ -d "$FRONTEND_ROOT" ]]; then
        mv "$FRONTEND_ROOT" "$BACKUP_DIR/failed-frontend"
      fi
      if [[ -d "$BACKUP_DIR/frontend" ]]; then
        mv "$BACKUP_DIR/frontend" "$FRONTEND_ROOT"
      fi
    fi
    "$SUPERVISORCTL" -c "$SUPERVISOR_CONFIG" restart ask-katy
  fi
  exit "$status"
}

trap rollback_release ERR

if [[ "$(whoami)" != "$EXPECTED_USER" ]]; then
  echo "Run this installer as $EXPECTED_USER, not $(whoami)." >&2
  exit 1
fi

if [[ ! "$RELEASE_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Invalid release identifier." >&2
  exit 1
fi

for required in \
  "$BACKEND_ARCHIVE" \
  "$FRONTEND_ARCHIVE" \
  "$BACKEND_ROOT/app" \
  "$BACKEND_ROOT/pyproject.toml" \
  "$FRONTEND_ROOT" \
  "$PYTHON" \
  "$SUPERVISORCTL" \
  "$SUPERVISOR_CONFIG"; do
  if [[ ! -e "$required" ]]; then
    echo "Required deployment path is missing: $required" >&2
    exit 1
  fi
done

if [[ -e "$BACKUP_DIR" || -e "$STAGING_ROOT" ]]; then
  echo "Release $RELEASE_ID already exists; create a new release instead." >&2
  exit 1
fi

mkdir -p "$BACKUP_ROOT" "$STAGING_ROOT/backend" "$STAGING_ROOT/frontend"
chmod 700 "$BACKUP_ROOT" "$STAGING_ROOT"
unzip -tq "$BACKEND_ARCHIVE" >/dev/null
unzip -tq "$FRONTEND_ARCHIVE" >/dev/null
unzip -q "$BACKEND_ARCHIVE" -d "$STAGING_ROOT/backend"
unzip -q "$FRONTEND_ARCHIVE" -d "$STAGING_ROOT/frontend"

if [[ ! -f "$STAGING_ROOT/backend/app/main.py" || \
      ! -f "$STAGING_ROOT/backend/pyproject.toml" || \
      ! -f "$STAGING_ROOT/frontend/index.html" ]]; then
  echo "Release package is missing a required application file." >&2
  exit 1
fi

if ! cmp -s "$BACKEND_ROOT/pyproject.toml" "$STAGING_ROOT/backend/pyproject.toml"; then
  "$PYTHON" -m pip install --disable-pip-version-check --quiet "$STAGING_ROOT/backend"
fi

mkdir "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
DEPLOY_STARTED=1
mv "$BACKEND_ROOT/app" "$BACKUP_DIR/backend-app"
BACKEND_BACKED_UP=1
mv "$BACKEND_ROOT/pyproject.toml" "$BACKUP_DIR/pyproject.toml"
PYPROJECT_BACKED_UP=1
mv "$FRONTEND_ROOT" "$BACKUP_DIR/frontend"
FRONTEND_BACKED_UP=1
mv "$STAGING_ROOT/backend/app" "$BACKEND_ROOT/app"
mv "$STAGING_ROOT/backend/pyproject.toml" "$BACKEND_ROOT/pyproject.toml"
mv "$STAGING_ROOT/frontend" "$FRONTEND_ROOT"

OLD_PROCESS_ID="$("$SUPERVISORCTL" -c "$SUPERVISOR_CONFIG" pid ask-katy 2>/dev/null || true)"
RESTART_STATUS=0
if "$SUPERVISORCTL" -c "$SUPERVISOR_CONFIG" restart ask-katy; then
  RESTART_STATUS=0
else
  RESTART_STATUS="$?"
fi
if [[ "$RESTART_STATUS" -ne 0 ]]; then
  NEW_PROCESS_ID="$("$SUPERVISORCTL" -c "$SUPERVISOR_CONFIG" pid ask-katy 2>/dev/null || true)"
  if [[ ! "$OLD_PROCESS_ID" =~ ^[0-9]+$ || \
        ! "$NEW_PROCESS_ID" =~ ^[0-9]+$ || \
        "$NEW_PROCESS_ID" == "$OLD_PROCESS_ID" ]]; then
    echo "Supervisor did not confirm a replacement Ask Katy process." >&2
    false
  fi
  echo "Supervisor returned early, but replacement process $NEW_PROCESS_ID started; verifying health."
fi
curl --fail --silent --show-error --retry 5 --retry-all-errors --retry-delay 2 "$PUBLIC_API_URL" >/dev/null
curl --fail --silent --show-error --retry 5 --retry-all-errors --retry-delay 2 "$PUBLIC_ADMIN_URL" >/dev/null

DEPLOY_STARTED=0
trap - ERR
if ! mv "$BACKEND_ARCHIVE" "$BACKUP_DIR/backend-release.zip"; then
  echo "Warning: the uploaded backend archive could not be moved into the backup." >&2
fi
if ! mv "$FRONTEND_ARCHIVE" "$BACKUP_DIR/frontend-release.zip"; then
  echo "Warning: the uploaded frontend archive could not be moved into the backup." >&2
fi
if [[ -f "${BASH_SOURCE[0]}" && "${BASH_SOURCE[0]}" == "$REMOTE_HOME"/.ask-katy-install-* ]]; then
  if ! mv "${BASH_SOURCE[0]}" "$BACKUP_DIR/install-release.sh"; then
    echo "Warning: the uploaded installer could not be moved into the backup." >&2
  fi
fi
rmdir "$STAGING_ROOT/backend" "$STAGING_ROOT" 2>/dev/null || true

echo "Release $RELEASE_ID installed successfully."

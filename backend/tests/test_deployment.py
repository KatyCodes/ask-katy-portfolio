import getpass
import importlib.util
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_MODULE_PATH = PROJECT_ROOT / "scripts" / "deploy.py"
INSTALLER_PATH = PROJECT_ROOT / "scripts" / "install-production-release.sh"
BACKUP_INSTALLER_PATH = PROJECT_ROOT / "scripts" / "install-production-backup.sh"
PUBLIC_RELEASE_AUDIT_PATH = PROJECT_ROOT / "scripts" / "public_release_audit.py"


# Loads the root deployment module without requiring it to be an installed package.
def load_deploy_module():
    spec = importlib.util.spec_from_file_location("ask_katy_deploy", DEPLOY_MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Loads the public-release auditor so its snapshot and history checks can be tested.
def load_public_release_audit_module():
    spec = importlib.util.spec_from_file_location(
        "ask_katy_public_release_audit", PUBLIC_RELEASE_AUDIT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Writes one small file while creating any missing parent directories.
def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# Makes one fake server command succeed without changing the test computer.
def write_success_command(path: Path) -> None:
    write_file(path, "#!/usr/bin/env bash\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


# Runs one Git command inside a disposable test repository.
def run_git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
    )


# Mimics Supervisor returning an error while still replacing the old process.
def write_restart_race_supervisor_command(path: Path) -> None:
    state_path = path.with_suffix(".restarted")
    write_file(path, f"""#!/usr/bin/env bash
if [[ "$*" == *" pid ask-katy"* ]]; then
  if [[ -e "{state_path}" ]]; then echo 202; else echo 101; fi
  exit 0
fi
if [[ "$*" == *" restart ask-katy"* ]]; then
  touch "{state_path}"
  exit 7
fi
exit 0
""")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


# Confirms backend packages contain code but never secrets, databases, or logs.
def test_backend_archive_has_an_explicit_private_data_boundary(tmp_path):
    deploy = load_deploy_module()
    project = tmp_path / "project"
    write_file(project / "backend" / "app" / "main.py", "new backend")
    write_file(project / "backend" / "app" / "__pycache__" / "main.pyc", "cache")
    write_file(project / "backend" / "pyproject.toml", "[project]")
    write_file(project / "backend" / ".env", "OPENAI_API_KEY=secret")
    write_file(
        project / "backend" / "private_content" / "ask-katy.private.db",
        "private database",
    )
    write_file(project / "backend" / "private_content" / "logs" / "errors.log", "log")
    archive = tmp_path / "backend.zip"

    deploy.create_backend_archive(project, archive)

    with zipfile.ZipFile(archive) as release:
        names = set(release.namelist())
    assert names == {"app/main.py", "pyproject.toml"}


# Confirms frontend packages contain only the compiled public site.
def test_frontend_archive_contains_only_built_public_files(tmp_path):
    deploy = load_deploy_module()
    project = tmp_path / "project"
    write_file(project / "frontend" / "dist" / "index.html", "new frontend")
    write_file(project / "frontend" / "dist" / "assets" / "app.js", "compiled")
    write_file(project / "frontend" / "src" / "App.tsx", "source")
    archive = tmp_path / "frontend.zip"

    deploy.create_frontend_archive(project, archive)

    with zipfile.ZipFile(archive) as release:
        names = set(release.namelist())
    assert names == {"index.html", "assets/app.js"}


# Confirms the server installer is valid shell and never names protected data as a target.
def test_server_installer_has_valid_syntax_and_avoids_private_targets():
    result = subprocess.run(
        ["bash", "-n", str(INSTALLER_PATH)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    installer = INSTALLER_PATH.read_text()
    assert "ask-katy.private.db" not in installer
    assert "/.env" not in installer
    assert "private/ask-katy/deploy-backups" in installer


# Confirms the reproducible backup installer uses private paths and bounded retention.
def test_database_backup_installer_has_valid_syntax_and_safe_defaults():
    result = subprocess.run(
        ["bash", "-n", str(BACKUP_INSTALLER_PATH)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    installer = BACKUP_INSTALLER_PATH.read_text()
    assert 'PRIVATE_ROOT="$REMOTE_HOME/private/ask-katy"' in installer
    assert 'BACKUP_ROOT="$PRIVATE_ROOT/database-backups"' in installer
    assert "ask-katy.private.db" in installer
    assert "--keep 30" in installer
    assert "# ask-katy-database-backup" in installer


# Confirms backup setup creates a single repeatable nightly cron entry.
def test_database_backup_installer_is_idempotent(tmp_path):
    remote_home = tmp_path / "remote-home"
    backend = remote_home / "ask-katy-api" / "backend"
    private = remote_home / "private" / "ask-katy"
    write_file(backend / "app" / "database_backup.py", "backup module")
    write_file(private / "ask-katy.private.db", "database")
    backup_runs = tmp_path / "backup-runs"
    write_file(
        backend / ".venv" / "bin" / "python",
        f"#!/usr/bin/env bash\necho \"$*\" >> \"{backup_runs}\"\n",
    )
    (backend / ".venv" / "bin" / "python").chmod(0o755)
    fake_bin = tmp_path / "fake-bin"
    crontab_state = tmp_path / "crontab-state"
    write_file(
        fake_bin / "crontab",
        f'''#!/usr/bin/env bash
if [[ "${{1:-}}" == "-l" ]]; then
  [[ -f "{crontab_state}" ]] && cat "{crontab_state}"
  exit 0
fi
cp "$1" "{crontab_state}"
''',
    )
    (fake_bin / "crontab").chmod(0o755)
    environment = os.environ.copy()
    environment.update({
        "ASK_KATY_REMOTE_HOME": str(remote_home),
        "PATH": f"{fake_bin}:{environment['PATH']}",
    })

    for _ in range(2):
        result = subprocess.run(
            ["bash", str(BACKUP_INSTALLER_PATH)],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        assert result.returncode == 0, result.stderr

    installed_crontab = crontab_state.read_text()
    assert installed_crontab.count("# ask-katy-database-backup") == 1
    assert "17 2 * * *" in installed_crontab
    assert "--keep 30" in installed_crontab
    assert len(backup_runs.read_text().splitlines()) == 2


# Confirms tracked automation does not publish Katy's server hostname or shell username.
def test_tracked_deployment_scripts_do_not_expose_server_identity():
    tracked_automation = "\n".join([
        DEPLOY_MODULE_PATH.read_text(),
        INSTALLER_PATH.read_text(),
        BACKUP_INSTALLER_PATH.read_text(),
        (PROJECT_ROOT / ".deploy.env.example").read_text(),
    ])

    assert "vps" + "35952.dreamhostps.com" not in tracked_automation
    assert "dh_" + "w74dkf" not in tracked_automation


# Prevents private files, secret-shaped values, and real applications from shipping publicly.
def test_public_release_snapshot_contains_only_safe_demo_material():
    result = subprocess.run(
        [sys.executable, str(PUBLIC_RELEASE_AUDIT_PATH)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


# Proves deleting a leaked value from today's files does not remove it from Git history.
def test_public_release_history_audit_finds_deleted_secrets(tmp_path):
    audit = load_public_release_audit_module()
    repository = tmp_path / "repository"
    repository.mkdir()
    run_git(repository, "init", "-q")
    run_git(repository, "config", "user.name", "Security Test")
    run_git(repository, "config", "user.email", "security-test@example.invalid")
    write_file(repository / "notes.txt", "sk-" + "A" * 32)
    run_git(repository, "add", "notes.txt")
    run_git(repository, "commit", "-q", "-m", "unsafe history")
    write_file(repository / "notes.txt", "safe public text")
    run_git(repository, "add", "notes.txt")
    run_git(repository, "commit", "-q", "-m", "clean current file")

    assert audit.audit_public_snapshot(repository) == []
    findings = audit.audit_repository_history(repository)

    assert findings == ["notes.txt: historical secret-shaped content"]


# Confirms a healthy replacement process survives Supervisor's premature restart error.
def test_server_installer_updates_code_after_supervisor_restart_race(tmp_path):
    remote_home = tmp_path / "remote-home"
    backend = remote_home / "ask-katy-api" / "backend"
    frontend = remote_home / "katycodes.com" / "ask-katy"
    private = remote_home / "private" / "ask-katy"
    write_file(backend / "app" / "main.py", "old backend")
    write_file(backend / "pyproject.toml", "old project")
    write_file(backend / ".env", "server secret")
    write_file(frontend / "index.html", "old frontend")
    write_file(private / "ask-katy.private.db", "production data")
    write_file(remote_home / "ask-katy-api" / "supervisord.conf", "supervisor")
    write_success_command(backend / ".venv" / "bin" / "python")
    write_restart_race_supervisor_command(backend / ".venv" / "bin" / "supervisorctl")

    release_source = tmp_path / "release"
    write_file(release_source / "backend" / "app" / "main.py", "new backend")
    write_file(release_source / "backend" / "pyproject.toml", "new project")
    write_file(release_source / "frontend" / "index.html", "new frontend")
    backend_archive = remote_home / "backend.zip"
    frontend_archive = remote_home / "frontend.zip"
    with zipfile.ZipFile(backend_archive, "w") as release:
        release.write(release_source / "backend" / "app" / "main.py", "app/main.py")
        release.write(release_source / "backend" / "pyproject.toml", "pyproject.toml")
    with zipfile.ZipFile(frontend_archive, "w") as release:
        release.write(release_source / "frontend" / "index.html", "index.html")

    fake_bin = tmp_path / "fake-bin"
    write_success_command(fake_bin / "curl")
    environment = os.environ.copy()
    environment.update({
        "ASK_KATY_REMOTE_HOME": str(remote_home),
        "ASK_KATY_REMOTE_USER": getpass.getuser(),
        "PATH": f"{fake_bin}:{environment['PATH']}",
    })

    result = subprocess.run(
        [
            "bash",
            str(INSTALLER_PATH),
            "test-release",
            str(backend_archive),
            str(frontend_archive),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert "replacement process 202 started" in result.stdout
    assert (backend / "app" / "main.py").read_text() == "new backend"
    assert (frontend / "index.html").read_text() == "new frontend"
    assert (backend / ".env").read_text() == "server secret"
    assert (private / "ask-katy.private.db").read_text() == "production data"
    backup = private / "deploy-backups" / "test-release"
    assert (backup / "backend-app" / "main.py").read_text() == "old backend"
    assert (backup / "frontend" / "index.html").read_text() == "old frontend"


# Confirms even a failure between file swaps restores every original production file.
def test_server_installer_rolls_back_a_partial_file_swap(tmp_path):
    remote_home = tmp_path / "remote-home"
    backend = remote_home / "ask-katy-api" / "backend"
    frontend = remote_home / "katycodes.com" / "ask-katy"
    private = remote_home / "private" / "ask-katy"
    write_file(backend / "app" / "main.py", "old backend")
    write_file(backend / "pyproject.toml", "old project")
    write_file(backend / ".env", "server secret")
    write_file(frontend / "index.html", "old frontend")
    write_file(private / "ask-katy.private.db", "production data")
    write_file(remote_home / "ask-katy-api" / "supervisord.conf", "supervisor")
    write_success_command(backend / ".venv" / "bin" / "python")
    write_success_command(backend / ".venv" / "bin" / "supervisorctl")

    release_source = tmp_path / "release"
    write_file(release_source / "backend" / "app" / "main.py", "new backend")
    write_file(release_source / "backend" / "pyproject.toml", "new project")
    write_file(release_source / "frontend" / "index.html", "new frontend")
    backend_archive = remote_home / "backend.zip"
    frontend_archive = remote_home / "frontend.zip"
    with zipfile.ZipFile(backend_archive, "w") as release:
        release.write(release_source / "backend" / "app" / "main.py", "app/main.py")
        release.write(release_source / "backend" / "pyproject.toml", "pyproject.toml")
    with zipfile.ZipFile(frontend_archive, "w") as release:
        release.write(release_source / "frontend" / "index.html", "index.html")

    fake_bin = tmp_path / "fake-bin"
    write_success_command(fake_bin / "curl")
    failure_marker = tmp_path / "mv-failed-once"
    real_mv = subprocess.run(
        ["which", "mv"], check=True, capture_output=True, text=True
    ).stdout.strip()
    write_file(fake_bin / "mv", f"""#!/usr/bin/env bash
if [[ "$1" == */backend/pyproject.toml && ! -e "{failure_marker}" ]]; then
  touch "{failure_marker}"
  exit 1
fi
exec "{real_mv}" "$@"
""")
    (fake_bin / "mv").chmod((fake_bin / "mv").stat().st_mode | stat.S_IXUSR)
    environment = os.environ.copy()
    environment.update({
        "ASK_KATY_REMOTE_HOME": str(remote_home),
        "ASK_KATY_REMOTE_USER": getpass.getuser(),
        "PATH": f"{fake_bin}:{environment['PATH']}",
    })

    result = subprocess.run(
        [
            "bash",
            str(INSTALLER_PATH),
            "failed-release",
            str(backend_archive),
            str(frontend_archive),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode != 0
    assert (backend / "app" / "main.py").read_text() == "old backend"
    assert (backend / "pyproject.toml").read_text() == "old project"
    assert (frontend / "index.html").read_text() == "old frontend"
    assert (backend / ".env").read_text() == "server secret"
    assert (private / "ask-katy.private.db").read_text() == "production data"

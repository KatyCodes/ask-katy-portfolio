#!/usr/bin/env python3
"""Build, test, package, upload, install, and verify one Ask Katy release."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 22
DEFAULT_KEY = Path.home() / ".ssh" / "ask_katy_dreamhost_ed25519"
PRODUCTION_API_URL = "https://api.katycodes.com"
PRODUCTION_SITE_URL = "https://katycodes.com"


# Represents a deployment problem that can be explained without a Python traceback.
class DeploymentError(RuntimeError):
    pass


# Reads simple key-value settings without executing the local configuration file.
def read_deployment_config(project_root: Path) -> dict[str, str]:
    config_path = project_root / ".deploy.env"
    if not config_path.is_file():
        return {}
    config = {}
    for line_number, raw_line in enumerate(config_path.read_text().splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise DeploymentError(
                f"Invalid .deploy.env setting on line {line_number}."
            )
        config[key.strip()] = value.strip()
    return config


# Reads optional non-secret overrides while keeping Katy's production values as defaults.
class DeploymentSettings:
    def __init__(self, project_root: Path = PROJECT_ROOT) -> None:
        config = read_deployment_config(project_root)

        # Lets an environment value override the matching local configuration value.
        def setting(name: str, default: str = "") -> str:
            return os.getenv(name, config.get(name, default)).strip()

        self.host = setting("ASK_KATY_DEPLOY_HOST")
        self.user = setting("ASK_KATY_DEPLOY_USER")
        if not self.host or not self.user:
            raise DeploymentError(
                "Copy .deploy.env.example to .deploy.env and add the DreamHost "
                "hostname and shell username."
            )
        try:
            self.port = int(setting("ASK_KATY_DEPLOY_PORT", str(DEFAULT_PORT)))
        except ValueError as error:
            raise DeploymentError("ASK_KATY_DEPLOY_PORT must be a number.") from error
        self.key = Path(
            setting("ASK_KATY_DEPLOY_KEY", str(DEFAULT_KEY))
        ).expanduser()
        self.remote_home = setting(
            "ASK_KATY_REMOTE_HOME", f"/home/{self.user}"
        )

    # Returns the SSH destination without placing passwords or secrets in the command.
    @property
    def destination(self) -> str:
        return f"{self.user}@{self.host}"


# Prints one deployment phase in a consistent, readable format.
def announce(message: str) -> None:
    print(f"\n==> {message}", flush=True)


# Runs one command without a shell so file paths cannot become executable input.
def run_command(
    command: list[str],
    *,
    cwd: Path = PROJECT_ROOT,
    environment: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    print(f"    {shlex.join(command)}", flush=True)
    # A list keeps arguments separate and subprocess shell mode remains disabled.
    return subprocess.run(  # nosec B603
        command,
        cwd=cwd,
        env=environment,
        check=True,
        text=True,
        capture_output=capture_output,
    )


# Stops early with a useful message when a required local command is unavailable.
def require_commands(commands: list[str]) -> None:
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        raise DeploymentError(
            "Install the missing command(s) before deploying: " + ", ".join(missing)
        )


# Prevents an accidental deployment of work that has not been saved in Git.
def require_clean_worktree() -> None:
    result = run_command(
        ["git", "status", "--porcelain"], capture_output=True
    )
    if result.stdout.strip():
        raise DeploymentError(
            "The project has uncommitted changes. Commit them before deploying so "
            "this release can always be identified and restored."
        )


# Verifies the dedicated deployment key exists before any build work begins.
def require_ssh_key(settings: DeploymentSettings) -> None:
    if not settings.key.is_file():
        raise DeploymentError(
            f"Deployment key not found at {settings.key}. Complete the one-time SSH "
            "key setup first."
        )


# Runs every automated check before production files are packaged.
def run_tests() -> None:
    announce("Running backend tests")
    run_command([str(PROJECT_ROOT / "backend" / ".venv" / "bin" / "pytest"), "-q"])
    announce("Running frontend tests")
    run_command(["npm", "test", "--", "--run"], cwd=PROJECT_ROOT / "frontend")


# Builds browser files with production URLs and the correct /ask-katy asset prefix.
def build_frontend() -> None:
    announce("Building the production frontend")
    environment = os.environ.copy()
    environment.update({
        "VITE_API_URL": PRODUCTION_API_URL,
        "VITE_SITE_URL": PRODUCTION_SITE_URL,
    })
    run_command(
        ["npm", "run", "build", "--", "--base=/ask-katy/"],
        cwd=PROJECT_ROOT / "frontend",
        environment=environment,
    )


# Rejects archive paths that could expose private runtime data.
def validate_archive_names(names: list[str]) -> None:
    forbidden_names = {".env", "private_content", "logs", "__pycache__"}
    forbidden_suffixes = (".db", ".db-shm", ".db-wal", ".pyc", ".log")
    for name in names:
        path = Path(name)
        if any(part in forbidden_names or part.startswith(".env.") for part in path.parts):
            raise DeploymentError(f"Private path was blocked from a release: {name}")
        if name.endswith(forbidden_suffixes):
            raise DeploymentError(f"Private file was blocked from a release: {name}")


# Packages only Python application code and dependency metadata.
def create_backend_archive(project_root: Path, destination: Path) -> None:
    backend = project_root / "backend"
    sources = [backend / "pyproject.toml"]
    sources.extend(sorted((backend / "app").rglob("*")))
    files = [
        path
        for path in sources
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    ]
    if not (backend / "app" / "main.py").is_file():
        raise DeploymentError("Backend entry point backend/app/main.py is missing.")
    if not (backend / "pyproject.toml").is_file():
        raise DeploymentError("Backend dependency file backend/pyproject.toml is missing.")
    names = [str(path.relative_to(backend)) for path in files]
    validate_archive_names(names)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as release:
        for source, name in zip(files, names, strict=True):
            if source.is_symlink():
                raise DeploymentError(f"Symbolic links are not allowed in releases: {source}")
            release.write(source, name)


# Packages only Vite's compiled public frontend output.
def create_frontend_archive(project_root: Path, destination: Path) -> None:
    public_build = project_root / "frontend" / "dist"
    if not (public_build / "index.html").is_file():
        raise DeploymentError("Frontend build is missing frontend/dist/index.html.")
    files = sorted(path for path in public_build.rglob("*") if path.is_file())
    names = [str(path.relative_to(public_build)) for path in files]
    validate_archive_names(names)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as release:
        for source, name in zip(files, names, strict=True):
            if source.is_symlink():
                raise DeploymentError(f"Symbolic links are not allowed in releases: {source}")
            release.write(source, name)


# Creates a readable, unique release identifier from time and the Git commit.
def release_identifier() -> str:
    revision = run_command(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True
    ).stdout.strip()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{revision}"


# Uploads the two verified packages and the fixed server installer over SSH.
def upload_release(
    settings: DeploymentSettings,
    backend_archive: Path,
    frontend_archive: Path,
    installer: Path,
) -> None:
    announce("Uploading the release to DreamHost")
    run_command([
        "scp",
        "-i",
        str(settings.key),
        "-P",
        str(settings.port),
        "-o",
        "BatchMode=yes",
        str(backend_archive),
        str(frontend_archive),
        str(installer),
        f"{settings.destination}:{settings.remote_home}/",
    ])


# Invokes the tested server installer that backs up, swaps, restarts, and verifies.
def install_release(
    settings: DeploymentSettings,
    release_id: str,
    backend_archive: Path,
    frontend_archive: Path,
    installer: Path,
) -> None:
    announce("Installing the release and checking the live site")
    remote_backend = f"{settings.remote_home}/{backend_archive.name}"
    remote_frontend = f"{settings.remote_home}/{frontend_archive.name}"
    remote_installer = f"{settings.remote_home}/{installer.name}"
    run_command([
        "ssh",
        "-i",
        str(settings.key),
        "-p",
        str(settings.port),
        "-o",
        "BatchMode=yes",
        settings.destination,
        "bash",
        remote_installer,
        release_id,
        remote_backend,
        remote_frontend,
    ])


# Builds unique local package names so concurrent or repeated releases cannot collide.
def prepare_release_files(temporary_directory: Path, release_id: str) -> tuple[Path, Path, Path]:
    backend_archive = temporary_directory / f".ask-katy-backend-{release_id}.zip"
    frontend_archive = temporary_directory / f".ask-katy-frontend-{release_id}.zip"
    installer = temporary_directory / f".ask-katy-install-{release_id}.sh"
    create_backend_archive(PROJECT_ROOT, backend_archive)
    create_frontend_archive(PROJECT_ROOT, frontend_archive)
    shutil.copy2(PROJECT_ROOT / "scripts" / "install-production-release.sh", installer)
    return backend_archive, frontend_archive, installer


# Performs the complete guarded production deployment.
def deploy(*, prepare_only: bool = False) -> None:
    require_commands(["git", "npm"])
    require_clean_worktree()
    settings = None
    if not prepare_only:
        require_commands(["ssh", "scp"])
        settings = DeploymentSettings()
        require_ssh_key(settings)
    run_tests()
    build_frontend()
    release_id = release_identifier()
    with tempfile.TemporaryDirectory(prefix="ask-katy-release-") as temporary:
        files = prepare_release_files(Path(temporary), release_id)
        announce("Validated release packages with no database, .env, logs, or secrets")
        if prepare_only:
            print("Preparation check passed; nothing was uploaded.")
            return
        if settings is None:
            raise DeploymentError("Deployment settings were not initialized")
        upload_release(settings, *files)
        install_release(settings, release_id, *files)
    announce(f"Ask Katy release {release_id} is live")
    print(f"Admin: {PRODUCTION_SITE_URL}/admin")
    print(f"API health: {PRODUCTION_API_URL}/v1/health")


# Parses the intentionally small command-line interface.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely test and deploy Ask Katy to DreamHost."
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="run tests, build, and validate packages without uploading",
    )
    return parser.parse_args()


# Converts expected deployment failures into a short action-oriented message.
def main() -> int:
    arguments = parse_arguments()
    try:
        deploy(prepare_only=arguments.prepare_only)
    except (DeploymentError, subprocess.CalledProcessError) as error:
        print(f"\nDeployment stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fail safely when a tracked file is unsuitable for the public source repository."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ENV_EXAMPLES = {".env.example", ".deploy.env.example"}
PRIVATE_SUFFIXES = {
    ".db",
    ".db-shm",
    ".db-wal",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
}
SECRET_PATTERNS = {
    "OpenAI-style API key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "GitHub-style access token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
    ),
    "private key material": re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
}
PRIVATE_IDENTIFIERS = {
    "real employer fixture": (
        "Orange" + " Logic",
        "orange" + "-logic",
        "Bank" + " of America",
        "bank" + "-of-america",
        "Field" + " Nation",
        "field" + "-nation",
        "Talk" + "desk",
        "talk" + "desk",
    ),
    "production server identity": (
        "vps" + "35952.dreamhostps.com",
        "dh_" + "w74dkf",
    ),
}
HISTORY_SECRET_EXPRESSIONS = (
    r"(^|[^A-Za-z0-9_-])sk-(proj-)?[A-Za-z0-9_-]{20,}",
    r"(^|[^A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{20,}",
    r"(^|[^A-Za-z0-9_])github_pat_[A-Za-z0-9_]{20,}",
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----",
)


# Returns every file Git would publish, without inspecting ignored private files.
def tracked_paths(project_root: Path = PROJECT_ROOT) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
    return [
        project_root / Path(item.decode())
        for item in result.stdout.split(b"\0")
        if item
    ]


# Identifies tracked filenames that should always remain outside source control.
def private_path_reason(relative_path: Path) -> str | None:
    name = relative_path.name.casefold()
    lower_path = relative_path.as_posix().casefold()
    if name == ".env" or (name.startswith(".env.") and name not in ALLOWED_ENV_EXAMPLES):
        return "environment file"
    if any(lower_path.endswith(suffix) for suffix in PRIVATE_SUFFIXES):
        return "private data or credential file"
    if lower_path.endswith(".application.private.json"):
        return "private application file"
    if "private_content/" in lower_path and name != ".gitkeep":
        return "private application content"
    return None


# Reads only ordinary UTF-8 source text; binaries are checked by filename instead.
def readable_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


# Returns safe descriptions and paths, never the possible secret value itself.
def audit_public_snapshot(project_root: Path = PROJECT_ROOT) -> list[str]:
    findings: list[str] = []
    for path in tracked_paths(project_root):
        relative_path = path.relative_to(project_root)
        path_reason = private_path_reason(relative_path)
        if path_reason:
            findings.append(f"{relative_path}: tracked {path_reason}")
            continue
        text = readable_text(path)
        if text is None:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{relative_path}: possible {label}")
        for label, identifiers in PRIVATE_IDENTIFIERS.items():
            if any(identifier.casefold() in text.casefold() for identifier in identifiers):
                findings.append(f"{relative_path}: contains a {label}")
    return findings


# Lists historical matching paths without printing any matching content or secret value.
def historical_matching_paths(
    project_root: Path,
    *,
    expressions: tuple[str, ...],
    fixed_strings: bool,
) -> set[str]:
    revisions = subprocess.run(
        ["git", "rev-list", "--all"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if not revisions:
        return set()
    command = ["git", "grep", "-I", "-l", "-F" if fixed_strings else "-E"]
    for expression in expressions:
        command.extend(["-e", expression])
    result = subprocess.run(
        [*command, *revisions, "--", "."],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError("Could not inspect Git history")
    return {
        line.split(":", 1)[1]
        for line in result.stdout.splitlines()
        if ":" in line
    }


# Audits every reachable commit while reporting paths only, never matching values.
def audit_repository_history(project_root: Path = PROJECT_ROOT) -> list[str]:
    findings: set[str] = set()
    path_history = subprocess.run(
        ["git", "log", "--all", "--name-only", "--pretty=format:", "-z"],
        cwd=project_root,
        check=True,
        capture_output=True,
    ).stdout
    for item in path_history.split(b"\0"):
        if not item:
            continue
        relative_path = Path(item.decode())
        reason = private_path_reason(relative_path)
        if reason:
            findings.add(f"{relative_path}: historical {reason}")

    secret_paths = historical_matching_paths(
        project_root,
        expressions=HISTORY_SECRET_EXPRESSIONS,
        fixed_strings=False,
    )
    for path in secret_paths:
        findings.add(f"{path}: historical secret-shaped content")

    for label, identifiers in PRIVATE_IDENTIFIERS.items():
        paths = historical_matching_paths(
            project_root,
            expressions=identifiers,
            fixed_strings=True,
        )
        for path in paths:
            findings.add(f"{path}: historical {label}")
    return sorted(findings)


# Prints a concise release verdict and exits nonzero when the selected audit is unsafe.
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--history",
        action="store_true",
        help="also inspect every reachable Git commit",
    )
    arguments = parser.parse_args()
    findings = audit_public_snapshot()
    if arguments.history:
        findings.extend(audit_repository_history())
    if findings:
        print("Public release audit failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    scope = "snapshot and history" if arguments.history else "tracked snapshot"
    print(f"Public release audit passed: {scope} contains no known private material.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Check distributable files, never print a matched secret value."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = (".local/", ".aws/", ".codex/", ".brain/", "daily/", "weekly/", "projects/", "inbox/", ".playwright-mcp/", ".env")
PRIVATE_FILES = {"PORTFOLIO.md", "reminders.md"}
RULES = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})"),
    "GitLab token": re.compile(rb"glpat-[A-Za-z0-9_-]{15,}"),
    "AWS access id": re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "provider API key": re.compile(rb"sk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}"),
    "personal home path": re.compile(rb"/(?:Users|home)/[A-Za-z0-9_.-]+/"),
}


def violations(name, data):
    found = []
    if name.startswith(PRIVATE) or name in PRIVATE_FILES:
        found.append("private workspace file")
    found.extend(label for label, pattern in RULES.items() if pattern.search(data))
    return found


def main():
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    files = [name for name in tracked if name]
    if not files:
        print("No tracked files. Stage the intended public files, then run this check.", file=sys.stderr)
        return 1
    failures = []
    required = {f".agents/skills/{name}/SKILL.md" for name in ("today", "weekly", "radar", "schedule", "inbox")}
    required.update({"LICENSE", "README.md", "bin/brain.py", "examples/demo.json"})
    failures.extend((name, "required public file is not tracked") for name in required - set(files))
    for name in files:
        path = ROOT / name
        if path.is_symlink():
            failures.append((name, "symlink requires manual review"))
            continue
        if path.is_file():
            failures.extend((name, issue) for issue in violations(name, path.read_bytes()))
        staged = subprocess.run(["git", "show", ":" + name], cwd=ROOT, capture_output=True)
        if staged.returncode == 0:
            failures.extend((name, "index: " + issue) for issue in violations(name, staged.stdout))
    # History inspection catches private paths that were deleted from the working tree.
    history = subprocess.run(["git", "log", "--all", "--format=", "--name-only"], cwd=ROOT, capture_output=True, text=True)
    for name in set(history.stdout.splitlines()):
        if name and (name.startswith(PRIVATE) or name in PRIVATE_FILES):
            failures.append((name, "private path in Git history"))
    for name, reason in failures:
        print(f"FAIL {name}: {reason}", file=sys.stderr)
    if failures:
        return 1
    print(f"Release content check passed for {len(files)} tracked files. Review prose and history before publication.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import copy
import datetime as dt
import json
from pathlib import Path
import plistlib
import shutil
import sys
from zoneinfo import ZoneInfo

from . import __version__
from .collect import collect
from .config import DEFAULT, load
from .reports import render
from .runner import generate
from .storage import BrainError, atomic_write, run_lock, write_json

SOURCE = Path(__file__).resolve().parents[1]


def initialize(root):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = root / ".brain"
    state.mkdir(exist_ok=True, mode=0o700)
    if not (state / "config.json").exists():
        write_json(state / "config.json", copy.deepcopy(DEFAULT))
    for name in ("daily", "weekly", "inbox", "projects"):
        (root / name).mkdir(exist_ok=True, mode=0o700)
    for name, content in {
        "reminders.md": "# Reminders\n\nRecord dated, local-only reminders here.\n",
        "inbox/INBOX.md": "# Inbox\n\n## Pending\n\n## Archived\n",
        "projects/operating-rules.md": "# Personal operating rules\n\nAdd your working rhythm, responsibilities, and approved exceptions here.\n",
    }.items():
        if not (root / name).exists():
            atomic_write(root / name, content)
    if root != SOURCE:
        for name in ("AGENTS.md", "CLAUDE.md", ".gitignore"):
            if not (root / name).exists():
                shutil.copyfile(SOURCE / name, root / name)
        for name in (".agents/skills", ".claude/commands"):
            if not (root / name).exists():
                shutil.copytree(SOURCE / name, root / name)
        # An external workspace can still use the documented bin/brain.py command.
        script = root / "bin/brain.py"
        if not script.exists():
            atomic_write(script, "#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n"
                         + f"sys.path.insert(0, {str(SOURCE)!r})\n"
                         + "from workbrain.cli import main\n"
                         + "raise SystemExit(main(['--root', str(Path(__file__).resolve().parents[1]), *sys.argv[1:]]))\n")
    print("Initialized private workspace. Edit .brain/config.json; no credentials or live data were copied.")


def refresh(root, config):
    snapshot = collect(config)
    # Collection must succeed in full before any current output is replaced.
    write_json(root / ".brain/snapshot.json", snapshot)
    atomic_write(root / "PORTFOLIO.md", render(snapshot, config, "portfolio"))
    return snapshot


def read_snapshot(root, config):
    try:
        snapshot = json.loads((root / ".brain/snapshot.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BrainError("No valid snapshot; run refresh first.") from None
    today = dt.datetime.now(ZoneInfo(config.get("timezone", "UTC"))).date().isoformat()
    if snapshot.get("collected_at", "")[:10] != today:
        raise BrainError("Snapshot is from another date; run refresh before generating a current report.")
    return snapshot


def report(root, config, snapshot, kind, agent=None):
    date = snapshot["collected_at"][:10]
    name = f"radar-{date}" if kind == "radar" else date
    folder = "daily" if kind == "today" else "weekly"
    # Deterministic refreshes never overwrite interactive conclusions in the main report.
    source_path = root / folder / (name + ".source.md")
    destination = root / folder / (name + ".md")
    atomic_write(source_path, render(snapshot, config, kind))
    if agent:
        generate(root, SOURCE, snapshot, config, kind, destination, agent)
        print(f"Generated {destination}")
    else:
        print(f"Updated {source_path}; use the matching skill for decisions and prioritization.")


def demo(root):
    fixture = json.loads((SOURCE / "examples/demo.json").read_text(encoding="utf-8"))
    output = root / ".brain/demo"
    write_json(output / "snapshot.json", fixture["snapshot"])
    for kind in ("today", "weekly", "radar", "portfolio"):
        atomic_write(output / (kind + ".md"), render(fixture["snapshot"], fixture["config"], kind))
    print(render(fixture["snapshot"], fixture["config"]))
    print(f"\nOffline demo written to {output}; no network, credentials, or model calls.")


def launchd(root, hour, minute, agent):
    command = [sys.executable, str(SOURCE / "bin/brain.py"), "--root", str(root), "morning"]
    if agent:
        command += ["--agent", agent]
    value = {"Label": "dev.brain.morning", "ProgramArguments": command,
             "WorkingDirectory": str(root), "StartCalendarInterval": {"Hour": hour, "Minute": minute},
             "StandardOutPath": str(root / ".brain/morning.log"), "StandardErrorPath": str(root / ".brain/morning-error.log")}
    atomic_write(root / ".brain/dev.brain.morning.plist", plistlib.dumps(value).decode())
    print("Generated .brain/dev.brain.morning.plist. Review before installing; no schedule was activated.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Brain — local-first work management")
    parser.add_argument("--root", type=Path, default=SOURCE, help="private workspace (default: this clone)")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "demo", "refresh", "doctor"):
        commands.add_parser(name)
    for name in ("brief", "morning"):
        p = commands.add_parser(name)
        p.add_argument("--agent", choices=("codex", "claude"), help="explicitly send snapshot to an AI CLI (may incur usage)")
        if name == "brief":
            p.add_argument("--kind", choices=("today", "weekly", "radar"), default="today")
    p = commands.add_parser("launchd", help="generate a macOS schedule; does not activate it")
    p.add_argument("--hour", type=int, choices=range(24), default=8)
    p.add_argument("--minute", type=int, choices=range(60), default=30)
    p.add_argument("--agent", choices=("codex", "claude"))
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    try:
        if args.command == "init":
            initialize(root)
        elif args.command == "demo":
            demo(root)
        else:
            config = load(root)
            if args.command == "doctor":
                print(f"Brain {__version__}; config valid; {len(config['projects'])} configured projects.")
                print("Python: " + sys.version.split()[0])
                print("Agent CLIs: " + ", ".join(a for a in ("codex", "claude") if shutil.which(a)))
                print("Credentials and live API connectivity were not tested. Refresh verifies configured providers.")
            elif args.command == "launchd":
                launchd(root, args.hour, args.minute, args.agent)
            else:
                with run_lock(root):
                    snapshot = read_snapshot(root, config) if args.command == "brief" else refresh(root, config)
                    if args.command == "refresh":
                        print("Updated .brain/snapshot.json and PORTFOLIO.md.")
                    elif args.command == "brief":
                        report(root, config, snapshot, args.kind, args.agent)
                    else:
                        report(root, config, snapshot, "today", args.agent)
                        if dt.date.fromisoformat(snapshot["collected_at"][:10]).isoweekday() == 1:
                            for kind in ("weekly", "radar"):
                                report(root, config, snapshot, kind, args.agent)
        return 0
    except BrainError as error:
        print(f"Brain: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        print("Brain: invalid configuration, response, or local file. No raw data was printed; inspect your local setup.", file=sys.stderr)
        return 1

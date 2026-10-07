import json
import os
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .storage import BrainError


DEFAULT = {
    "version": 1,
    "owner": {"name": "Me", "asana_user": "", "asana_workspace": ""},
    "timezone": "UTC",
    "language": "en",
    "providers": {},
    "projects": [],
    "weekly_focus": {},
    "routines": [{"name": "Write", "weekdays": [1, 2, 3, 4, 5]}],
    "non_working_dates": [],
}


def validate(config):
    if not isinstance(config, dict) or config.get("version") != 1:
        raise BrainError("Config must be an object with version: 1.")
    try:
        ZoneInfo(config.get("timezone", "UTC"))
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise BrainError("Config timezone must be an installed IANA timezone (for example UTC).") from None
    if not isinstance(config.get("projects"), list):
        raise BrainError("Config projects must be a list.")
    seen = set()
    for project in config["projects"]:
        if not isinstance(project, dict) or not project.get("name") or not isinstance(project.get("id"), str):
            raise BrainError("Each project needs a string id and a name.")
        if project["id"] in seen:
            raise BrainError("Project ids must be unique.")
        seen.add(project["id"])
        if project.get("role", "build") not in ("build", "review", "monitor"):
            raise BrainError("Project role must be build, review, or monitor.")
        for field in ("gitlab_projects", "asana_roots", "meeting_tasks"):
            if not isinstance(project.get(field, []), list):
                raise BrainError(f"Project {field} must be a list.")
    for day, ids in config.get("weekly_focus", {}).items():
        if day not in {str(i) for i in range(1, 8)} or not isinstance(ids, list) or any(p not in seen for p in ids):
            raise BrainError("weekly_focus maps weekdays 1–7 to configured project ids.")
    return config


def load(root):
    try:
        data = json.loads((Path(root) / ".brain/config.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BrainError("Run python3 bin/brain.py init, then edit .brain/config.json.") from None
    except (ValueError, OSError):
        raise BrainError("Cannot read .brain/config.json as JSON.") from None
    return validate(data)


def credential(spec):
    """Read exactly one configured source; never fall back to another identity."""
    if not isinstance(spec, dict) or len(spec) != 1:
        raise BrainError("credential needs exactly one source: env, command, or keychain.")
    if "env" in spec:
        value = os.environ.get(spec["env"], "")
    else:
        if "keychain" in spec:
            entry = spec["keychain"]
            command = ["security", "find-generic-password", "-s", entry["service"], "-a", entry["account"], "-w"]
        else:
            command = spec.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise BrainError("Credential command must be a nonempty argument array, without a shell.")
        command = [str(Path(command[0]).expanduser()), *command[1:]]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=True)
            value = result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            raise BrainError("Credential provider failed. Check its local setup; output was withheld.") from None
    if not value or "\n" in value or "\r" in value:
        raise BrainError("Credential provider returned an empty or invalid value.")
    return value

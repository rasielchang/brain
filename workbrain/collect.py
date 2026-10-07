"""Build one complete snapshot before publishing any local output."""
import datetime as dt
import urllib.parse
from zoneinfo import ZoneInfo

from .clients import API, TASK_FIELDS, task_tree
from .config import credential
from .storage import BrainError


def active(project):
    return project.get("active", True) and project.get("status") != "paused"


def collect(config, now=None, factory=API):
    now = now or dt.datetime.now(ZoneInfo(config.get("timezone", "UTC")))
    clients = {}

    def client(name):
        if name not in clients:
            spec = config.get("providers", {}).get(name)
            if not spec:
                raise BrainError(f"Configure providers.{name} before enabling its projects.")
            default = "https://app.asana.com/api/1.0" if name == "asana" else "https://gitlab.com/api/v4"
            clients[name] = factory(spec.get("base_url", default), credential(spec.get("credential")), name)
        return clients[name]

    projects = []
    excluded_tasks, excluded_projects = set(), set()
    for project in config["projects"]:
        if not active(project):
            excluded_projects.add(str(project.get("asana_project", "")))
            excluded_tasks.update(map(str, project.get("asana_roots", [])))
            continue
        tasks, meetings, repos = [], [], []
        if project.get("asana_project") or project.get("asana_roots"):
            tasks = task_tree(client("asana"), project.get("asana_project"), project.get("asana_roots", []))
        for gid in project.get("meeting_tasks", []):
            stories = client("asana").all(f"/tasks/{gid}/stories", {
                "opt_fields": "text,created_at,created_by.name,resource_subtype"})
            meetings.extend({**story, "task_gid": str(gid)} for story in stories
                            if story.get("resource_subtype") == "comment_added")
        for pid in project.get("gitlab_projects", []):
            prefix = "/projects/" + urllib.parse.quote(str(pid), safe="")
            gl = client("gitlab")
            repo = gl.one(prefix)
            commits = gl.all(prefix + "/repository/commits", {
                "since": (now - dt.timedelta(days=7)).isoformat(), "until": now.isoformat()})
            mrs = gl.all(prefix + "/merge_requests", {"state": "opened"})
            repos.append({"name": repo["path_with_namespace"], "url": repo["web_url"],
                          "commits": [{k: c.get(k) for k in ("id", "title", "committed_date", "web_url")} for c in commits],
                          "merge_requests": [{k: m.get(k) for k in ("iid", "title", "web_url", "source_branch", "target_branch", "draft", "created_at")} for m in mrs]})
        projects.append({"id": project["id"], "name": project["name"], "role": project.get("role", "build"),
                         "tasks": tasks, "meetings": sorted(meetings, key=lambda x: x["created_at"])[-20:],
                         "repos": repos})
    # Owner assignments include future deadlines and work outside mapped projects.
    # Unmapped assignments are shown for triage, not automatically prioritized.
    owner = config.get("owner", {})
    assignments = []
    if owner.get("asana_user") and owner.get("asana_workspace"):
        assignments = client("asana").all("/tasks", {
            "assignee": owner["asana_user"], "workspace": owner["asana_workspace"],
            "completed_since": "now", "opt_fields": TASK_FIELDS + ",projects"})
        ancestry = {}

        def excluded(task):
            visited = set()
            while task:
                gid = task["gid"]
                if gid in excluded_tasks or any(p["gid"] in excluded_projects for p in task.get("projects", [])):
                    return True
                if gid in visited:
                    raise BrainError("Asana parent cycle; cannot verify paused-project scope.")
                visited.add(gid)
                parent = task.get("parent")
                if not parent or not (excluded_tasks or excluded_projects - {""}):
                    return False
                pgid = parent["gid"]
                if pgid not in ancestry:
                    ancestry[pgid] = client("asana").one(f"/tasks/{pgid}", {"opt_fields": "parent,projects"})
                task = ancestry[pgid]
            return False

        assignments = [t for t in assignments if not t.get("completed") and not excluded(t)]
    return {"schema_version": 1, "collected_at": now.isoformat(), "demo": False,
            "projects": projects, "assignments": assignments,
            "limits": ["Assignment changes need story lookup; modified_at is not assignment time.",
                       "Commit counts do not prove delivery, deployment, or customer acceptance.",
                       "Local agent sessions and source documents require opt-in interactive review."]}

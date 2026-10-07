"""Deterministic evidence summaries, without invented priority or completion."""
import datetime as dt
from zoneinfo import ZoneInfo


def text(value):
    return str(value or "").replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def link(title, url):
    title = text(title).replace("[", "\\[").replace("]", "\\]")
    if not str(url or "").startswith("https://"):
        return title
    return f"[{title}](<{str(url).replace('>', '%3E').replace(chr(10), '')}>)"


def render(snapshot, config, kind="today", date=None):
    day = date or dt.date.fromisoformat(snapshot["collected_at"][:10])
    if isinstance(day, str):
        day = dt.date.fromisoformat(day)
    titles = {"today": "Today", "weekly": "Weekly review", "radar": "Risk radar", "portfolio": "Portfolio"}
    lines = [f"# {titles[kind]} · {day}", "", f"Evidence snapshot: {snapshot['collected_at']}", ""]
    if snapshot.get("demo"):
        lines += ["> DEMO — all people, projects, and records below are fictional.", ""]
    lines += ["> Source summary. Priority, deployment, and acceptance require verification.", ""]
    holiday = day.isoformat() in config.get("non_working_dates", [])
    if holiday:
        lines += ["## Non-working day", "", "No work is scheduled. The following is status only.", ""]
    focus = [] if holiday else config.get("weekly_focus", {}).get(str(day.isoweekday()), [])
    owner = str(config.get("owner", {}).get("asana_user", ""))
    mapped = {t["gid"] for p in snapshot["projects"] for t in p["tasks"]}
    lines += ["## Owner deadlines — triage, not an urgency ranking", ""]
    due_tasks = {t["gid"]: t for t in snapshot.get("assignments", [])}
    for project in snapshot["projects"]:
        for task in project["tasks"]:
            if owner and str((task.get("assignee") or {}).get("gid")) == owner:
                due_tasks[task["gid"]] = task
    count = 0
    for task in sorted(due_tasks.values(), key=lambda t: (t.get("due_on") or "9999", t["gid"])):
        if task.get("completed"):
            continue
        due = task.get("due_on")
        if due and dt.date.fromisoformat(due) > day + dt.timedelta(days=45):
            continue
        count += 1
        note = "outside mapped task trees; check project/paused status" if task["gid"] not in mapped else "verify latest waiting/delivery state"
        lines.append(f"- {link(task['name'], task.get('permalink_url'))} — due {due or 'not set'}; {note}.")
    if not count:
        lines.append("- No owner deadlines found in the configured scope. This does not establish that there is no urgent work.")
    lines += ["", "## Projects", ""]
    by_id = {p["id"]: p for p in snapshot["projects"]}
    order = list(dict.fromkeys([p for p in focus if p in by_id] + list(by_id)))
    week_start = day - dt.timedelta(days=day.weekday())
    zone = ZoneInfo(config.get("timezone", "UTC"))

    def this_week(commit):
        raw = commit.get("committed_date")
        if not raw:
            return False
        local_date = dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(zone).date()
        return week_start <= local_date <= day

    for pid in order:
        project = by_id[pid]
        current = [c for repo in project["repos"] for c in repo["commits"]
                   if this_week(c)]
        lines += [f"### {text(project['name'])} · {project['role']}" + (" · today's focus" if pid in focus else ""), ""]
        if current:
            lines.append(f"- This week: {len(current)} recorded commit(s); delivery/acceptance still requires verification.")
        else:
            lines.append("- This week: no verified progress in the fetched code evidence; check non-code work and approved session sources.")
        incomplete = [t for t in project["tasks"] if not t.get("completed")]
        lines.append(f"- Open tasks: {len(incomplete)} (including nested subtasks).")
        if project["meetings"]:
            story = project["meetings"][-1]
            lines.append(f"- Meeting note ({story['created_at'][:10]}, unverified source statement): {text(story['text'])}")
        for repo in project["repos"]:
            for mr in repo["merge_requests"]:
                label = f"{repo['name']} !{mr['iid']} — {mr['title']}"
                lines.append(f"- Open MR: {link(label, mr['web_url'])}; {text(mr['source_branch'])} → {text(mr['target_branch'])}; next actor unverified.")
        if pid in focus:
            lines.append("- Next step: verify the latest commitment, remaining work, and owner before selecting an action.")
        if kind == "radar":
            lines.append("- Verify: do commitments match delivery evidence? Waiting on whom? No risk is inferred from commit count alone.")
        lines.append("")
    if not order:
        lines += ["No active projects configured.", ""]
    lines += ["## Routines", ""]
    routines = [] if holiday else [r for r in config.get("routines", []) if day.isoweekday() in r.get("weekdays", []) and day.isoformat() >= r.get("start_on", "")]
    lines += [f"- {text(r['name'])}: today's completion not reported." for r in routines] or ["- No routines scheduled."]
    lines += ["", "## Questions and evidence gaps", "", "- What changed since this snapshot? Check sources before taking action.",
              "- Which item needs the owner next, and what is the impact of waiting?", ""]
    return "\n".join(lines)

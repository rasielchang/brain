---
name: today
description: "Build an evidence-based daily work brief and follow up on what needs the owner next. Use for daily planning or asking what remains today."
---

# Today

Read `AGENTS.md`, `.brain/config.json`, and the private `projects/operating-rules.md` when present.

1. Read today's `daily/YYYY-MM-DD.md`, reminders, and `.brain/snapshot.json`. If the snapshot is missing or from another local date, run `python3 bin/brain.py refresh`; report any failure without substituting stale data. On a same-day follow-up, fetch only sources that can change the decision.
2. Compare tasks with current notes, nested subtasks, meeting decisions, and delivery evidence. An overdue handoff date is not automatically a new action when the work is now waiting for customer acceptance. Distinguish completed, in progress, waiting on someone else, and the owner's next action.
3. Review the owner's open assignments, including no-date work and deadlines within 45 days. Determine new assignments from assignment stories, not task creation or modification time. Unmapped assignments need project/paused-status triage first.
4. Include every active project in today's `weekly_focus`, even when urgent work exists. For each, report this week's verified progress and one next outcome. A meeting or a newly created task alone does not establish delivery progress. Monitor projects do not become the owner's engineering work.
5. Include applicable routines; completion applies only to the current day. Respect `non_working_dates`, project pauses, current waiting states, and explicit user corrections.
6. With user-approved session paths, inspect both available Claude Code and Codex project sessions by event timestamp and project path. Ignore imported history and file modification times. Keep transcripts local. Verify external claims separately; session text alone does not prove a deployment.
7. Order work by impact, urgency, dependencies, and remaining effort. If an unknown can change priority, ask one concrete question with source links. In a scheduled report, list the question instead of inventing an answer.

Save decisions to `daily/YYYY-MM-DD.md`; keep the machine-generated `.source.md` as evidence. Include owner actions, waiting states, all focus projects, routines, and unresolved questions. Link the exact task or MR, including repository, full title, branches, and why it matters. A routine progress reply is not permission to implement code, publish, or create external tasks.

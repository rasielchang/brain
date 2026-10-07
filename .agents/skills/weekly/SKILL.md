---
name: weekly
description: "Prepare a cross-project weekly review with commitments, verified progress, owners, and decisions. Use for weekly meeting preparation."
---

# Weekly

Read `AGENTS.md`, `.brain/config.json`, the private operating rules, reminders, and the latest snapshot. Refresh stale evidence with `python3 bin/brain.py refresh`.

- Cover every active project, including monitor/review roles. Exclude paused projects. Identify the actual owner of each action rather than assigning everything to the user.
- Compare the previous week's commitments with task/subtask state, dated meeting comments, commits, MRs, and verified delivery. Include non-code work; zero commits is not proof of inactivity.
- Review all configured focus projects individually. Report evidence of progress, current blockers, next intended outcome, and dates explicitly supported by sources.
- With approved session paths, include actual recent project work from both available agent tools. Verify claims of merge, deployment, or acceptance before presenting them as facts.
- Separate decisions the user must make, reminders to the PM/team, and customer/external waiting. Give enough context to decide: options, impact, deadlines, and direct links.
- Keep uncertain commitments or estimates visible. Do not invent meeting dates from a recurring focus day.

Save the review to `weekly/YYYY-MM-DD.md`. Include all project states, fixed-focus progress, upcoming commitments, owner decisions, and questions for the meeting. This prepares the meeting; it does not authorize external updates or messages.

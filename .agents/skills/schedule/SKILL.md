---
name: schedule
description: "Propose task dates using effort, dependencies, capacity, and existing commitments, then record the agreed schedule. Use when the user asks to schedule project work."
---

# Schedule

Read `AGENTS.md`, config, private operating rules, current tasks/subtasks, existing dates, and reminders. Refresh relevant live task data before drafting changes.

Propose start and due dates with their basis: remaining effort, dependencies, working days, holidays, capacity shared with other projects, and customer commitments. Ask about gaps that materially change the schedule. Do not treat an empty due date as evidence that work is unimportant.

Preserve user-provided dates and existing authorization. Present unresolved changes as a concrete table of task link, current date, proposed date, start reminder, and reason. Obtain a decision only for changes not already authorized.

- Record starts in `reminders.md` as local reminders.
- Update external due dates only when explicitly requested/approved and an authenticated write tool is available. The bundled Python collector is read-only. Otherwise save a proposal under `.brain/proposals/` and clearly report that external dates remain unchanged.
- Do not silently change assignees, duplicate assignments on parent and child, or infer a completion date from a test window.
- Immediately before writing, read the current task; preserve unrelated fields and existing history. Read back each change and record its source. Stop on an ambiguous response and reconcile before retrying.

A scheduling request authorizes schedule work, not implementation, payments, deployment, or notifying other people.

---
name: radar
description: "Compare project commitments with verified execution evidence to identify delivery risks, missing ownership, and unresolved dependencies. Use for a project risk review."
---

# Radar

Read `AGENTS.md`, configuration, private operating rules, and current snapshots/reports. Fetch missing or stale evidence before reaching a conclusion.

Check each active project's commitments against its actual execution evidence. Inspect task trees and recent meeting comments; for code deliverables inspect relevant commits, MRs, and pipeline/deployment results. The snapshot's commit/MR lists are a starting point, not complete proof of deployment.

Report only supported risks:
- A commitment and evidence disagree: quote the dated commitment briefly and link the exact contrary evidence.
- Remaining effort plus dependencies threaten a known deadline. If effort or impact is unknown, ask; do not manufacture a numerical forecast.
- A blocker persists across dated observations, or a configured focus project has no verified progress after its planned work day.
- Work has progressed without a corresponding handoff, acceptance decision, or task record.

Each finding needs an owner, consequence, source links, uncertainty, and smallest useful next action. PM/customer work stays with that owner. Non-code deliverables require their own evidence; zero commits alone is not a risk. Check local project sessions only within user-approved paths, and verify their external claims.

Save `weekly/radar-YYYY-MM-DD.md`. If evidence is missing, label it unknown rather than healthy or failed. Do not create tasks, change dates, or repair product code as a side effect of the review.

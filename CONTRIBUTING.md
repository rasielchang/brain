# Contributing

Use fictional projects, tasks, transcripts, and tokens. Never attach a real
`.brain/` directory, meeting document, API response, customer screenshot, or agent log.

Before proposing a change:

```bash
python3 -m unittest discover -s tests -v
python3 bin/check-release.py
```

Tests should verify outcomes: complete pagination, nested tasks, preserved reports
on failure, paused-project behavior, and authorization boundaries. Do not make live
API requests or paid model calls in CI.

For a new integration, keep collection read-only, document what the source can
and cannot prove, and supply synthetic API fixtures. Do not silently turn errors
into empty successful results. External mutation support should be reviewed as a
separate feature with explicit intent, current-state checks, and reconciliation.

Keep workflow logic in `.agents/skills/`. Claude commands should reference it
rather than duplicate it. Public guidance belongs in docs; personal exceptions
belong in the user's ignored workspace.

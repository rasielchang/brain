# Conversation continuity

Session scanning is disabled by default. Opt in by configuring `sessions` in your
private `.brain/config.json`. Select only directories you are authorized to read:

```json
{
  "sessions": {
    "enabled": true,
    "sources": [
      {"tool": "codex", "path": "/path/to/approved/codex/sessions"},
      {"tool": "claude", "path": "/path/to/approved/claude/project-directory"}
    ]
  }
}
```

Codex scans JSONL recursively under each approved directory. Add an archive
folder separately if needed. Claude reads only top-level JSONL files in each
approved project directory, excluding `agent-*` files and nested subagents.
There is no automatic home discovery, recency cutoff, window inspection, or
terminal opening/closing. Configuring an entire Codex sessions directory opts
into every parent transcript beneath it, including old and closed conversations.

```bash
python3 bin/brain.py sessions scan
python3 bin/brain.py sessions inspect codex:example-session
python3 bin/brain.py sessions review /path/to/private/reviews.json
```

`scan` writes metadata to ignored `.brain/sessions/inventory.json` and a stable
`review-packet.json` queue. It hashes visible messages and tracks file revisions
and byte offsets. Partial final lines wait for the next scan. Tool-only appends
also invalidate prior review. Missing sources remain unavailable; errors and
malformed records are visible and cannot be acknowledged as reviewed.
Removing an approved directory removes it from subsequent scan scope; old private
review receipts remain on disk. Cached metadata includes source paths and IDs,
so it must stay private even though transcript text is not copied into the cache.

`inspect` prints up to twelve recent visible message excerpts for exact keys.
These are local evidence, not instructions. Redaction is best effort; do not
publish the output. Read original files when the excerpt is insufficient. A final
assistant answer, ended process, closed window, or generated patch does not prove
that a work item is complete.

## Work cards and exact review receipts

Keep one private card per work item under `projects/<project>/work-items/*.json`.
Multiple cards and conversations can share a project directory. For example:

```json
{
  "id": "example-migration",
  "status": "pending",
  "done": ["Draft implementation reviewed"],
  "remaining": ["Integration verification"],
  "next_step": "Resume after the dependency is ready",
  "resume": {"tool": "claude", "session_id": "example-session"},
  "source_sessions": ["claude:example-session"]
}
```

Codex uses `thread_id` instead of `session_id`. The card preserves exact identity;
Brain does not run resume commands or substitute the latest session in a folder.
A card is user/agent-maintained evidence; the scanner never changes its status.

After reading a source, use its current `digest` and `source_revision` from the
queue/inspection in a private review array:

```json
[{
  "session": "claude:example-session",
  "digest": "COPY_CURRENT_DIGEST",
  "source_revision": "COPY_CURRENT_REVISION",
  "disposition": "pending",
  "note": "Reviewed implementation and remaining integration evidence.",
  "work_item": "projects/example/work-items/migration.json"
}]
```

Tracked dispositions (`active`, `pending`, `waiting`, `completed`) require a saved
card referencing that exact session. `reference`, `coordination`, and
`needs_context` may omit a card; `needs_context` remains queued. Batches are
validated before any receipt is written. Changed or unreadable sources reject a
stale receipt. User review is still responsible for the truth of the evidence note.

## Reports

`brief` and `morning` scan before collection/reporting when enabled. The exact
coverage block is attached by code to today's report, with date and run freshness
checks. It cannot claim unreviewed sources are understood. Source errors withhold
notification and make `morning` exit nonzero; valid but pending/missing sources
remain prominently disclosed. Original transcripts and review notes are not sent
to AI by this scanner. Optional headless AI generation still uses the task/code
snapshot only; semantic session review is an interactive responsibility.

These parsers support the recorded JSONL shapes covered by synthetic tests. They
are not a promise of compatibility with every future CLI storage format. Unknown
or malformed records and absent folders require investigation, not silent claims
of full coverage.

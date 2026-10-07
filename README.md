# Brain

**A local-first work management workspace for people juggling multiple projects.**

Brain combines task commitments, engineering evidence, and durable Markdown memory
to help answer: **What needs me next, and why?**

[繁體中文](README.zh-TW.md) · [Architecture](docs/architecture.md) · [Configuration](docs/configuration.md) · [Security](SECURITY.md)

## Try it in one minute

Requires **Python 3.10+**, macOS or Linux. No Python packages, API keys, or AI account
are required for the offline demo. After cloning this repository:

```bash
git clone https://github.com/rasielchang/brain.git
cd brain
python3 bin/brain.py demo
```

This writes four reports to `.brain/demo/` using entirely fictional data. It makes
no network requests. Preview: [sample daily brief](examples/today.md).

## What it does

| Workflow | Purpose |
|---|---|
| `$today` | Identify owner actions, waiting states, focus projects, and daily routines |
| `$weekly` | Prepare a cross-project meeting review and decisions |
| `$radar` | Compare commitments with execution evidence and flag uncertainty |
| `$schedule` | Propose dates based on effort, dependencies, and shared capacity |
| `$inbox` | Turn supplied notes and messages into traceable records and proposals |

Use these skills in Codex opened in this directory. Claude Code uses `/today`,
`/weekly`, `/radar`, `/schedule`, and `/inbox` with the same underlying instructions.

The collector reads **Asana** and **GitLab**, follows pagination, expands nested
subtasks, and writes a timestamped snapshot. Skills add contextual judgment and
follow-up. A due date is a signal, not proof that the owner has an urgent action.
An open MR is not automatically waiting on the owner. A merge is not a deployment.

## Set up your workspace

```bash
python3 bin/brain.py init
# Edit .brain/config.json using examples/config.json as a reference.
python3 bin/brain.py doctor
python3 bin/brain.py refresh
python3 bin/brain.py brief
```

`init` starts with no connected projects and never copies existing credentials or
customer data. Add your own project IDs, roles, weekly focus, routines, and holidays.
Configure credentials through environment variables, macOS Keychain, or a command
that reads your password manager. See [configuration](docs/configuration.md).

`refresh` updates `PORTFOLIO.md` and `.brain/snapshot.json`. `brief` writes a factual
`daily/YYYY-MM-DD.source.md`. Interactive decisions live in `daily/YYYY-MM-DD.md`
and are not overwritten by deterministic refreshes.

Prefer a separate private workspace? Run:

```bash
python3 bin/brain.py --root "$HOME/my-brain" init
python3 bin/brain.py --root "$HOME/my-brain" refresh
```

The workspace gets the skills and a launcher pointing to this source checkout.
Keep the checkout in place; rerun setup manually if you move it.

## Optional AI reports and automation

With an installed, authenticated CLI:

```bash
python3 bin/brain.py brief --agent codex
# or:
python3 bin/brain.py brief --agent claude
```

This explicitly sends the current snapshot to the selected provider and may use
paid quota. It generates from the supplied evidence; it does not perform a fresh
interactive investigation. Failures and timeouts preserve the existing report.
Use interactive skills when a decision requires deeper source inspection.

```bash
python3 bin/brain.py morning
python3 bin/brain.py launchd --hour 8 --minute 30
```

`morning` refreshes and produces source summaries; on Mondays it includes weekly
and radar summaries. Add `--agent codex` or `--agent claude` to opt into AI reports.
`launchd` generates a plist for review and does **not** activate a schedule.
[Scheduling instructions](docs/automation.md) cover macOS and Linux.

## Data boundaries

- Asana is the task/commitment source; GitLab is engineering evidence.
- Local Markdown preserves decisions and provenance. No database or vector service is required.
- Private config, reports, inbox files, and project memory are Git-ignored.
- The Python collector exposes GET-only API operations. External updates require
  an authorized interactive agent with a separate write tool, or remain local proposals.
- Local agent-session inspection is opt-in through configured project paths.
  There is no automatic whole-home transcript ingestion.
- Source text is untrusted evidence. Review AI conclusions before external actions.

## v0.1 scope

This is a working starter framework extracted from a personal workflow. It includes
read-only Asana/GitLab connectors, five skills, an offline demo, optional AI CLI
reports, and scheduling helpers. LINE webhooks, a web dashboard, GitHub project
collection, autonomous task writes, and automatic session parsing are not included.
Skills describe how an interactive agent can inspect additional approved sources.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 bin/check-release.py
```

Tests use fictional API responses and fake agent processes. They do not consume
model quota or touch customer accounts. See [CONTRIBUTING.md](CONTRIBUTING.md).

MIT licensed. Your private data remains yours; keep it out of public contributions.

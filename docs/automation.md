# Automation

Start with a successful manual `refresh` and `morning` before enabling a schedule.
The default schedule creates deterministic source summaries and makes no AI calls.
The collector is read-only. Reports remain private in your workspace.

## macOS

Generate a launchd plist using the current Python executable and absolute source path:

```bash
python3 bin/brain.py launchd --hour 8 --minute 30
```

Review `.brain/dev.brain.morning.plist`, then install it yourself:

```bash
mkdir -p "$HOME/Library/LaunchAgents"
cp .brain/dev.brain.morning.plist "$HOME/Library/LaunchAgents/dev.brain.morning.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/dev.brain.morning.plist"
```

Stop it with:

```bash
launchctl bootout "gui/$(id -u)/dev.brain.morning"
```

The calendar schedule uses the Mac's local clock; report dates use the configured
timezone. Align them intentionally. Only one installation of this label should be
active. The generator does not inspect or replace an existing installed job.

launchd does not inherit your interactive shell's environment or CLI PATH. Prefer
Keychain or an absolute credential-helper command. For optional AI generation,
add `--agent codex` or `--agent claude` when generating the plist, and add the actual
CLI binary directory to the plist's `EnvironmentVariables.PATH` before installation.
Keep tokens out of plist files. The Python executable path must remain available.

Logs are `.brain/morning.log` and `.brain/morning-error.log`. Failed source fetches
keep the previous snapshot and exit nonzero. Agent timeouts terminate the process
group and preserve the previous report. The lock is released on process exit;
do not remove the lock file to recover a run.

## Linux

Use your existing scheduler. For example, a cron entry with real absolute paths:

```cron
30 8 * * * /usr/bin/python3 /path/to/brain/bin/brain.py --root /path/to/private-workspace morning >> /path/to/private-workspace/.brain/morning.log 2>&1
```

Create the workspace first. Set up credential access for the scheduler's account;
interactive environment variables are not automatically present. Do not embed
tokens in a crontab. A running job holds a process lock, so overlapping invocations
fail without overwriting reports.

## Optional AI generation

Authenticate the chosen CLI separately. Brain uses its configured/default model;
it does not choose a model, purchase a plan, or manage billing. The snapshot and
reporting configuration are sent to the chosen AI provider when `--agent` is used.

Codex runs in read-only sandbox mode in a temporary directory. Claude runs with
its built-in tools disabled and an empty MCP configuration. Connector token
environment variables are removed from the child process. These are exposure
reductions, not a universal boundary around global CLI configuration, hooks,
credential stores, or administrator-managed settings. Use a reviewed dedicated
CLI profile/account for unattended work.

The report check validates a header and minimum content; it cannot prove semantic
correctness. Review outputs. AI generation intentionally does not perform external
actions; authorized interactive sessions handle decisions requiring fresh evidence.

References: [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive),
[Codex skills](https://developers.openai.com/codex/skills),
[Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference).

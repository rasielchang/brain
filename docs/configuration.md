# Configuration

Run `python3 bin/brain.py init`. Edit the private `.brain/config.json`; see
[`examples/config.json`](../examples/config.json) for field names. The example's
placeholder IDs must be replaced before enabling its integrations.

| Field | Meaning |
|---|---|
| `version` | Configuration schema, currently `1` |
| `owner` | Display name, Asana user GID, and workspace GID; empty IDs disable owner assignment collection |
| `timezone` | IANA timezone, such as `UTC` or `Asia/Taipei` |
| `language` | AI report language, such as `en` or `zh-TW`; deterministic source reports are English |
| `projects` | Unique ID, name, role (`build`, `review`, `monitor`), provider mappings |
| `active: false` / `status: paused` | Exclude the project from regular tracking |
| `asana_project` | Optional Asana project GID, including its nested task trees |
| `asana_roots` | Root task GIDs for projects without their own Asana project |
| `meeting_tasks` | Task GIDs whose comments carry meeting progress; retains the latest 20 comments per project in the snapshot |
| `gitlab_projects` | GitLab numeric IDs or `group/repository` paths |
| `session_paths` | Optional project paths approved for interactive session inspection; the collector does not read them |
| `weekly_focus` | Weekday strings `1`–`7` mapped to project IDs; multiple projects per day are supported |
| `routines` | Names and weekdays; optional `start_on` in `YYYY-MM-DD` format |
| `non_working_dates` | Local dates with no scheduled focus work or routines |

## Credentials

Each provider requires exactly one `credential` source. Never put the token itself
in this file. The source choice is explicit; there is no automatic fallback to a
different identity. For GitLab, prefer a token with `read_api` scope.

Environment (supply through your own secret manager or shell setup):

```json
{"credential": {"env": "ASANA_TOKEN"}}
```

Existing macOS Keychain entry:

```json
{"credential": {"keychain": {"service": "your-asana-service", "account": "your-account"}}}
```

Existing credential helper that prints only the token to stdout:

```json
{"credential": {"command": ["/absolute/path/to/read-token", "asana"]}}
```

Command arrays run without a shell and time out after 15 seconds. Their stdout and
stderr are not logged. Commands are trusted local configuration: do not import an
unreviewed config file. Credentials are obtained only when that provider is needed.

Self-hosted GitLab is supported with an HTTPS `base_url`, for example
`https://gitlab.example.com/api/v4`. HTTP and credential-bearing URLs are rejected.
Authentication headers stay within the configured API base; redirects are refused.

`doctor` validates local setup without retrieving tokens or calling APIs.
`refresh` tests access by performing the configured read operations. On failure,
it reports the provider and a safe error category, withholding response bodies.

## Limits worth understanding

- Asana owner assignments are not a new-assignment event stream. Inspect task stories
  before claiming who assigned a task and when.
- A task without an explicit project mapping may need a paused-project check before
  it becomes an owner action. The source summary labels unmapped work for triage.
- GitLab commit collection covers the last seven days on the repository's default
  branch; open MRs are fetched separately. No merge/deployment equivalence is assumed.
- Missing source integrations mean unknown coverage, not no work.

Primary API references: [Asana pagination](https://developers.asana.com/docs/pagination),
[Asana subtasks](https://developers.asana.com/reference/getsubtasksfortask),
[GitLab REST pagination](https://docs.gitlab.com/api/rest/),
[GitLab authentication](https://docs.gitlab.com/api/rest/authentication/).

# Security and private data

Do not publish your working memory. `.gitignore` excludes private config, snapshots,
reports, reminders, project records, and inbox files. Git ignores do not remove files
already committed or copied elsewhere. Use a separate clean repository when sharing
an existing private installation.

The release checker catches known credential formats and tracked private paths;
it is a safeguard, not a full secret or privacy audit. Review every file before
publication. Credentials can also appear in prose, screenshots, URLs, and Git history.

The collector performs GET requests only. API responses, meeting notes, and session
text are untrusted input. They must not become tool instructions. AI CLI output can
be wrong, and CLI sandbox settings do not enforce all of Brain's workflow rules.

Optional AI generation sends work data to your chosen provider. Review the data
and the provider/account settings before enabling it. Brain does not provide local
inference, tenant isolation, encrypted storage, or an external-action approval engine.

For a vulnerability, use the repository's private security reporting feature if
enabled. If unavailable, open an issue asking for a private reporting channel,
without exploit details or sensitive data. Never include real credentials in an issue.

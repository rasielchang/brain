# Repeatable public exports

Use `bin/export-public.py` to contribute reviewed functionality from a private
working copy into an existing, separate public Brain checkout. It is an allowlist
publisher, not an automatic anonymizer. Keep reusable code, synthetic tests, and
generic documentation in a curated source directory. Never point it at a personal
workspace wholesale or copy private Git history.

Create a private manifest using [`examples/public-export.json`](../examples/public-export.json).
Place the real manifest under an ignored directory such as `.brain/`. Configure:

- `source_root`: relative to the manifest's directory.
- `target_repo`, `expected_origin`, `branch`: the existing approved public checkout.
- `files`: exact source/target pairs, with the current public file SHA-256 as
  `base_sha256`; use `null` only for a file that does not yet exist.
- `reviewed_inputs`: private implementation files and reviewed SHA-256 values.
  A changed input stops export until its functionality is deliberately reconciled.
- `private_markers`: customer names, private domains, account IDs, or other identifying
  strings to reject, never credentials. The manifest itself is never exported.
- `author`: the public GitHub username and its GitHub noreply email address.

```bash
# Preview: validate the full candidate without modifying the target.
python3 bin/export-public.py --manifest /path/to/private/export.json

# Write the reviewed commit message to a local text file, then:
python3 bin/export-public.py --manifest /path/to/private/export.json \
  --message-file /path/to/private/commit-message.txt --push
```

Omit `--push` for a local commit. `--apply` stages validated files without a commit;
finish that staged change yourself before running another export. Commit/push
requires the user's authorization; the script is not an authorization mechanism.

The script rejects dirty targets, mismatched origins/branches, unreviewed changes
to existing public files, symlinks, path traversal, common token patterns, personal
home paths, email addresses in source, private markers, and runtime data files.
It checks the complete candidate tree, then clones only the public repo into a
temporary directory, applies exact files, stages exact paths, and runs tests,
`check-release.py`, and whitespace validation before changing the real checkout.
Only path names and rule categories are printed on privacy failure, never matches.

After commit it advances baseline hashes and records the export commit in the
private manifest. Identical repeats create no new commit. If push fails after a
commit, rerun the same command: it can publish only the recorded export commit,
and only when the remote still matches its expected parent (or already contains
that exact commit). It never force-pushes, deletes files/branches, or publishes
unrelated local commits. Use your existing credential helper; no tokens belong in
arguments, the manifest, or the repo.

Review prose and the diff before publication. Pattern checks cannot prove that all
personal meaning has been removed. This exporter only scans the current candidate;
`check-release.py` also checks historical private path names. Neither substitutes
for a separate full-history security audit when importing an unfamiliar repo.

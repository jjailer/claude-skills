# Commit hook

## Traps

- **Registration and code load at different times.** `hooks.json` is read at session start and on
  `/reload-plugins`; the script is re-read on every call. Changing which events register needs a
  reload; changing the script does not.
- **The installed copy may not be this tree.** A marketplace install runs a cached copy pinned to
  the last *pushed* commit. Only a session started with `--plugin-dir` runs this tree, and it
  replaces the installed copy silently — `claude plugin list` still shows the marketplace row
  enabled. Look for `intent-layer@inline` in `/plugin` before reasoning about what the hook does.
- **Don't `marketplace add` this repo's path.** It carries the same marketplace name and replaces
  the GitHub entry machine-wide.

## Verifying a change

The suite's payloads are hand-built, so it can pass against a shape Claude Code doesn't send.
Before calling a change done, trigger it live: commit under a node in a scratch repo, and for the
failure path, commit and exit non-zero in the same call.

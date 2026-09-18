# Commit hook

## Traps

- **Registration and code load at different times.** `hooks.json` is read once, at session start;
  the script is re-read on every call. Changing which events register needs a restart; changing
  the script does not.
- **The installed copy may not be this tree.** A marketplace install runs a cached copy pinned to
  the last *pushed* commit. Check `claude plugin list` for which copy is loaded before reasoning
  about what the hook does.
- **Plugins collide on name, not id.** A disabled install still holds `intent-layer`, so a working
  copy symlinked under `~/.claude/skills/` won't load until the marketplace copy is uninstalled.
  Don't `marketplace add` this repo's path: it carries the same marketplace name and replaces the
  GitHub entry machine-wide.

## Verifying a change

The suite's payloads are hand-built, so it can pass against a shape Claude Code doesn't send.
Before calling a change done, trigger it live: commit under a node in a scratch repo, and for the
failure path, commit and exit non-zero in the same call.

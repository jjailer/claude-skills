---
description: Sweep CLAUDE.md nodes for drift the commit hook cannot see
allowed-tools: Bash(git ls-files:*), Bash(git log:*), Bash(wc:*), Read, Grep, Glob, Task
---

Audit this repo's intent layer for rot.

Use the `auditing-intent-layer` skill for the scope, the fan-out, the six checks, and the report
format. It is read-only: produce the verdict list and stop before editing anything.

If $ARGUMENTS names a path, restrict the sweep to nodes at or under it. Otherwise sweep the whole
layer, both variants.

$ARGUMENTS

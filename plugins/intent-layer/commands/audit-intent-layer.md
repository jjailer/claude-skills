---
description: Sweep CLAUDE.md nodes for drift the commit hook cannot see
allowed-tools: Bash(git ls-files:*), Bash(git log:*), Bash(wc:*), Read, Grep, Glob, Task
---

Audit the intent layer for rot.

The commit hook already catches the easy case — code changing under a node that the same commit
doesn't touch. **This command exists for what the hook is blind to:** a node that went stale because
something *outside* its directory moved, and a node that was true when written but is now merely
restating the code.

## Scope

Enumerate nodes with `git ls-files -- "*CLAUDE.md"`. If `$ARGUMENTS` names a path, restrict to nodes
at or under it. Otherwise sweep all of them.

## Fan out

Dispatch **one agent per node, in parallel** — a single message with multiple tool calls. This
parallelizes almost perfectly by subtree, and doing it serially on a large repo is the reason audits
get skipped. Each agent is read-only and returns findings; it does not edit.

Give each agent its node's path and this checklist:

1. **Dangling references** — every file, symbol, signature, flag, or test the node names, checked
   against the code as it is now. A reference that no longer resolves is a failure, not untidiness:
   it sends a reader somewhere that doesn't exist.
2. **Now-derivable lines** — anything a capable model reading the source would get right on its own.
   These are the lines that quietly accumulate. They pass every review because they aren't *wrong*.
3. **External drift** — the case the hook cannot see. A shared contract moved, a dependency's API
   changed, a rule got generalized into a hub, the sanctioned choice shifted. Check what the node
   claims about anything it does not own.
4. **Narration and tombstones** — changelog lines, commit SHAs, decision dates, and obituaries for
   removed symbols.
5. **Size** — `wc -l`. Over ~200 lines, ask whether the excess is a routing problem: procedures
   belong in a skill, file-shaped rules in `.claude/rules/`, enforcement in a hook.

## Report

Collect the findings into one list, ordered by cost to a reader: dangling references first, then
external drift, then derivable lines, then narration, then size.

For each: the node, the line, and the verdict — **delete**, **correct**, or **move** (and where).

Then stop and show the list. Do not edit until $USER has seen it — a node's owner may have context
the audit doesn't, and a sweep that prunes on its own authority is how load-bearing lines get lost.

If a node is clean, say so in one line. Clean nodes are the expected case for anything recently
touched.

$ARGUMENTS

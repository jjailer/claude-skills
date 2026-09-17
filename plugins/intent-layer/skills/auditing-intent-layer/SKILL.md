---
name: auditing-intent-layer
description: Sweeping an existing CLAUDE.md layer for rot the commit hook cannot see — enumerating committed and local nodes, fanning out one read-only agent per node, and reporting delete/correct/move verdicts without editing. Use when you suspect a layer has drifted, when a node's subject moved somewhere outside its own directory, at the end of a capture campaign, or before trusting a layer you didn't write. Triggers on "audit the CLAUDE.md files", "the intent layer is stale", "check my CLAUDE.md files for drift", "is my intent layer still true", "find stale lines in my CLAUDE.md files".
argument-hint: "[path]"
allowed-tools: Bash(git ls-files:*), Bash(git log:*), Bash(wc:*), Read, Grep, Glob, Agent
---

# Auditing an intent layer

The commit hook already catches the easy case — code changing under a node that the same commit
doesn't touch. **This is for what the hook is blind to:** a node that went stale because something
*outside* its directory moved, and a node that was true when written but now merely restates the
code.

Auditing is read-only. Produce the verdict list and stop before editing anything.

## Scope

If `$ARGUMENTS` names a path, restrict to nodes at or under it. Otherwise sweep both variants:

1. `git ls-files -- '*CLAUDE.md' '*CLAUDE.local.md'` — the committed layer, plus any local node that
   was committed by mistake (flag those: **move** out of the commit).
2. `git ls-files -o -- '*CLAUDE.local.md'` — the local layer, ignored or not. An unignored one is a
   finding too: it is one `git add -A` from being committed.

Keep only paths whose basename is exactly `CLAUDE.md` or `CLAUDE.local.md` — the pathspec also
matches `NOT_CLAUDE.md`.

**The second call is not redundant.** Plain `git ls-files` lists only tracked files, and local nodes
are untracked — they need `-o`. Fold both into one call and half the layer silently stops being
audited. `Glob` is no substitute: it may honour `.gitignore` and find nothing. And this is the only
check a local node gets: the commit hook can remind you to update one, but cannot read it.

Then run `wc -l` once over every node.

## Fan out

Dispatch **one `Explore` agent per node, in parallel** — a single message with multiple tool calls.
Doing it serially on a large repo is the reason audits get skipped. `Explore` has no Edit or Write
tool, so read-only doesn't rest on the prompt alone. Each prompt carries:

- The node's path, its variant, and its `wc -l`.
- **Local node:** the committed `CLAUDE.md` in the same directory, if any, and every committed
  ancestor.
- **Committed node:** the paths outside its directory changed since it was last touched —
  `git log -1 --format=%h -- <node>`, then `git log --name-only --format= <that>..HEAD`, deduped.
- The absolute paths of `../intent-layer/SKILL.md` and `../intent-layer/references/local-nodes.md`,
  resolved from this skill's base directory, with an instruction to Read the sections the table cites before judging —
  `Explore` agents don't load skills.
- *What to check* below, and the brake in one line: *when unsure, keep it; never cut a prohibition or
  agent directive for reading as generic.*
- The return format: rows of `node | line | pass | verdict (delete / correct / move → where) |
  evidence`, or the single word `clean`.

## What to check

Four of the six passes are the `intent-layer` skill's rules turned around: that skill says what earns
a line, and an audit asks whether the lines already present still earn it. **Read the rule there —
this table points, it does not restate.**

| Pass | Look for | Rule |
|---|---|---|
| **Dangling references** | Every file, symbol, signature, flag, or test the node names, checked against the code as it is now. A reference that no longer resolves sends a reader somewhere that doesn't exist. | `intent-layer` → *Maintenance*, "Prefer claims that can't dangle" |
| **Now-derivable lines** | Anything a capable model reading the source would get right on its own. These quietly accumulate: they pass every review because they aren't *wrong*. | `intent-layer` → *Where a rule belongs*, first row |
| **Narration and tombstones** | Changelog lines, commit SHAs, decision dates, and obituaries for removed symbols. | `intent-layer` → *What goes in a node*, "Invariants, not narration" and "Never leave a tombstone" |
| **Size** | The `wc -l` passed in. Over ~200 lines, ask whether the excess is a routing problem rather than a writing one. | `intent-layer` → *Compression*, then *Where a rule belongs* for whatever should move out |

Two passes are the audit's own. Nothing else in the plugin performs them.

**External drift** — the case the hook cannot see, and the reason this skill exists. Check what the
node claims about anything it does not own. For a committed node, a changed outside path that the node
names is a candidate to check, not a verdict. A local node has no last commit, so this pass is
best-effort: check the outside paths it names against the code as it is now.

**Overlap with the committed node** — local nodes only, against the `CLAUDE.md` in the same directory
and every committed ancestor. A local line restating one of theirs is a duplicate that loads last and
outranks its original: **delete**. A local line contradicting one without saying so is an accidental
override: **correct**, by naming what it overrides — see `intent-layer` → *When the node isn't
yours* (`../intent-layer/references/local-nodes.md`), "Never restate — add, or override in the open".

## The brake

One rule overrides all six, and it isn't the audit's to state: **`intent-layer` → *What goes in a
node*, "When unsure, keep it."** Read it there before proposing a single deletion.

Why it matters most here: every pass above pushes toward cutting, and an audit is the one operation
with both the motive and the authority to lose a load-bearing line.

## Report

Merge the agents' rows into one list, ordered by cost to a reader: dangling references first, then
overlap, then external drift, then derivable lines, then narration, then size.

Then stop and show the list. **Do not edit until the user has seen it** — a node's owner may have
context the audit doesn't.

If a node is clean, say so in one line. Clean nodes are the expected case for anything recently
touched.

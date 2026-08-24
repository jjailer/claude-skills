---
name: auditing-intent-layer
description: Sweeping an existing CLAUDE.md layer for rot the commit hook cannot see — enumerating committed and local nodes, fanning out one read-only agent per node, and reporting delete/correct/move verdicts without editing. Use when you suspect a layer has drifted, when a node's subject moved somewhere outside its own directory, at the end of a capture campaign, or before trusting a layer you didn't write. Triggers on "audit the CLAUDE.md files", "the intent layer is stale", "sweep the nodes for rot", "check my CLAUDE.md files for drift", "is my intent layer still true", "prune the intent layer".
---

# Auditing an intent layer

The commit hook already catches the easy case — code changing under a node that the same commit
doesn't touch. **This is for what the hook is blind to:** a node that went stale because something
*outside* its directory moved, and a node that was true when written but is now merely restating the
code.

Auditing is read-only. It produces a list of verdicts, not a diff.

## Scope

Enumerate nodes twice, and sweep the union:

1. `git ls-files -- "*CLAUDE.md"` — the committed layer.
2. `Glob` for `**/CLAUDE.local.md`, excluding `node_modules/`, `vendor/`, and generated trees.

**The second call is not redundant.** Local nodes are gitignored, so `git ls-files` cannot see them at
all — fold this back into one pathspec and half the layer silently stops being audited. This is also
the only automated check a local node gets: the commit hook reminds you to update one, but it cannot
read what you wrote.

If a path was named, restrict to nodes at or under it. Otherwise sweep all of them.

## Fan out

Dispatch **one agent per node, in parallel** — a single message with multiple tool calls. This
parallelizes almost perfectly by subtree, and doing it serially on a large repo is the reason audits
get skipped. Each agent is read-only and returns findings; it does not edit.

Give each agent its node's path and the checks below.

## What to check

Four of the six passes are the `intent-layer` skill's rules turned around: that skill says what earns
a line, and an audit asks whether the lines already present still earn it. **Read the rule there —
this table points, it does not restate.**

| Pass | Look for | Rule |
|---|---|---|
| **Dangling references** | Every file, symbol, signature, flag, or test the node names, checked against the code as it is now. A reference that no longer resolves is a failure, not untidiness — it sends a reader somewhere that doesn't exist. | `intent-layer` → *Maintenance*, "Prefer claims that can't dangle" |
| **Now-derivable lines** | Anything a capable model reading the source would get right on its own. These are the lines that quietly accumulate: they pass every review because they aren't *wrong*. | `intent-layer` → *Where a rule belongs*, first row |
| **Narration and tombstones** | Changelog lines, commit SHAs, decision dates, and obituaries for removed symbols. | `intent-layer` → *What goes in a node*, "Invariants, not narration" and "Never leave a tombstone" |
| **Size** | `wc -l`. Over ~200 lines, ask whether the excess is a routing problem rather than a writing one. | `intent-layer` → *Compression*, then *Where a rule belongs* for whatever should move out |

Two passes are the audit's own. Nothing else in the plugin performs them.

**External drift** — the case the hook cannot see, and the reason this skill exists. A shared contract
moved, a dependency's API changed, a rule got generalized into a hub, the sanctioned choice shifted.
Check what the node claims about anything it does not own. The hook watches a node's own directory;
nothing at all watches the rest of the repo on its behalf.

**Overlap with the committed node** — local nodes only, against the `CLAUDE.md` in the same directory
and every committed ancestor. A local line restating one of theirs is a duplicate that loads last and
outranks its original: **delete**. A local line contradicting one without saying so is an accidental
override: **correct**, by naming what it overrides — see `intent-layer` → *When the node isn't yours*,
"Never restate — add, or override in the open". Neither is visible to anyone reading only the
committed layer, which is why this pass has to look.

## The brake

One rule overrides all six, and it isn't the audit's to state: **`intent-layer`'s "When unsure, keep
it — and never cut a prohibition for reading as generic."** Read it there before proposing a single
deletion.

Why it matters most here: every pass above pushes toward cutting, and an audit is the one operation
with both the motive and the authority to lose a load-bearing line. "Never push to main" and "never
edit `generated/`" look generic — generic is what safety-critical prohibitions look like when they are
working.

## Report

Collect the findings into one list, ordered by cost to a reader: dangling references first, then
overlap, then external drift, then derivable lines, then narration, then size.

For each: the node, the line, and the verdict — **delete**, **correct**, or **move** (and where).

Then stop and show the list. **Do not edit until the user has seen it** — a node's owner may have
context the audit doesn't, and a sweep that prunes on its own authority is how load-bearing lines get
lost.

If a node is clean, say so in one line. Clean nodes are the expected case for anything recently
touched.

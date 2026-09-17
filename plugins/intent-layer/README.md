# intent-layer

Keeps `CLAUDE.md` intent-layer nodes honest — the hierarchy of `CLAUDE.md` files that carries
contracts, traps, and the sanctioned choice alongside the code.

The organizing principle: **a node carries only what a capable model cannot re-derive from the
source.** The WHAT is a grep away. A node's budget goes to the WHAT NOT and the WHY.

## Components

Two halves: capture builds a layer, and everything else keeps it honest. Every entry point is a
skill, named for the discipline, and loadable by anything — you, another skill, the hook.

| Piece | What it does | When it costs anything |
|---|---|---|
| `intent-layer` skill | The doctrine — where a node belongs, what earns a line, where a rule goes when a node isn't the answer, how hard to compress, when to delete. | On demand, when you create, edit, or review a `CLAUDE.md`. |
| `/intent-layer:capturing-intent-layer [path]` | Establishes a layer on a repo that has none, by interviewing you leaf-first. Asks up front whether the repo's `CLAUDE.md` files are yours to commit; if they aren't, the layer goes to gitignored `CLAUDE.local.md` and supplements them. Resumable; a campaign outlives the session. Docs in scope are read as evidence: where one disagrees with the code or waits on something the code can't show (a migration, a vendor), you're asked with no answer recommended, and every doc citation shows its age — e.g. *`docs/adr/001.md` (changed 2024-06-10, 4 chunk commits since) says webhooks enqueue; `handler.py` charges directly. Which is true?* | Only when you type it — it never starts on its own, because it writes files — plus the attention it asks for. |
| `/intent-layer:auditing-intent-layer [path]` | Sweep for drift the commit hook can't see — a node rots when something *outside* its directory moves. Read-only; reports delete/correct/move verdicts and stops. | When you invoke it, or when you ask whether a layer is stale. |
| `/intent-layer:harvesting-pitfalls [focus]` | Triage of this session's friction — what a real pitfall looks like and which tier it belongs in. Shows each capture before writing it. | When the hook's harvest fires, or you invoke it because the bar didn't trip but you know something happened. |
| Commit hook | On `git commit`, reports any node whose directory has changed code the same commit doesn't touch, and flags a session that shows signs of a recurring pitfall. | Nothing unless it speaks. |

Upgrading from 1.x: the `/capture-intent-layer`, `/audit-intent-layer`, and `/harvest-pitfalls`
commands are gone. Use the skills above.

## The hook is built to stay quiet

It says nothing when a commit updates code and its node together, nothing when the change sits under
no node, and nothing about the repo root unless a top-level file changed — a root node nominally sits
above everything, and a reminder that always fires is one you learn to ignore. Replayed over a
14-node repo's history it spoke on 2 commits in 8.

It reads the commit the way git will make it: files staged in the same call
(`git add foo && git commit -m …`), pathspec commits, `-a`, `git -C <dir> commit`, and commits run
from a subdirectory all count.

A `CLAUDE.local.md` is gitignored, so it can never be in the commit and that first test would never
strike it — a reminder that fires forever. It gets the same rule off a different clock instead: it is
struck by being newer than the code implicating it, which is what "edit code, edit node, commit"
already produces. Deletions are the deliberate exception; a `git rm` under a node is when it most
likely has a tombstone to prune, so those still speak.

One more case earns a sentence: a directory someone else lands, carrying its own `CLAUDE.md` with no
local node beside it yet. Where the repo gitignores `CLAUDE.local.md`, the hook adds a line pointing
at the sibling to start instead. That fires once per directory — the sibling then resolves ahead of
the committed node, and the reminder is ordinary again.

That silence is also how you tell whether a capture held the bar. A layer with more nodes than it
earned turns a quiet reminder into a constant one. Measure it on any repo:

```
python3 plugins/intent-layer/hooks/intent_layer_check.py --replay 30
# {"commits": 30, "fired": 7, "rate": 0.233, "local_upper_bound": false, "nodes": {...}}
```

Capture runs this before it lands and merges nodes upward above roughly 1 in 3.

The pitfall harvest holds the same bar. It needs two independent signals of real friction before it
speaks, reports each signal once per session rather than once per commit, and gives an explicit cheap
exit — *iteration is not a pitfall.* Without that exit a review prompt manufactures findings to
justify itself.

Requires `python3` on `PATH`.

## State outside the repo

Nothing the plugin keeps between runs lives in your repo:

- `~/.claude/intent-layer/harvest/` — which harvest signals each session has already reported.
  Files older than 14 days are removed.
- `~/.claude/intent-layer/capture/` — a capture campaign's progress, keyed by repo, emptied when the
  campaign closes.

## Tests

```
python3 -m unittest discover -s plugins/intent-layer/tests
```

They build real repos and need nothing beyond git and python3. Most cases are ways the hook goes
*wrong* rather than ways it goes right, because both failure directions are silent: one gets the hook
disabled, the other is never noticed.

## Credit

The Intent Layer concept originates with **Tyler Brandt at Intent Systems** —
[The Intent Layer](https://intent-systems.com/blog/intent-layer), which describes it as "a thin,
hierarchical context system that lives *inside* your repo."

This plugin is an independent implementation of that idea for Claude Code: the doctrine for authoring
nodes, plus the hook and skills that keep them from rotting. Any opinion here that the original
doesn't hold is mine, not theirs.

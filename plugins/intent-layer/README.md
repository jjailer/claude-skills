# intent-layer

Keeps `CLAUDE.md` intent-layer nodes honest — the hierarchy of `CLAUDE.md` files that carries
contracts, traps, and the sanctioned choice alongside the code.

The organizing principle: **a node carries only what a capable model cannot re-derive from the
source.** The WHAT is a grep away. A node's budget goes to the WHAT NOT and the WHY.

## Components

Two halves: `/capture-intent-layer` builds a layer, and everything else keeps it honest.

| Piece | What it does | When it costs anything |
|---|---|---|
| `intent-layer` skill | The doctrine — where a node belongs, what earns a line, how hard to compress, when to delete. | On demand, when you create, edit, or audit a `CLAUDE.md`. |
| `capture-intent-layer` skill | The interview — how to earn a question from the code, how parents are written from their children, where a shared fact belongs. | On demand, during a capture. |
| `harvest-pitfalls` skill | The triage — what a real pitfall looks like and which tier it belongs in. | On demand, when a harvest fires or you invoke it. |
| Commit hook | On `git commit`, reports any node whose directory has changed code the same commit doesn't touch, and flags a session that shows signs of a recurring pitfall. | Nothing unless it speaks. |
| `/capture-intent-layer` | Establishes a layer on a repo that has none, by interviewing you leaf-first. Asks up front whether the repo's `CLAUDE.md` files are yours to commit; if they aren't, the layer goes to gitignored `CLAUDE.local.md` and supplements them. Resumable; a campaign outlives the session. | When you type it, plus the attention it asks for. |
| `/harvest-pitfalls` | Manual harvest, for when the bar didn't trip but you know something happened. | When you type it. |
| `/audit-intent-layer` | On-demand sweep for drift the commit hook can't see — a node rots when something *outside* its directory moves. | When you type it. |

## The hook is built to stay quiet

It says nothing when a commit updates code and its node together, nothing when the change sits under
no node, and nothing about the repo root unless a top-level file changed — a root node nominally sits
above everything, and a reminder that always fires is one you learn to ignore. Replayed over a
14-node repo's history it spoke on 2 commits in 8.

A `CLAUDE.local.md` is gitignored, so it can never be in the commit and that first test would never
strike it — a reminder that fires forever. It gets the same rule off a different clock instead: it is
struck by being newer than the code implicating it, which is what "edit code, edit node, commit"
already produces. Deletions are the deliberate exception; a `git rm` under a node is when it most
likely has a tombstone to prune, so those still speak.

One more case earns a sentence: a directory someone else lands, carrying its own `CLAUDE.md` with no
local node beside it yet. The hook names the file you may not be able to edit, so where the repo
gitignores `CLAUDE.local.md` it adds a line pointing at the sibling to start instead. That fires once
per directory — the sibling then resolves ahead of the committed node, and the reminder is ordinary
again.

That silence is also how you tell whether a capture held the bar. Nodes are what the hook watches, so
a layer with more nodes than it earned turns a quiet reminder into a constant one. If the hook starts
speaking on every commit after a campaign, the campaign wrote nodes that hadn't earned their
directory — `/capture-intent-layer` measures the rate before it lands and merges upward above roughly
1 in 3.

What the node section does — which node a path resolves to, and what counts as having updated it —
is pinned by `hooks/test_intent_layer_check.py`. Run it with `python3 hooks/test_intent_layer_check.py`;
it builds real repos and needs nothing beyond git and python3. Most of its cases are ways the
reminder goes *wrong* rather than ways it goes right, because both failure directions are silent:
one gets the hook disabled, the other is never noticed.

The pitfall harvest holds the same bar. It needs two independent signals of real friction before it
speaks, fires once per session rather than once per commit, and gives an explicit cheap exit —
*iteration is not a pitfall.* Without that exit a review prompt manufactures findings to justify
itself.

Requires `python3` on `PATH`.

## Credit

The Intent Layer concept originates with **Tyler Brandt at Intent Systems** —
[The Intent Layer](https://intent-systems.com/blog/intent-layer), which describes it as "a thin,
hierarchical context system that lives *inside* your repo."

This plugin is an independent implementation of that idea for Claude Code: the doctrine for authoring
nodes, plus the hooks and commands that keep them from rotting. Any opinion here that the original
doesn't hold is mine, not theirs.

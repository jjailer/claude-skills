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
| `/intent-layer:capturing-intent-layer [path]` | Establishes a layer on a repo that has none, by interviewing you leaf-first. Asks up front whether the repo's `CLAUDE.md` files are yours to commit; if they aren't, the layer goes to gitignored `CLAUDE.local.md` and supplements them. Resumable; a campaign outlives the session. An answer is marked recommended only when a doc and the code agree on it; a guess from code alone never is, so an unmarked question is deliberate. Docs in scope are read as evidence: where one disagrees with the code or waits on something the code can't show (a migration, a vendor), you're asked with no answer recommended, and every doc citation shows its age — e.g. *`docs/adr/001.md` (changed 2024-06-10, 4 chunk commits since) says webhooks enqueue; `handler.py` charges directly. Which is true?* | Only when you type it — it never starts on its own, because it writes files — plus the attention it asks for. |
| `/intent-layer:auditing-intent-layer [path]` | Sweep for drift the commit hook can't see — a node rots when something *outside* its directory moves. Read-only; reports delete/correct/move verdicts and stops. | When you invoke it, or when you ask whether a layer is stale. |
| `/intent-layer:harvesting-pitfalls [focus]` | Triage of this session's friction — what a real pitfall looks like and which tier it belongs in. Shows each capture before writing it. | When the hook's harvest fires, or you invoke it because the bar didn't trip but you know something happened. |
| Commit hook | After a `git commit` lands, reports any node whose directory has changed code the same commit doesn't touch, and flags a session that shows signs of a recurring pitfall. | Nothing unless it speaks. |

Upgrading from 1.x: the `/capture-intent-layer`, `/audit-intent-layer`, and `/harvest-pitfalls`
commands are gone. Use the skills above.

## The hook is built to stay quiet

It says nothing when a commit updates code and its node together, nothing when the change sits under
no node, nothing for a file its node's `implicated-by` line leaves out (see *Narrowing what
implicates a node*), and nothing about the repo root unless a top-level file changed — a root node
nominally sits above everything, and a reminder that always fires is one you learn to ignore.
Replayed over a 14-node repo's history it spoke on 2 commits in 8.

A rename counts as both of its paths. A file moved out of a node's directory implicates the node it
left as well as the one it joined, since the node it left may still name it.

It reads the commit git actually made, never the command that made it. Detection is git's own
summary line — `[main 1a2b3c4]` — checked against the repo before it is trusted, so files staged in
the same call (`git add foo && git commit -m …`), pathspec commits, `-a`, `git -C <dir> commit`,
commits run from a subdirectory, and anything wrapped in `$(…)` or `bash -c` all count without the
hook having to understand any of it. A `git commit -q` prints no summary, so HEAD stands in — but
only for a commit made seconds ago, on a call that succeeded.

Two cases say nothing because a reminder there would be wrong rather than merely noisy. A commit git
refused — an empty index, a rejecting pre-commit hook, a denied tool call — leaves nothing to update
a node for. And a merge commit re-reports work the branch's own commits already spoke about, so it is
skipped, which is also what `--replay` does.

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

Capture runs this before it lands. Above roughly 1 in 3 it merges nodes upward, or narrows one (next
section).

The pitfall harvest holds the same bar. It needs two independent signals of real friction before it
speaks, reports each signal once per session rather than once per commit, and gives an explicit cheap
exit — *iteration is not a pitfall.* Without that exit a review prompt manufactures findings to
justify itself.

Requires `python3` on `PATH`.

## Narrowing what implicates a node

Some nodes cover a subtree's *conventions*, not every file in it. A test suite's node about
markers, shared fixtures, and driver helpers is the usual case. Every regression test added beneath
it implicates it, yet a new test rarely makes one of its lines false. That node can list the files
that do implicate it, on a line of its own anywhere in the node:

```markdown
<!-- intent-layer: implicated-by conftest.py telenium_helpers.py fixtures/** -->
```

- **Globs, relative to the node's directory**, whitespace-separated, matched against the rest of
  the path one segment at a time. Inside a segment, `*`, `?`, and `[…]` are `fnmatch` patterns
  (case-sensitive) that never cross a `/`. A `**` segment matches zero or more whole directories.
  So `conftest.py` means only the one beside the node; `**/conftest.py` means every one beneath it,
  including that one; `fixtures/**` means everything under `fixtures/`. Stray slashes are
  forgiven: `./x` and `/x` mean `x`, and `dir/` means `dir/**`.
- **A file the globs don't match implicates nothing.** Not this node, and not an ancestor either:
  the nearest node owns its subtree, and the declaration says the rest of it isn't intent-layer
  news. That includes deletions. If the node names a file by path, put that file in the
  declaration: a rename counts as its old path too, so the reminder then fires.
- **Absent unless well-formed.** The line must stand alone, so the syntax quoted in prose (in
  backticks) or inside a fenced code block doesn't count. The first such line wins. If the line is
  empty or unreadable, the node behaves as if it had no declaration. It never behaves as if no file
  implicates it.
- **A `CLAUDE.local.md` beside a `CLAUDE.md`** uses its own declaration if it has one, and its
  sibling's otherwise.
- **Read from the working tree**, for `CLAUDE.md` and `CLAUDE.local.md` alike, not from the commit.
  An unstaged edit to the line already narrows the commit being judged. `--replay` judges history
  by the declaration as it stands now, so to measure a candidate line, add it and replay.

Don't use it on a node that describes the files beneath it one by one, such as a widget catalogue.
There every file is the node's business, and narrowing hides real drift.

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

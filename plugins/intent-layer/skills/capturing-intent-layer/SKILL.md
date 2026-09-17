---
name: capturing-intent-layer
description: Establish an intent layer on a repo that has none, or resume one in progress — survey and chunk the repo, interview you leaf-first, and roll children's nodes up into parents. A resumable campaign across sessions. User-invoked only, because it writes files.
argument-hint: "[path]"
disable-model-invocation: true
allowed-tools: Bash(git ls-files:*), Bash(git log:*), Bash(git shortlog:*), Bash(git diff:*), Bash(git rev-parse:*), Bash(git rev-list:*), Bash(git check-ignore:*), Bash(grep:*), Bash(wc:*), Bash(xargs -0 cat:*), Read, Grep, Glob, Agent, Skill, AskUserQuestion, Write, Edit
---

# Capture an intent layer

Everything else in this plugin maintains a layer someone already built. This is how one gets built:
read the code, then ask the person who knows what the code doesn't say.

**Capture does not get its own bar.** It gets a procedure. What earns a line, how hard to compress,
and where a node belongs stay with the `intent-layer` skill, unchanged — capture is the only additive
operation in the plugin, and an additive operation holding a friendlier bar is how a repo acquires
twenty nodes of `ls` output.

> **Chunking decides where you look. The interview decides where you write.** A chunk that produced
> nothing a model can't re-derive produces no node.

If invoked with a path (`$ARGUMENTS`), restrict the campaign to it.

## Phase 0 — Survey

Read-only, no questions yet. First look for campaign state (`references/campaign-state.md`).

```
git ls-files | wc -l
git rev-parse HEAD
```

Enumerate existing nodes exactly as the `auditing-intent-layer` skill's *Scope* does — both calls,
because local nodes are untracked. Find manifests and measure **source bytes** with the commands in
`references/chunking-signals.md`, using the exclusions in `intent-layer` → *Where nodes live*. File count is the wrong measure — a docs-heavy repo
can hold seventeen files and a thousand lines of implementation.

| Classification | Looks like |
|---|---|
| **greenfield** | Under ~20KB of source, no manifest declaring real dependencies, **and** under ~20 commits touching source (`git rev-list --count HEAD -- <source paths>`; a repo with no commits counts as zero). A small repo with real history is brownfield — it has a past to cite. Follow `references/greenfield.md` instead of the rest of this file. |
| **brownfield-cold** | Source, no nodes anywhere. |
| **brownfield-seeded** | Source, and a root `CLAUDE.md` but nothing below it. |
| **brownfield-partial** | Some nodes already exist. Chunk and interview only what they don't cover; existing nodes are input, like a seed. |
| **resume** | Campaign state found for this repo. Report progress and offer to resume or restart. |

Then one `AskUserQuestion` confirming the classification, the scope, and the destination. **That is
the only question before the chunk map.** Write `head` and `destination` to campaign state as soon as
it is answered.

## The destination

**Settled once, before the chunk map, and never per node.** Ask it as permission, not preference:
*may you commit changes to this repo's `CLAUDE.md` files?* If not, the campaign writes
`CLAUDE.local.md` throughout — read `intent-layer` → *When the node isn't yours*
(`../intent-layer/references/local-nodes.md` from this skill's base directory) for what a local node
is and how to write one. Three
things change about the **campaign**:

| | In local mode |
|---|---|
| **Gate on the ignore first** | Before writing anything, `git check-ignore -q CLAUDE.local.md` and again for a nested path such as `x/CLAUDE.local.md` — an anchored `/CLAUDE.local.md` pattern passes the first and leaves every nested node committable. If either isn't ignored, stop and offer `.git/info/exclude` — the default, because it doesn't modify a tracked file — or `.gitignore` if the convention is worth announcing. An unignored local node gets committed, which is precisely what you lack permission to do. |
| **Committed nodes are input, never edited** | Classify their claims the way you'd classify a seed, and use the result to decide what the local layer must *not* repeat. Seed (step 2) does not run: the root is not yours to rewrite. |
| **Disagreements park as overrides** | A contradiction the SME states is not a correction you can make. Park it in `overrides`; close-out hands it back. |

Write to the settled variant throughout, never a mix.

## Chunking

Gather the signals from the `intent-layer` skill's *Where nodes live*, fanning out one read-only
`Explore` agent per candidate directory. Run the git commands yourself —
`references/chunking-signals.md` has them, the coupling arithmetic, and its traps — and give each agent
its directory and the path to `../intent-layer/SKILL.md` for the cohesion and tests signals, since
`Explore` agents don't load skills. No single signal decides a boundary — coupling above ~40% proposes
a merge and says which other signals agree.

**Tier** is path depth, and capture runs deepest-first. **Within a tier**, order ascending by
co-change partners times distinct authors. Small, cohesive, single-owner, well-tested chunks go
first; the hub every subtree imports goes last, by which time the nodes around it already say what it
has to satisfy. Many authors is not a disqualification — it is a later slot.

Present the map as a table — boundary, paths, size, tier, order, why — and **stop for approval.** This
is the highest-leverage checkpoint in the campaign: a bad map wastes the SME's attention and cannot be
fixed later without re-interviewing. Write `chunks` to state on approval.

## The campaign

Chunking is step 1. The rest:

**2 — Seed.** *Committed mode only.* If a root node exists, treat it as draft input regardless of what
wrote it. Classify every claim as derivable, non-derivable, or unverifiable, and park each survivor
against the chunk it belongs to. Say plainly that the root node will be **rewritten, not appended
to**, and show the diff before writing it in step 3's final tier.

**3 — Tier by tier, deepest first.** For each tier:

1. **Pre-read.** Fan out one agent per chunk in the tier, each given the chunk's paths, the parked
   facts that touch it, the open questions as of dispatch, and the path to this file's *The
   interview* evidence table; each returns what it sees and candidate questions with their citations.
   You never load a whole chunk yourself; that is what keeps the campaign inside one context. A chunk
   with child nodes is pre-read per *Rolling up*.
2. **Interview, one chunk at a time** — there is one human. Re-read state immediately before asking
   and discard questions the intervening chunks already answered; a high discard rate means the tier
   ordering was wrong. Then state what you see, ask, draft, one revision round, and write **or skip**.
3. **Close the tier.** Land every parked fact whose least common ancestor is a chunk in this tier —
   by now every chunk it touches is closed (*Rolling up*). No chunk in the next tier up starts until
   this is done.

**4 — Compress.** Sweep the paths just written with the `auditing-intent-layer` skill — unmodified, so
capture can't drift a friendlier bar. A campaign of more than a few chunks that skipped none is the
likeliest to need it. Show the verdicts, apply the ones the SME approves, then (committed mode) offer
the commit.

**5 — Close.** Report in one block: chunks, merges proposed while chunking, nodes written, total
lines, **chunks skipped and why** — a merge is not a skip; skipping is an interview outcome — open
questions, tasks, overrides, and which variant was written. Then replay the commit hook over recent
history, from the plugin's `hooks/intent_layer_check.py` (two directories above this skill's base
directory):

```
python3 <plugin>/hooks/intent_layer_check.py --replay 30
```

`rate` is how often the hook will now speak, using the hook's own nearest-node rule, across the whole
repo even when the campaign was scoped to a path — read `nodes` for the scoped ones. Under about 1 in
3 is healthy; above it, merge nodes upward before landing. For a local layer the output says
`local_upper_bound` — a local node is struck by the clock, which history can't show — and the
threshold still applies. Close out campaign state per `references/campaign-state.md`.

## The interview

**Budget the campaign, not the chunk.** At most four questions per chunk, one turn, around five
minutes of attention. An SME asked eight questions about chunk 1 does not show up for chunk 7, and a
half-finished campaign is the failure mode that actually happens. Rank a chunk's questions and park the
rest in `open_questions`; split only a chunk over the size ceiling in `intent-layer` → *Where nodes
live*.

**Open with what you believe, not with what you want.** Three to five bullets first: what this area
owns, what it doesn't, the contract you think holds, the one thing that looks wrong. An SME corrects a
wrong sentence in five seconds and answers an open question in five minutes — and the correction is
the more valuable artifact, because it names an assumption the code did not prevent. That is the
definition of a trap.

**Shape: one `AskUserQuestion` call, up to four questions.**

- **Up to three options-questions**, wherever you have a hypothesis. Each has at most three candidate
  answers plus **"I don't know"** — the tool allows four options and adds "Other" itself.
- **One prose question, last:** *what do people get wrong here?* Give it options like "Nothing comes to
  mind" and "Someone else would know"; the real answer arrives typed in "Other". It has no answer set,
  and it is where the highest-value content comes from.

**When an option rests on a doc, recommend it only when the code and that doc agree** — list it first
with "(Recommended)" in its label. A doc claim that waits on something the code cannot show — a
migration, a vendor, a date — never agrees: the code standing still proves only that nobody touched
it. When a doc and the code disagree, recommend nothing — the SME's pick is the finding.

**Earn every question from evidence.** You may only ask about something you can point at. A doc
citation carries its date: `path (changed YYYY-MM-DD, N chunk commits since)`, from
`git log -1 --format='%h %cs' -- <doc>` and
`git log --oneline <sha>..HEAD -- <each chunk path> <exclusions> | wc -l` — code only, so the full
exclusion set from *Where nodes live* including markdown, counted from the doc's own commit, across
every path the chunk spans.

| You can point at | Ask | Because you cannot derive |
|---|---|---|
| Two live implementations of the same thing | "Which do I write next, and what happens to the other?" | Which pattern is sanctioned mid-migration. |
| A swallowed exception, a retry with no backoff, a `# don't` comment | "What went wrong that put this here?" | The incident the guard encodes. |
| A module every other module imports | "What is allowed to bypass this?" | Whether it is a hub by design or by accretion. |
| A flag with no reader, a directory with no tests, code nothing calls | "Is this live?" | Dead versus dormant-on-purpose. |
| A boundary crossed in both directions | "Which direction is legal?" | The intended direction of dependency. |
| **Nothing in particular** | **Don't ask.** | A question you could have asked before reading the code will be answered with something generic, and the generic answer will become a line. |

A chunk that yields no citable question yields no interview. Mark it skipped and move on.

**"I don't know" is free, and both outcomes are useful:**

- **Nobody knows.** That is itself non-derivable, and earns a conservative rule — *"Nobody currently
  knows whether charge replay is idempotent. Treat it as unsafe: never retry a charge without a fresh
  idempotency key."* That is a trap, and traps are what the layer is for.
- **Someone else knows** (named in "Other"). Park it in `open_questions` with their name and keep
  going. One unanswered question never blocks a chunk.

**Grep-verify any answer that names a file, symbol, signature, or flag** before it lands. A
contradiction gets surfaced to the SME, not written down — and it is usually the most interesting
thing the chunk produces.

**Close with the draft, not the transcript.** Show the drafted node and ask once whether anything is
wrong. One revision round, then move on.

## Rolling up

A chunk whose directory has child nodes is drafted from **those nodes and its own direct files, never
child source.** An agent that reads code re-derives, and re-derived content is precisely what the
compression pass deletes.

A parent earns lines from exactly three sources beyond its own direct files:

1. Facts true in two or more children, hoisted out of them.
2. Facts about the *relationships* between children — call direction, dependency order, "webhooks
   never call payments directly; they enqueue".
3. Downlinks. Cheap, and most of a parent's value.

**If nothing produces content, the parent gets no node.** Holes in the hierarchy are expected and
correct; otherwise every intermediate directory acquires a node that is an `ls` of its children.

**Park by what the fact is true of.** A fact *owned* by one chunk that others depend on — B's
contract, stated while interviewing A — is parked against B; it lands in B's node, and A's node links
to it. A fact *true of* several paths is parked with those paths, and goes to their least common
ancestor: the longest common directory prefix. Until the LCA's tier, it rides into that parent's
pre-read as input. At the LCA's tier close it lands in the LCA's node if the LCA got one, otherwise in
the nearest ancestor that does, and is **removed** from the descendants — both per `intent-layer` →
*What goes in a node*, "Never duplicate across nodes". When that node would be the repo root, work down `intent-layer` → *Where a rule belongs*
first: the root always loads, so it is the most expensive destination in the repo.

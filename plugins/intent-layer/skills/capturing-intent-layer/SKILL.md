---
name: capturing-intent-layer
description: Establishing an intent layer on a repo that has none — surveying and classifying the repo, chunking it at semantic boundaries, interviewing the subject-matter expert leaf-first, and rolling children's nodes up into parents without re-reading their code. Runs as a resumable campaign across sessions. Use when a repo has no CLAUDE.md hierarchy, when a single root CLAUDE.md should be several nodes, or when laying down nodes for a project before its code exists. Triggers on "set up the intent layer", "bootstrap CLAUDE.md", "capture the intent layer", "we have no CLAUDE.md files", "split the root CLAUDE.md", "interview me about this codebase".
---

# Capture an intent layer

Everything else in this plugin maintains a layer someone already built. This is how one gets built:
read the code, then ask the person who knows what the code doesn't say.

**Capture does not get its own bar.** It gets a procedure. What earns a line, how hard to compress,
and where a node belongs stay with the `intent-layer` skill, unchanged. That separation is the whole
design: capture is the only additive operation in the plugin, and an additive operation holding a
friendlier bar is exactly how a repo acquires twenty nodes of `ls` output that `/audit-intent-layer`
then spends a month deleting.

> **Chunking decides where you look. The interview decides where you write.** A chunk that produced
> nothing a model can't re-derive produces no node, and a campaign that skipped zero chunks did not
> hold the bar.

## Phase 0 — Survey

Read-only, no questions yet.

```
git ls-files | wc -l
git ls-files -- '*CLAUDE.md'
git ls-files | grep -E '(package\.json|pyproject\.toml|go\.mod|Cargo\.toml|Gemfile|\.csproj)$'
git rev-parse HEAD
```

Measure **source bytes**, excluding markdown, config, lockfiles, `vendor/`, `node_modules/`,
generated code, fixtures, and snapshots. File count is the wrong measure — a docs-heavy repo can hold
seventeen files and a thousand lines of implementation.

| Classification | Looks like |
|---|---|
| **greenfield** | Under ~20KB of source and no manifest declaring real dependencies. There is nothing to derive from yet. |
| **brownfield-cold** | Source, no nodes anywhere. |
| **brownfield-seeded** | Source, and a root `CLAUDE.md` but nothing below it. |
| **brownfield-partial** | Some nodes already exist. Capture only what they don't cover. |
| **resume** | Campaign state found for this repo. Report progress and offer to resume or restart. |

If a path was named, restrict the campaign to it. Then one `AskUserQuestion` confirming the
classification, the scope, and the destination. **That is the only question before the chunk map** —
the destination rides in the same call, never a second turn.

## The destination

**Settled once, before the chunk map, and never per node.** Either you may commit to this repo's
`CLAUDE.md` files or you may not; if you may not, the campaign writes `CLAUDE.local.md` throughout.
Ask it as permission, not preference: *may you commit changes to this repo's `CLAUDE.md` files?*
Record the answer in campaign state so a resume doesn't re-ask. Permission is a property of the repo
and not of the fact, which is why one answer covers every chunk.

What a local node *is* — load order, why it supplements rather than replaces, and the rules for
writing one — belongs to the `intent-layer` skill's *When the node isn't yours*, including why the
bar is identical either way. Read it there. Three things change about the **campaign**:

| | In local mode |
|---|---|
| **Gate on the ignore first** | Before writing anything, `git check-ignore -q CLAUDE.local.md`. If it isn't ignored, stop and offer `.git/info/exclude` — the default, because it doesn't modify a tracked file, which is the whole reason you're in this mode — or `.gitignore` if the convention is worth announcing. An unignored local node gets committed, which is precisely what you lack permission to do. |
| **Committed nodes become input** | Classify their claims the way you'd classify a seed node, but use the result to decide what the local layer must *not* repeat. Pre-read a chunk's committed node the way you pre-read its code: it is input, and it decides what the local layer has left to say. |
| **Disagreements park as overrides** | A contradiction the SME states is not a correction you can make, since that file isn't yours to edit. Park it as a candidate override. And don't offer `/init` — it writes a committed root node. |

Write to the variant Phase 0 settled, throughout, never a mix.

## Chunking

Build the chunk map using the placement signals in the `intent-layer` skill's *Where nodes live*.
Present it as a table — boundary, size, tier, order, why — and **stop for approval.** This is the
highest-leverage checkpoint in the campaign: a bad map wastes the SME's attention and cannot be fixed
later without re-interviewing. Fan out one read-only agent per candidate directory to gather the
signals; that part is embarrassingly parallel. Write state only once the map is approved.

**Coupling, by inclusion-exclusion**, for adjacent sibling pairs among the surviving candidates only.
Three `git log --oneline --since=18.months -- <paths> | wc -l` calls — one for `A`, one for `B`, one
for `A B` — give co-changes as `|A| + |B| - |A∪B|`. Take the ratio against the smaller of the two;
above roughly 40%, merge them into one chunk. It needs no `awk` and it behaves the same on every git
version.

**Ignore that ratio when the smaller side has fewer than about ten commits.** One shared commit out
of two is 50% and means nothing — a young or rarely-touched directory has no co-change signal at all,
and reading one out of it will merge boundaries that have nothing to do with each other. Fall back to
the other four signals.

**Tier** is path depth, and capture runs deepest-first. **Within a tier**, order ascending by
co-change partners times distinct authors (`git shortlog -sn --since=18.months -- <dir>`). Small,
cohesive, single-owner, well-tested chunks go first; the hub every subtree imports goes last, by
which time the nodes around it already say what it has to satisfy. Many authors is not a
disqualification — it is a later slot.

## The campaign

Chunking is step 1. The rest:

**2 — Seed.** If a root node exists, treat it as draft input regardless of what wrote it — `/init`, a
human, another tool. Classify every claim in it as derivable, non-derivable, or unverifiable, and park
each survivor against the chunk it belongs to. Say plainly that the root node will be **rewritten, not
appended to**, and show the diff before writing. If no root node exists, offer to run `/init` first.

**3 — Capture, leaf-first.** Per chunk, in the approved order: pre-read, state what you see, ask,
draft, one revision round, then write **or skip**. Fan out the pre-reads one agent per chunk across
the upcoming tier, each returning what it sees plus candidate questions with their citations. That
fan-out is a context-budget mechanism as much as a speed one — it is why you never load a whole chunk
yourself.

Interviews serialize; there is one human. Give the pre-read agents the parked facts and open questions
as of dispatch, then re-read state immediately before asking and discard any question the intervening
chunks already answered. Count the discards: a high rate means the tier ordering was wrong.

**4 — Roll up.** Tier by tier upward, parents from children's nodes only. Resolve parked facts to
their least common ancestor at each tier close. Tier boundaries are real barriers — no roll-up starts
until the tier below it is closed.

**5 — Compress.** Sweep the paths just written with the `auditing-intent-layer` skill, **before** the
commit. It sweeps both variants, so a local layer is covered without being told which mode produced
it. Reusing the audit unmodified is deliberate: it is the same bar in its ongoing form, and routing
capture through it means capture cannot quietly drift a friendlier one.

**6 — Close.** Report in one block: chunks, nodes written, total lines, **chunks skipped and why**,
open questions parked, tasks recorded, and which variant was written. Then sample the last 30 commits
and count how many touched a directory that now has a node without touching that node — that is the
rate at which the commit hook will now speak. Under about 1 in 3 is healthy. Above it, merge nodes
upward before landing.

For a local layer that count is an **upper bound**, not the rate: a local node is struck by your
having updated it rather than by the commit, which the history can't show. Report it as the bound it
is. The threshold still applies — an over-noded layer is over-noded either way.

## The interview

**Budget the campaign, not the chunk.** At most four questions per chunk, asked in one turn, around
five minutes of attention. An SME asked eight questions about chunk 1 does not show up for chunk 7,
and a half-finished campaign is the failure mode that actually happens. A chunk that seems to need
more was under-chunked — split it and re-tier rather than spending the next chunk's budget here.

**Open with what you believe, not with what you want.** Three to five bullets first: what this area
owns, what it doesn't, the contract you think holds, the one thing that looks wrong. Then the
questions.

An SME corrects a wrong sentence in five seconds and answers an open question in five minutes — and
the correction is the more valuable artifact, because it names an assumption a model made that the
code did not prevent. That is the definition of a trap.

**Shape: at most three `AskUserQuestion` options-questions plus one open prose question, in a single
turn.** Use multiple choice wherever you have a hypothesis and two to four candidate answers, which
is most of them once you have read the chunk — it turns typing into clicking, and typing is what
ends campaigns. Reserve prose for exactly one question: *what do people get wrong here?* It has no
answer set, and it is where the highest-value content comes from.

**Earn every question from evidence.** You may only ask about something you can point at.

| You can point at | Ask | Because you cannot derive |
|---|---|---|
| Two live implementations of the same thing | "Which do I write next, and what happens to the other?" | Which pattern is sanctioned mid-migration. The code shows both and says nothing. |
| A swallowed exception, a retry with no backoff, a `# don't` comment | "What went wrong that put this here?" | The incident the guard encodes. |
| A module every other module imports | "What is allowed to bypass this?" | Whether it is a hub by design or by accretion. |
| A flag with no reader, a directory with no tests, code nothing calls | "Is this live?" | Dead versus dormant-on-purpose. |
| A boundary crossed in both directions | "Which direction is legal?" | The intended direction of dependency. |
| **Nothing in particular** | **Don't ask.** | A question you could have asked before reading the code is a question you haven't earned. It will be answered with something generic, and the generic answer will become a line. |

A chunk that yields no citable question yields no interview. Mark it skipped and move on.

**"I don't know" must be free.** Every options-question carries a cheap way to say it, and both
outcomes are useful:

- **Nobody knows.** That is itself non-derivable, and it earns a conservative rule — *"Nobody
  currently knows whether charge replay is idempotent. Treat it as unsafe: never retry a charge
  without a fresh idempotency key."* That is a trap, and traps are what the layer is for.
- **Someone else knows.** Park it in `open_questions` with their name and keep going. One unanswered
  question never blocks a chunk.

**Grep-verify any answer that names a file, symbol, signature, or flag** before it lands. Memory
drifts from the code faster than the code drifts from itself. A contradiction gets surfaced to the
SME, not written down — and it is usually the most interesting thing the chunk produces.

**Close with the draft, not the transcript.** Show the drafted node — it is short by construction —
and ask once whether anything is wrong. One revision round, then move on.

## Rolling up

Parents are captured after their children, from the children's nodes.

**The parent-drafting agent reads its children's node text and the parent's own direct files. It does
not read child source.** An agent that reads code re-derives, and re-derived content is precisely
what the compression pass deletes. An agent that reads children's nodes produces the two things a
parent is actually for.

A parent earns lines from exactly three sources:

1. Facts true in two or more children, hoisted out of them.
2. Facts about the *relationships* between children — call direction, dependency order, "webhooks
   never call payments directly; they enqueue".
3. Downlinks. Cheap, and most of a parent's value.

**If none of the three produce content, the parent gets no node.** Holes in the hierarchy are
expected and correct. Without this rule every intermediate directory acquires a node whose content
is a list of its children, which is an `ls`.

### Deduplicating to the least common ancestor

Any fact the SME states that mentions a path outside the current chunk gets parked with the list of
paths it applies to. At each tier close, for each parked fact: the LCA is the longest common
directory prefix of those paths. If that directory has or earns a node, the fact lands there and is
**removed** from the descendants — not replaced with a pointer.

**Hoisting to the LCA needs no back-link.** An ancestor node already loads whenever a descendant
does. A child that says "see the parent for the HTTP rule" spends a line telling the reader about
context they are already holding. Cross-links are for *sideways* references only — between subtrees,
where the LCA is the root.

**When the LCA is the repo root**, route the fact through the `intent-layer` skill's *Where a rule
belongs* before adding to the root node. The root always loads, which makes it the most expensive real
estate in the repo, and three of that table's five destinations are cheaper. It carries one row it
doesn't, because only a roll-up produces the situation:

| If the fact | Goes to | Because |
|---|---|---|
| Genuinely holds everywhere | Root node | That is what a root node is for, and a fact hoisted this far has earned it. |

## Before the code exists

The **greenfield** branch of Phase 0. A node written ahead of its code is the one case where nothing is derivable, so almost everything the
SME says qualifies. That is also what makes it dangerous: there is no source to check it against.

**Write commitments, not descriptions.**

| Dangles | Holds |
|---|---|
| "This directory will own payment retries" | "Everything touching Stripe goes through here — a `stripe` import anywhere else is a bug" |

A description of the future must be re-verified the day the code arrives, and nobody will. A
commitment is falsified by the code rather than by the node — so when the two diverge, the node is
right and the code is wrong. Present tense, always: state what is *allowed*, never what *will exist*.

**A boundary the SME cannot state a rule for does not get a directory.** If the only thing true about
it is its name, there is nothing to write down and the directory is a guess that someone will have to
delete.

### The four steps

**Do not run `/init`.** There is nothing to initialize from, and a generated root node would look
authoritative while saying nothing the SME chose.

**G1 — Elicit.** No code, so no evidence-earned questions — the citation table under *The interview*
is unavailable to you here. Ask what is being built, which boundaries are already intended, and, per
boundary, the one rule that must hold there.

**G2 — Scaffold.** Create the intended directories and one node each, commitments only, present
tense, in the variant Phase 0 settled. A boundary with no stated rule gets no directory.

**G3 — Root.** Write the root node from intent alone: what this project is, the boundaries and their
rules, downlinks to each.

**G4 — Hand off.** Say explicitly that `/init` should be run later, once there is code and tooling to
describe; it will find these nodes and layer under them.

## Campaign state

A campaign spans sessions, so four things live in
`~/.claude/intent-layer/capture/<repo-slug>.json` — slug built the way `intent_layer_check.py` builds
its project slug, from the absolute path with `/` and `.` replaced by `-`:

1. **The destination**, committed or local. Every other consumer reads it off disk; capture is the
   only one that can't, because it writes files that don't exist yet.
2. **The approved chunk map and its order.** Recomputing it is non-deterministic, and a different
   chunking mid-campaign silently produces overlapping nodes.
3. **Chunks deliberately skipped, with the reason.** Without this, resume re-interviews the chunks
   that correctly earned nothing — forever, punishing the exact behaviour the design wants.
4. **Parked facts, open questions, and tasks**, which by definition are in no node yet.

Plus the HEAD the campaign started from, so `git diff --name-only <sha>..HEAD` on resume decides
which boundaries moved enough to need re-chunking.

Kept under `~/.claude` rather than in the repo, following the harvest hook — and for a reason the
harvest rationale doesn't cover. **State is scaffolding, not product.** A file in the repo listing
open questions about payments is a second, unmaintained intent layer, and it rots exactly the way the
doctrine says nodes rot. Anything durable in it belongs in a node.

Keyed by repo rather than by session, deliberately unlike harvest: *harvest state expires by design
so a finished session stops nagging; campaign state persists by design so a campaign survives session
death.*

**Close-out empties the file.** Every remaining open question is either routed into a node as a
conservative rule or handed back to the SME as a task. State that outlives the campaign is state
nobody will ever read again.

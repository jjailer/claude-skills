---
description: Establish an intent layer on a repo that has none, by interviewing the subject-matter expert
allowed-tools: Bash(git ls-files:*), Bash(git log:*), Bash(git shortlog:*), Bash(git diff:*), Bash(git rev-parse:*), Bash(git check-ignore:*), Bash(wc:*), Read, Grep, Glob, Task, AskUserQuestion, Write, Edit
---

Build this repo's intent layer by interview. $USER is the subject-matter expert; you are the one who
reads the code and drafts.

Use the `capture-intent-layer` skill for the interview, the roll-up, and the state schema. Use the
`intent-layer` skill for where nodes belong and what earns a line — capture does not get its own bar.

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

Then one `AskUserQuestion` confirming the classification, the scope, and **where the layer is
written**. If `$ARGUMENTS` names a path, restrict the campaign to it. This is the only question before
the chunk map — the destination rides in the same call, never a second turn.

Ask the destination as permission, not preference: *may you commit changes to this repo's `CLAUDE.md`
files?*

| Answer | The campaign writes | And |
|---|---|---|
| **Yes** | `CLAUDE.md` | Everything below is unchanged. |
| **No** | `CLAUDE.local.md` | Committed nodes become read-only input; the local layer supplements them. |

Record the answer in campaign state so a resume doesn't re-ask.

**In local mode, gate on the ignore before writing anything.** `git check-ignore -q CLAUDE.local.md`.
If it isn't ignored, stop and offer `.git/info/exclude` — the default, because it doesn't modify a
tracked file, which is the whole reason you're in this mode — or `.gitignore` if the convention is
worth announcing. An unignored local node gets committed, which is precisely what you lack permission
to do.

## Brownfield

**1 — Chunk.** Build the chunk map using the placement signals in the `intent-layer` skill. Present it
as a table — boundary, size, tier, order, why — and **stop for approval.** This is the highest-leverage
checkpoint in the command: a bad map wastes the SME's attention and cannot be fixed later without
re-interviewing. Fan out one read-only agent per candidate directory to gather the signals; that part
is embarrassingly parallel. Write state only once the map is approved.

Compute the coupling signal by inclusion-exclusion, for adjacent sibling pairs among the surviving
candidates only. Three `git log --oneline --since=18.months -- <paths> | wc -l` calls — one for `A`,
one for `B`, one for `A B` — give co-changes as `|A| + |B| - |A∪B|`. Take the ratio against the
smaller of the two; above roughly 40%, merge them into one chunk. It needs no `awk` and it behaves
the same on every git version.

**Ignore that ratio when the smaller side has fewer than about ten commits.** One shared commit out
of two is 50% and means nothing — a young or rarely-touched directory has no co-change signal at all,
and reading one out of it will merge boundaries that have nothing to do with each other. Fall back to
the other four signals.

**Tier** is path depth, and capture runs deepest-first. **Within a tier**, order ascending by
co-change partners times distinct authors (`git shortlog -sn --since=18.months -- <dir>`). Small,
cohesive, single-owner, well-tested chunks go first; the hub every subtree imports goes last, by
which time the nodes around it already say what it has to satisfy. Many authors is not a
disqualification — it is a later slot.

**2 — Seed.** If a root node exists, treat it as draft input regardless of what wrote it — `/init`, a
human, another tool. Classify every claim in it as derivable, non-derivable, or unverifiable, and park
each survivor against the chunk it belongs to. Say plainly that the root node will be **rewritten, not
appended to**, and show the diff before writing. If no root node exists, offer to run `/init` first.

**In local mode this inverts.** Committed nodes are read-only: classify their claims the same way, but
use the result to decide what the local layer must *not* repeat, and park disagreements as candidate
overrides rather than edits. Don't offer `/init` — it writes a committed root node.

**3 — Capture, leaf-first.** Per chunk, in the approved order: pre-read, state what you see, ask, draft,
one revision round, then write **or skip** — to the variant Phase 0 settled, never a mix. Fan out the pre-reads one agent per chunk across the
upcoming tier, each returning what it sees plus candidate questions with their citations. That fan-out
is a context-budget mechanism as much as a speed one — it is why you never load a whole chunk yourself.

Interviews serialize; there is one human. Give the pre-read agents the parked facts and open questions
as of dispatch, then re-read state immediately before asking and discard any question the intervening
chunks already answered. Count the discards: a high rate means the tier ordering was wrong.

**4 — Roll up.** Tier by tier upward, parents from children's nodes only. Resolve parked facts to their
least common ancestor at each tier close. Tier boundaries are real barriers — no roll-up starts until
the tier below it is closed.

**5 — Compress.** Run `/audit-intent-layer` over the paths just written, **before** the commit. It
sweeps both variants, so a local layer is covered without being told which mode produced it. Reusing
the audit unmodified is deliberate: it is the same bar in its ongoing form, and routing capture through
it means capture cannot quietly drift a friendlier one.

**6 — Close.** Report in one block: chunks, nodes written, total lines, **chunks skipped and why**, open
questions parked, tasks recorded, and which variant was written. Then sample the last 30 commits and
count how many touched a directory that now has a node without touching that node — that is the rate
at which the commit hook will now speak. Under about 1 in 3 is healthy. Above it, merge nodes upward
before landing.

For a local layer that count is an **upper bound**, not the rate: a local node is struck by your
having updated it rather than by the commit, which the history can't show. Report it as the bound it
is. The threshold still applies — an over-noded layer is over-noded either way.

## Greenfield

Do not run `/init`. There is nothing to initialize from, and a generated root node would look
authoritative while saying nothing the SME chose.

**G1 — Elicit.** No code, so no evidence-earned questions. Ask what is being built, which boundaries are
already intended, and — per boundary — the one rule that must hold there.

**G2 — Scaffold.** Create the intended directories and one node each, commitments only, present tense,
in the variant Phase 0 settled. A boundary with no stated rule gets no directory.

**G3 — Root.** Write the root node from intent alone: what this project is, the boundaries and their
rules, downlinks to each.

**G4 — Hand off.** Say explicitly that `/init` should be run later, once there is code and tooling to
describe; it will find these nodes and layer under them.

$ARGUMENTS

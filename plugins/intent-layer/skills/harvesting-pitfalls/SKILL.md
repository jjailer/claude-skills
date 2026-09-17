---
name: harvesting-pitfalls
description: Turning friction from the current session into a durable rule, or correctly throwing it away — what counts as a pitfall, and whether it belongs in a CLAUDE.md node, a path-scoped rule, a skill, a hook, or nowhere. Use at the end-of-feature pause before committing, when the commit hook reports signals of a recurring pitfall, or when a session went badly and you want the lesson to survive it. Triggers on "harvest pitfalls", "what went wrong this session", "capture this as a rule", "make sure this doesn't happen again", "add this to CLAUDE.md so you remember".
argument-hint: "[what to focus on]"
---

# Harvest pitfalls

A session that hit real friction knows something the repo doesn't. This is how that becomes a rule —
or gets discarded, which is the more common correct answer.

You lived the session, so you have the one thing a transcript reader never recovers: **what you
assumed, and when you found out it was wrong.** That gap is the pitfall; the error message is just
where it surfaced. So work from what you lived — **don't re-read the transcript from disk.** If
`$ARGUMENTS` names a focus, harvest that.

## The bar

A pitfall is a **wrong assumption that will recur**. Not everything that cost time qualifies. Walk the
session against the *Qualifies* column.

| Qualifies | Doesn't |
|---|---|
| You assumed a contract that wasn't true, and nothing in the source said otherwise | You misread code that was perfectly clear |
| The same fix failed twice because the real cause was somewhere you didn't look | A test went red once and the next edit fixed it — that's red-green working |
| A convention exists, is enforced socially, and is invisible in the code | You needed a fact you could have grepped in ten seconds |
| The correction had to be given twice before it stuck | You were corrected once and adjusted |
| A tool or command fails in a way specific to this repo's layout | A typo, a wrong path, an ordinary slip |

**Iteration is not a pitfall.** Most sessions produce nothing durable, and saying so in one line is a
complete and correct answer. A harvest that always finds something is manufacturing findings to
justify itself, and every fabricated rule costs context forever while protecting against nothing.

## Route it

Name the assumption in one sentence — *what you assumed, what was actually true* — then place it.

**First, the pre-filters: is it a rule about the code at all?** Two kinds of session residue aren't.
Screen them out before the table, not after — its last row catches nearly any non-derivable trap, so
a dated incident checked there lands in a node.

| If | Destination | Because |
|---|---|---|
| It's a repeated permission prompt | **`settings.json` allowlist** | Not an intent-layer problem at all. |
| It's in-flight, dated, or a volatile ID | **Memory, or nowhere** | `intent-layer` → *Memory vs. intent layer* |

**Then work down `intent-layer` → *Where a rule belongs*.** That table is the one home for this
decision; the first row that fits wins.

## Writing the escalation hook

Routing sends most things to *drop* or *one line in a node*. The hook row is the one that needs real
work, so it's worth knowing the shape before you decide it's too expensive.

A rule reaches that row because it must hold and a node is advisory — so the hook **denies**. A
`PreToolUse` hook reads a JSON event on stdin; to block, it prints `{"hookSpecificOutput":
{"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}`.

If advising would be enough, it probably isn't a hook — recheck the node row. An advisory hook earns
its place only when the reminder matters at one specific command. It prints `{"hookSpecificOutput":
{"hookEventName": "PreToolUse", "additionalContext": "..."}}`, and the tool still runs, so the model
reads it after the fact. `hooks/intent_layer_check.py` in this plugin is that case, and the worked
example of the shape.

Two rules that decide whether the hook survives contact:

- **Exit 0 on every path**, including malformed input. A hook that errors is a hook that gets removed.
- **Match narrowly** — on the specific command, not on `Bash`. A gate that fires on legitimate work
  gets disabled within a week, taking the real protection with it.

## Landing it

State each capture before writing it: the destination, the line, and which route sent it there. The
user sees every capture before it is written.

| Triggered by | Land it |
|---|---|
| **The commit hook** | The hook speaks before the commit runs, and the commit can still fail — a pre-commit hook, nothing staged. Confirm with `git log -1` that HEAD is the commit just made, then `git commit --amend --no-edit`. If it isn't, treat it as a manual invocation. |
| **A manual invocation** | There may be no pending commit, and HEAD may be pushed or unrelated. Stage alongside pending work if there is any; otherwise propose a standalone commit. Never amend unless HEAD is an unpushed commit this session made. |

Then say plainly what you captured and what you discarded. "Two signals, both ordinary iteration,
nothing captured" is a good outcome and should be reported as one, not padded.

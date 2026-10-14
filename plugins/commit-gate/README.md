# commit-gate

Refuses `git commit` until your latest prompt approves one.

A review pause written as prose ("present the diff, then wait for a go") holds until the one time it
doesn't. Then a commit lands that you never looked at. This gate makes the pause mechanical: the
agent can do all the work it likes, but a commit needs words from you since your last prompt.

## What counts as approval

Your most recent prompt decides. Every new prompt replaces the verdict, so a "go" never outlives
the conversation it answered.

| Approves | Doesn't |
|---|---|
| A bare answer: `go`, `go ahead`, `yes`, `ok`, `lgtm`, `ship it`, `approved`, `proceed` | A yes or go that approves other work: `yes, implement the plan`, `go ahead and implement it` |
| `commit` as a request: `Go, commit it`, `commit both, then plan the rename`, `fix the typo and commit`, `can you commit this?`, `let's commit`, `don't forget to commit` | `commit` as a noun: `look at the last commit`, `reword the commit message`, `why did you commit that?` |
| Several go-words as the whole answer: `ok go`, `yes go ahead`, `lgtm, ship it` | A negation: `don't commit yet`, `hold off on the commit`, `without committing` |
| Typing `/commit`, `/commit-commands:commit` or `/commit-commands:commit-push-pr` | Other work: `fix the padding on the title screen` |
| **When the agent has just asked about a commit:** a reply that ends in a yes: `don't dim for now, go`, `perfect. go`, `looks good to me`, `yes, please`, `👍` | Even then, a yes followed by more work (`looks good. rename it first`), a refusal before it (`not yet. looks good`), or work the commit should wait for (`rename it first. go`) |

**What your go answers.** The gate reads the agent's last message (`$.session.messages()`). It
counts as a commit question when one of its sentences both names the act ("commit", not
"committed" or "commit-gate") and asks for an answer (a "go", or a question mark): "Reply go and
I'll commit #176" is one, while "Committed 30b0487f. Shall I start on the rename?" is not. After
such a question, your reply is read clause by clause, and it approves when its **last** clause is
only a yes ("looks good", "perfect", "sure" and "👍" count here, on top of the go-words), no
earlier clause is a bare refusal ("no", "wait", "not yet"), and none holds the commit back with
"first" or "before". The yes must come last because a yes followed by more work would let the agent
do that work and commit it unseen: nothing has landed yet, so those edits don't lapse the go.

Anywhere else those extra words approve nothing, since a bare "looks good" could be answering a
plan. Only the question since your previous prompt counts: once you've replied to a commit question
with something else, it is closed. If the transcript can't be read, your prompt is judged on its
own.

Only your own words count: a prompt typed at the terminal, sent through Remote Control or a Slack
ping, or given to `claude -p`, or one a plugin submits on your behalf (`asUser`, say from a button
you press). A background task's completion notice or another session's message neither grants approval
nor takes it away, so a test suite finishing in the background doesn't cancel your "go".

**Approval covers what you reviewed.** It survives fix-ups made before the commit (a ruff format, a
typo). Once a commit has landed, though, the next edit through an edit tool (Edit, Write) is new work
you haven't seen, and the commit after it needs a fresh go. That rule exists because of a real slip:
"go, commit both, then plan the rename" was once read as covering the rename's commit too. A file
changed by a Bash command after a commit doesn't lapse approval: telling `git mv` or `sed -i` apart
from the `git add` between two approved commits is guesswork the gate doesn't attempt.

Scratch files don't lapse it either: an edit under `/tmp`, `/private/tmp` or `/var/folders` (where
Claude Code's scratchpad lives) is a commit message for `-F` or a note, not work you review, so two
commits you approved together can each take a message file. A path that climbs out with `..` isn't
scratch. A repository checked out under one of those folders gets no lapse at all, so there the gate
covers only the first commit's pause.

## What it guards

It recognises `git commit` in a Bash command line: after `cd x &&`, `;`, `&`, `|` or `(`, behind
env assignments (`GIT_AUTHOR_NAME=x git commit`) and `env`, `command`, `time`, `nohup` or `exec`,
after a shell keyword (`then`, `do`, `if`, `!`), inside `$(…)` or backticks, through
`git -C <dir>` and `git -c k=v`, and as `/usr/bin/git`. Quoted strings and heredoc bodies are data,
so `echo "a && git commit"`, `echo '$(git commit)'` and a heredoc that mentions `git commit` pass,
as do `git commit-tree` and `git log --grep commit`.

It is a backstop against slips, not a sandbox. `bash -c "git commit"`, `sh <<EOF` feeding a commit,
a script or `xargs` that commits, a git alias, `git "commit"` or `\git commit` all get through. The
gate stops the agent from forgetting the pause; it doesn't stop an agent that is set on getting
around it.

When it refuses, the agent reads one of two reasons, so it can tell you which:

```
commit-gate: nothing since the last prompt approves a commit. Present the diff and test results,
then ask for a go.
```

```
commit-gate: the go lapsed when /repo/src/app.py was edited after the last commit, so this commit
holds work the person hasn't seen. Present it, then ask for a fresh go.
```

The guard fails closed. If it throws before the commit runs, the commit is refused with
`(its guard failed)` appended to the message; if it throws after, approval is revoked, so the next
commit needs a fresh go.

## It's a mod

This plugin is a hooks module (`hooks/register.ts`) for Claude Code's function-hook API, not a
command hook. It runs inside Claude Code, has no `python3` dependency, and keeps its state
(`$.state`, this session only) in memory rather than in files. The API is early access, so a Claude
Code release can break it. `claude plugin test plugins/commit-gate` runs its suite against the
engine you have installed.

## Install

```bash
/plugin marketplace add jjailer/claude-skills
/plugin install commit-gate@jjc-claude-skills
```

## Backing out

`/plugin uninstall commit-gate@jjc-claude-skills`. Nothing is left behind: the gate keeps no files.

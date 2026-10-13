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
| Typing `/commit`, `/commit-commands:commit` or `/commit-commands:commit-push-pr` | A negation: `don't commit yet`, `hold off on the commit`, `without committing` |
| | Other work: `fix the padding on the title screen` |

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

## What it guards

It recognises `git commit` in a Bash command line: after `cd x &&`, `;`, `|` or `(`, behind env
assignments (`GIT_AUTHOR_NAME=x git commit`) and `env`, `command`, `time`, `nohup` or `exec`,
through `git -C <dir>` and `git -c k=v`, and as `/usr/bin/git`. Quoted strings and heredoc bodies
are data, so `echo "a && git commit"` and a heredoc that mentions `git commit` pass, as do
`git commit-tree` and `git log --grep commit`.

It is a backstop against slips, not a sandbox. `bash -c "git commit"`, `sh <<EOF` feeding a commit,
a script that commits, or a git alias all get through. The gate stops the agent from forgetting the
pause; it doesn't stop an agent that is set on getting around it.

When it refuses, the agent reads:

```
commit-gate: nothing since the last prompt approves a commit. Present the diff and test results,
then ask for a go.
```

The guard fails closed. If it throws, the commit is refused with `(its guard failed)` appended to
the message.

## While you're away

At the end of each main-thread turn, if nothing approves a commit and `git status` shows changes,
the status line reads `commit-gate: uncommitted changes, awaiting go`. Outside a git repo it shows
nothing.

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

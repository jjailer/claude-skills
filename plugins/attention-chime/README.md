# attention-chime

Plays a sound when Claude needs you, and stays quiet the rest of the time.

| Sound | When |
|---|---|
| **Bottle**, a bubbly bloop | A decision is waiting: a permission prompt (yours or an agent-team worker's), an MCP elicitation dialog, an agent that needs your input, a question (`AskUserQuestion`) or a plan to approve (`ExitPlanMode`) |
| **Siri's "got it"** (`jbl_confirm`) | The work you asked for is done: the turn really ended, no subagent or workflow is still out, and no one-shot wakeup is pending |
| **Purr** | The context auto-compacts |

## When it stays quiet

| Case | Why |
|---|---|
| A stop that a Stop gate blocked (`ruff-gate`, a capture gate) | The turn goes on. The sound comes at its real end. |
| A turn that a background task's notice or another session's message started | Nobody is waiting on it. Only your own request arms the "done" sound (a prompt you type, send from Slack or Remote Control, a plugin button that sends as you, or a plan you approve with a cleared context), and the sound disarms it, so you hear it once per request. |
| A stop while a subagent, a workflow or a one-shot wakeup is pending | The session resumes on its own when it reports back, and that is when the sound comes. A background shell or a recurring `/loop` doesn't hold it back: a dev server or a loop may never end. |
| The end of a `claude -p` run | Nobody is at the terminal. |
| A subagent finishing, or a subagent's question | It isn't the main task. |
| `idle_prompt`, `auth_success`, `agent_completed` notifications | The first repeats a stop that already rang, and the others need nothing from you. |
| A `/compact` you typed | You're already there. |
| A second decision sound within 5 seconds | A plan dialog raises both its tool call and a permission notification, and one sound covers both. |

## Example

You type "fix the padding and run the tests". Claude edits a file, and its Stop is blocked once by
`ruff-gate`, which is silent. It fixes the lint, dispatches a test subagent and stops to wait, also
silent. The subagent returns, Claude reports, and the turn ends: one "got it". A minute later a
background security review finishes and Claude summarises it. That's silent, because you didn't ask
for that turn.

## Changing the sounds

The sounds are constants at the top of `hooks/register.ts`. Any file `afplay` can play works. To
audition the built-in ones:

```bash
afplay /System/Library/Sounds/Pop.aiff
ls /System/Library/Sounds /System/Library/Components/CoreAudio.component/Contents/SharedSupport/SystemSounds/*
```

A sound that fails to play falls back to `Glass.aiff`. Off macOS (no `afplay`, say over ssh), it
writes a terminal bell to `/dev/tty`, which rings the emulator you're sitting at.

## It's a mod

A hooks module (`hooks/register.ts`) for Claude Code's function-hook API. It hooks `prompt.submit`,
`tool.call` and the classic `Notification`, `Stop` and `PreCompact` events. It sits above your
settings and plugin hooks in the chain, which is what lets it see a Stop gate's block. The API is
early access, so a Claude Code release can break it. `claude plugin test plugins/attention-chime`
runs its suite against the engine you have installed.

## Install

```bash
/plugin marketplace add jjailer/claude-skills
/plugin install attention-chime@jjc-claude-skills
```

If you already play sounds from a classic hook (a `Stop` or `Notification` command in
`settings.json`), remove it, or you'll hear both.

## Backing out

`/plugin uninstall attention-chime@jjc-claude-skills`. It keeps no files.

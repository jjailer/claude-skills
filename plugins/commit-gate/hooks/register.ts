import { atom, read, update } from 'claude-code'
import type { PromptOrigin, Register } from 'claude-code'

import type { CommitApproval } from '../types'

const approval = atom({ plugin: 'commit-gate', key: 'approval' } as const, {
  isApproved: false,
  hasCommitted: false,
} as CommitApproval)

const DENY =
  'commit-gate: nothing since the last prompt approves a commit. Present the diff and test results, ' +
  'then ask for a go. (A string-match backstop: it reads `git … commit` in the command line.)'

// Only words the person typed (or pressed, via a plugin submitting asUser) grant or revoke
// approval. A task notification or a peer's message is not the person: it leaves it as it was.
function isPersonsOwn(origin: PromptOrigin): boolean {
  switch (origin.kind) {
    case 'composer':
    case 'bridge':
    case 'sdk':
    case 'slack-ping':
      return true
    case 'plugin':
      return origin.asUser === true
    default:
      return false
  }
}

const NEGATED = /\b(don'?t|do not|not yet|no|never|without|hold off(?: on)?|skip)\b(?:\s+\w+){0,2}\s+commit/
// A yes or go approves only as the whole answer: "yes, implement the plan" approves the plan, not a commit.
const BARE_GO = /^(go|go ahead|yes|y|yep|yeah|ok|okay|lgtm|ship it|approved|proceed|do it)[\s.,!]*$/
// "commit" as a request (opening a clause, or after and/then/please/can you), not as a noun:
// "look at the last commit" and "reword the commit message" approve nothing.
const ASKS_TO_COMMIT =
  /(^|[,;.!?]\s*|\b(?:and|then|please|now|you can|can you|could you|go ahead and|let's|feel free to|you may|want you to|remember to)\s+)commit\b(?!\s+message)/
const SLASH_COMMIT = /^\/(commit-commands:)?commit(-push-pr)?\b/

export function approvesCommit(prompt: string): boolean {
  const text = prompt
    .trim()
    .toLowerCase()
    .replace(/\b(don'?t|do not) forget to\b/g, 'remember to')
  if (SLASH_COMMIT.test(text)) return true
  if (NEGATED.test(text)) return false
  return BARE_GO.test(text) || ASKS_TO_COMMIT.test(text)
}

const GIT_OPTIONS_WITH_VALUE = new Set(['-C', '-c', '--git-dir', '--work-tree', '--namespace', '--exec-path'])
const PREFIX_COMMANDS = new Set(['env', 'command', 'time', 'nohup', 'exec'])
const HEREDOC_BODY = /<<-?\s*(['"]?)(\w+)\1[^\n]*\n[\s\S]*?(?:\n[ \t]*\2[ \t]*(?=\n|$)|$)/g
const QUOTED = /'[^']*'|"(?:[^"\\]|\\.)*"/g

// Heredoc bodies and quoted strings are data, not commands, so they are blanked before the
// command line is split into simple commands at `;`, `&&`, `||`, `|` and newlines.
export function runsGitCommit(command: string): boolean {
  const code = command.replace(HEREDOC_BODY, ' ').replace(QUOTED, "''")
  return code.split(/&&|\|\||[;|\n]/).some(segment => {
    const words = segment.trim().replace(/^[({]\s*/, '').split(/\s+/)
    let i = 0
    while (
      i < words.length &&
      (PREFIX_COMMANDS.has(words[i] ?? '') || /^[A-Za-z_][A-Za-z0-9_]*=/.test(words[i] ?? ''))
    ) {
      i++
    }
    if (!/(^|\/)git$/.test(words[i] ?? '')) return false
    i++
    while (i < words.length && (words[i] ?? '').startsWith('-')) {
      i += GIT_OPTIONS_WITH_VALUE.has(words[i] ?? '') ? 2 : 1
    }
    return words[i] === 'commit'
  })
}

const EDIT_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit'])
// What the approval writers' .catch stores: a hook that fails is skipped, which would leave an
// earlier go standing.
const REVOKED: CommitApproval = { isApproved: false, hasCommitted: false }

export const register: Register = on => {
  on('prompt.submit', async ($, e, next) => {
    if (isPersonsOwn(e.origin)) {
      await update($, approval, () => ({ isApproved: approvesCommit(e.text), hasCommitted: false }))
    }
    return next(e)
  }).catch(async ($, e, next) => {
    await update($, approval, () => REVOKED).catch(() => undefined)
    return next(e)
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (!runsGitCommit(e.command)) return next(e)
    const state = await read($, approval)
    if (!state.isApproved) return { deny: DENY }
    const ran = await next(e)
    if (ran.deny === undefined && ran.isError !== true) {
      await update($, approval, s => ({ ...s, hasCommitted: true }))
    }
    return ran
  }).catch(($, e, next) => (next.called ? next(e) : { deny: `${DENY} (its guard failed)` }))

  on('turn.complete', async ($, e, next) => {
    const answered = await next(e)
    if (e.agentId !== undefined) return answered
    const { isApproved } = await read($, approval)
    const status = isApproved ? undefined : await $.process.run(['git', 'status', '--porcelain']).catch(() => undefined)
    const isAwaiting = status !== undefined && status.exitCode === 0 && status.stdout.trim() !== ''
    $.ui.status(isAwaiting ? 'commit-gate: uncommitted changes, awaiting go' : undefined)
    return answered
  })

  // Approval covers the work the person reviewed. Once a commit has landed, a further edit is
  // new work they have not seen, so the next commit needs a fresh go.
  on('tool.call', async ($, e, next) => {
    if (EDIT_TOOLS.has(String(e.tool))) {
      await update($, approval, s => (s.hasCommitted ? REVOKED : s))
    }
    return next(e)
  }).catch(async ($, e, next) => {
    await update($, approval, () => REVOKED).catch(() => undefined)
    return next(e)
  })
}

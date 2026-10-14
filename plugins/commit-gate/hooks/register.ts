import { atom, read, update } from 'claude-code'
import type { EngineInterface, PromptOrigin, Register } from 'claude-code'

import type { CommitApproval } from '../types'

const approval = atom({ plugin: 'commit-gate', key: 'approval' } as const, {
  isApproved: false,
  hasCommitted: false,
} as CommitApproval)

const BACKSTOP = '(A string-match backstop: it reads `git … commit` in the command line.)'
const DENY =
  'commit-gate: nothing since the last prompt approves a commit. Present the diff and test results, ' +
  `then ask for a go. ${BACKSTOP}`
const lapsedDeny = (path: string) =>
  `commit-gate: the go lapsed when ${path} was edited after the last commit, so this commit holds ` +
  `work the person hasn't seen. Present it, then ask for a fresh go. ${BACKSTOP}`

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
const GO_WORD = String.raw`(?:go ahead|go|yes|y|yep|yeah|ok|okay|lgtm|ship it|approved|proceed|do it)`
// The words that are only a yes once the agent has asked about a commit.
const ASSENT_WORD = String.raw`(?:go for it|please|sure|yup|looks good(?: to me)?|sounds good(?: to me)?|great|perfect|nice|good|👍)`
// A yes or go approves only as the whole answer: "yes, implement the plan" approves the plan, not a commit.
const BARE_GO = new RegExp(String.raw`^(?:${GO_WORD}[\s.,!]*)+$`, 'u')
// Once the agent has asked about a commit, the reply's last clause can be the answer: "don't dim
// for now, go" approves. A yes followed by more work ("looks good. rename it first") does not,
// since the agent would do that work and commit it unseen.
const ASSENT_CLAUSE = new RegExp(String.raw`^(?:(?:${GO_WORD}|${ASSENT_WORD})[\s!]*)+$`, 'u')
const CLAUSE_BREAK = /[.!?;,\n—–]+|\s-\s/
// An earlier clause that refuses ("not yet. looks good") or holds the commit back for something
// ("rename it first. go") outweighs the yes.
const REFUSAL_CLAUSE = /^(?:no|nope|nah|not yet|not now|wait|hold on|hold off|stop|later|don'?t|do not)$/
const HOLDS_BACK = /\b(?:first|before)\b/
// The agent asked about a commit when its message's last sentence names the act ("commit", not
// "committed" or "commit-gate") and asks for an answer: a go, or a question. The agent writes that
// message, so it must not also announce work still to come ("Next I'll do the rename. Say go and
// I'll commit both."): a yes would then cover work done after it and committed unseen.
const SENTENCE_END = /(?<=[.!?])\s+|\n+/
const NAMES_A_COMMIT = /\bcommit\b(?!-)/i
const ASKS = /\bgo\b|\?/i
const WORK_TO_COME = /\b(?:next|then|first|after that),? i'?ll\b|\bi'?ll\b[^.?!\n]*\b(?:first|then)\b/i
// "commit" as a request (opening a clause, or after and/then/please/can you), not as a noun:
// "look at the last commit" and "reword the commit message" approve nothing.
const ASKS_TO_COMMIT =
  /(^|[,;.!?]\s*|\b(?:and|then|please|now|you can|can you|could you|go ahead and|let's|feel free to|you may|want you to|remember to)\s+)commit\b(?!\s+message)/
const SLASH_COMMIT = /^\/(commit-commands:)?commit(-push-pr)?\b/

export function approvesCommit(prompt: string, agentAsked = ''): boolean {
  const text = prompt
    .trim()
    .toLowerCase()
    .replace(/\b(don'?t|do not) forget to\b/g, 'remember to')
  if (SLASH_COMMIT.test(text)) return true
  if (NEGATED.test(text)) return false
  if (BARE_GO.test(text) || ASKS_TO_COMMIT.test(text)) return true
  if (!askedAboutCommit(agentAsked)) return false
  const clauses = text
    .split(CLAUSE_BREAK)
    .map(clause => clause.trim())
    .filter(clause => clause !== '')
  const last = clauses.pop()
  if (last === undefined || !ASSENT_CLAUSE.test(last)) return false
  return !clauses.some(clause => REFUSAL_CLAUSE.test(clause) || HOLDS_BACK.test(clause))
}

function askedAboutCommit(agentText: string): boolean {
  const last = agentText
    .split(SENTENCE_END)
    .map(sentence => sentence.trim())
    .filter(sentence => sentence !== '')
    .at(-1)
  if (last === undefined || !NAMES_A_COMMIT.test(last) || !ASKS.test(last)) return false
  return !WORK_TO_COME.test(agentText)
}

// The text of the agent's most recent message: what the person's prompt is answering. The new
// prompt may already be in the transcript, so it and tool results are passed over; any other
// prompt of the person's ends the search, since a question it answered is no longer open.
async function lastAgentText($: EngineInterface, prompt: string): Promise<string> {
  const rows = await $.session.messages()
  if (!Array.isArray(rows)) return ''
  let isPromptSeen = false
  for (let i = rows.length - 1; i >= 0; i--) {
    const row = rows[i]
    if (row?.role === 'assistant') {
      if (row.text) return String(row.text)
    } else if (row?.toolResults?.length) {
      continue
    } else if (!isPromptSeen && String(row?.text ?? '').trim() === prompt.trim()) {
      isPromptSeen = true
    } else {
      return ''
    }
  }
  return ''
}

const GIT_OPTIONS_WITH_VALUE = new Set(['-C', '-c', '--git-dir', '--work-tree', '--namespace', '--exec-path'])
// Words a command can sit behind: shell keywords, and commands that run their arguments.
const PREFIX_WORDS = new Set(['env', 'command', 'time', 'nohup', 'exec', 'if', 'then', 'else', 'elif', 'do', 'while', 'until', '!'])
const HEREDOC_BODY = /<<-?\s*(['"]?)(\w+)\1[^\n]*\n[\s\S]*?(?:\n[ \t]*\2[ \t]*(?=\n|$)|$)/g
const SINGLE_QUOTED = /'[^']*'/g
const SUBSTITUTION = /\$\(([^()]*)\)|`([^`]*)`/g
const DOUBLE_QUOTED = /"(?:[^"\\]|\\.)*"/g

// Heredoc bodies and quoted strings are data, not commands, so they are blanked before the
// command line is split into simple commands at `;`, `&&`, `||`, `&`, `|`, parentheses and
// newlines. A command substitution runs even inside double quotes, so each one is checked as a
// command line of its own.
export function runsGitCommit(command: string): boolean {
  const code = command.replace(HEREDOC_BODY, ' ').replace(SINGLE_QUOTED, "''")
  const substituted = [...code.matchAll(SUBSTITUTION)].map(m => m[1] ?? m[2] ?? '')
  if (substituted.some(runsGitCommit)) return true
  return code
    .replace(SUBSTITUTION, "''")
    .replace(DOUBLE_QUOTED, "''")
    .split(/&&|\|\||[;|&()\n]/)
    .some(segment => {
      const words = segment.trim().replace(/^\{\s*/, '').split(/\s+/)
      let i = 0
      while (i < words.length && (PREFIX_WORDS.has(words[i] ?? '') || /^[A-Za-z_][A-Za-z0-9_]*=/.test(words[i] ?? ''))) {
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
// Scratch files (a commit message written for `-F`, notes) are not work the person reviews, so
// editing one doesn't lapse a go. Claude Code's scratchpad sits under these on macOS and Linux.
const SCRATCH_ROOTS = ['/tmp/', '/private/tmp/', '/var/folders/', '/private/var/folders/']

const isUnderScratch = (path: string) => SCRATCH_ROOTS.some(root => path.startsWith(root))

// Where an edit really lands, every link followed. A file a Write is about to create doesn't exist
// yet, so its folder is resolved instead. Undefined when neither resolves: the edit then counts as
// work, never as scratch.
async function landsAt($: EngineInterface, path: string): Promise<string | undefined> {
  const real = async (p: string) => (await $.fs.stat(p, { resolve: true }).catch(() => undefined))?.realPath
  const file = await real(path)
  if (file !== undefined) return file
  const slash = path.lastIndexOf('/')
  const folder = slash > 0 ? await real(path.slice(0, slash)) : undefined
  return folder === undefined ? undefined : `${folder}${path.slice(slash)}`
}

// A scratch edit by its spelling and by where it lands: a link under /tmp into a repository, or a
// path that climbs out with `..`, is work.
async function isScratchEdit($: EngineInterface, path: string): Promise<boolean> {
  if (!isUnderScratch(path) || path.split('/').includes('..')) return false
  const real = await landsAt($, path)
  return real !== undefined && isUnderScratch(real)
}
// What the approval writers' .catch stores: a hook that fails is skipped, which would leave an
// earlier go standing.
const REVOKED: CommitApproval = { isApproved: false, hasCommitted: false }

export const register: Register = on => {
  on('prompt.submit', async ($, e, next) => {
    if (isPersonsOwn(e.origin)) {
      // An unreadable transcript only loses the context: the prompt is then judged on its own.
      const asked = await lastAgentText($, e.text).catch(() => '')
      await update($, approval, () => ({ isApproved: approvesCommit(e.text, asked), hasCommitted: false }))
    }
    return next(e)
  }).catch(async ($, e, next) => {
    await update($, approval, () => REVOKED).catch(() => undefined)
    return next(e)
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (!runsGitCommit(e.command)) return next(e)
    const state = await read($, approval)
    if (!state.isApproved) return { deny: state.lapsedBy === undefined ? DENY : lapsedDeny(state.lapsedBy) }
    const ran = await next(e)
    if (ran.deny === undefined && ran.isError !== true) {
      await update($, approval, s => ({ ...s, hasCommitted: true }))
    }
    return ran
  }).catch(async ($, e, next) => {
    // A failure after the commit ran may have skipped recording it, which would leave this go
    // standing for the next commit past an edit that should lapse it.
    await update($, approval, () => REVOKED).catch(() => undefined)
    return next.called ? next(e) : { deny: `${DENY} (its guard failed)` }
  })

  // Approval covers the work the person reviewed. Once a commit has landed, a further edit is
  // new work they have not seen, so the next commit needs a fresh go.
  on('tool.call', async ($, e, next) => {
    if (EDIT_TOOLS.has(String(e.tool))) {
      const input = e as { file_path?: unknown; notebook_path?: unknown }
      const path = String(input.file_path ?? input.notebook_path ?? 'a file')
      // Only an edit after a commit can lapse the go, so only then is the path resolved.
      if ((await read($, approval)).hasCommitted && !(await isScratchEdit($, path))) {
        await update($, approval, s => (s.hasCommitted ? { ...REVOKED, lapsedBy: path } : s))
      }
    }
    return next(e)
  }).catch(async ($, e, next) => {
    await update($, approval, () => REVOKED).catch(() => undefined)
    return next(e)
  })
}

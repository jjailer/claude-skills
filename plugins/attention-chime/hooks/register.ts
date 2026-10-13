import { atom, read, update } from 'claude-code'
import type { EngineInterface, PromptOrigin, Register } from 'claude-code'

import type { ChimeState } from '../types'

const SYSTEM_SOUNDS = '/System/Library/Components/CoreAudio.component/Contents/SharedSupport/SystemSounds'
const DECISION = '/System/Library/Sounds/Bottle.aiff'
const DONE = `${SYSTEM_SOUNDS}/siri/jbl_confirm.caf`
const COMPACT = '/System/Library/Sounds/Purr.aiff'
const FALLBACK = '/System/Library/Sounds/Glass.aiff'

// A dialog can raise both its tool call and a permission notification: one ring covers both.
const QUIET_MS = 5_000
const ASKS_THE_PERSON = new Set(['AskUserQuestion', 'ExitPlanMode'])
const DECISION_NOTIFICATIONS = new Set([
  'permission_prompt',
  'worker_permission_prompt',
  'elicitation_dialog',
  'elicitation_url_dialog',
  'agent_needs_input',
])
// Work that wakes the session with a result. A background shell or monitor may never finish (a dev
// server, a log tail), so it can't hold the "done" sound back.
const AWAITED_TASKS = new Set(['subagent', 'workflow'])

const chime = atom({ plugin: 'attention-chime', key: 'chime' } as const, {
  isArmed: false,
  lastDecisionAt: null,
} as ChimeState)

// Only the person's own request starts work worth a "done" sound. A task notification or a peer's
// message wakes the session without anyone waiting on it, and a `claude -p` script has nobody at
// the terminal. An auto-continuation counts: approving a plan with a cleared context starts the
// implementation that way.
function isPersonsRequest(origin: PromptOrigin): boolean {
  switch (origin.kind) {
    case 'composer':
    case 'bridge':
    case 'slack-ping':
    case 'auto-continuation':
      return true
    case 'plugin':
      return origin.asUser === true
    default:
      return false
  }
}

async function play($: EngineInterface, sound: string) {
  for (const file of [sound, FALLBACK]) {
    const ran = await $.process.run(['afplay', file]).catch(() => undefined)
    if (ran?.exitCode === 0) return
  }
  // No afplay (a Linux box over ssh): a BEL on the terminal rings the emulator at the far end.
  await $.process.run(['sh', '-c', "printf '\\a' > /dev/tty"]).catch(() => undefined)
}

async function ringForDecision($: EngineInterface) {
  const now = await $.clock.now()
  const { lastDecisionAt } = await read($, chime)
  if (lastDecisionAt !== null && now - lastDecisionAt < QUIET_MS) return
  await update($, chime, s => ({ ...s, lastDecisionAt: now }))
  void play($, DECISION)
}

function isAwaited(e: { background_tasks?: { type: string }[]; session_crons?: { recurring: boolean }[] }) {
  // A recurring /loop never ends the session's wait; a one-shot wakeup does resume it.
  return (
    (e.background_tasks ?? []).some(task => AWAITED_TASKS.has(task.type)) ||
    (e.session_crons ?? []).some(cron => !cron.recurring)
  )
}

export const register: Register = on => {
  on('prompt.submit', async ($, e, next) => {
    if (isPersonsRequest(e.origin)) await update($, chime, s => ({ ...s, isArmed: true }))
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    if (ASKS_THE_PERSON.has(String(e.tool)) && e.agentId === undefined) await ringForDecision($)
    return next(e)
  })

  // idle_prompt repeats a stop that already rang; auth_success needs nothing from anyone.
  on('classic.Notification', async ($, e, next) => {
    if (DECISION_NOTIFICATIONS.has(e.notification_type)) await ringForDecision($)
    return next(e)
  })

  // Beneath this hook run the Stop gates (settings and plugin hooks alike): a block means the turn
  // goes on, and its final stop arrives later with stop_hook_active set.
  on('classic.Stop', async ($, e, next) => {
    const result = await next(e)
    if (result.block !== undefined) return result
    if (isAwaited(e) || !(await read($, chime)).isArmed) return result
    await update($, chime, s => ({ ...s, isArmed: false }))
    void play($, DONE)
    return result
  })

  // A manual /compact is one the person typed, so they are already there.
  on('classic.PreCompact', async ($, e, next) => {
    if (e.trigger === 'auto') void play($, COMPACT)
    return next(e)
  })
}

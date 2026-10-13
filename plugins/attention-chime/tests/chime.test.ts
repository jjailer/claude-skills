import { describe, expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

const BOTTLE = '/System/Library/Sounds/Bottle.aiff'
const CONFIRM = '/System/Library/Components/CoreAudio.component/Contents/SharedSupport/SystemSounds/siri/jbl_confirm.caf'
const PURR = '/System/Library/Sounds/Purr.aiff'
const GLASS = '/System/Library/Sounds/Glass.aiff'

type Kind = 'composer' | 'task-notification' | 'peer' | 'sdk' | 'auto-continuation'

// The machine beneath the plugin: afplay plays every file it is given unless told one is missing,
// and the Stop gates pass unless told to block the first attempt.
function speaker(on: On, { missing = [] as string[], isStopBlocked = false } = {}): string[] {
  const played: string[] = []
  on('process.run', ($, e) => {
    const file = String(e.argv[1])
    if (e.argv[0] !== 'afplay') return { value: { exitCode: 0, stdout: '', stderr: '' } } as never
    if (missing.includes(file)) return { value: { exitCode: 1, stdout: '', stderr: 'no such file' } } as never
    played.push(file)
    return { value: { exitCode: 0, stdout: '', stderr: '' } } as never
  })
  on('prompt.submit', ($, e) => ({ text: e.text }))
  on('tool.call', () => ({ result: {} }) as never)
  on('classic.Stop', ($, e) => (isStopBlocked && !e.stop_hook_active ? { block: 'ruff violations' } : {}))
  on('classic.Notification', () => ({}))
  on('classic.PreCompact', () => ({}))
  return played
}

async function say($: Engine, kind: Kind = 'composer') {
  await $.prompt.submit({ text: 'fix the padding', wait: false, origin: { kind } } as never)
}

async function pluginSays($: Engine, asUser: boolean) {
  await $.prompt.submit({ text: 'go', wait: false, origin: { kind: 'plugin', plugin: 'buttons', asUser } } as never)
}

async function stop($: Engine, fields: Record<string, unknown> = {}) {
  return $.classic.Stop({ stop_hook_active: false, background_tasks: [], session_crons: [], ...fields } as never)
}

async function notify($: Engine, notification_type: string) {
  return $.classic.Notification({ message: 'Claude needs your attention', notification_type } as never)
}

describe('the work you asked for is done', () => {
  test('rings once per request, not again when a notification wakes it later', async ($, on) => {
    const played = speaker(on)
    const clock = mock.clock(on)
    await say($)
    await stop($)
    await clock.advance(60_000)
    await say($, 'task-notification')
    await stop($)
    expect(played).toEqual([CONFIRM])
  })

  test('waits out a stop a gate blocked, then rings at the real end', async ($, on) => {
    const played = speaker(on, { isStopBlocked: true })
    mock.clock(on)
    await say($)
    await stop($)
    expect(played).toEqual([])
    await stop($, { stop_hook_active: true })
    expect(played).toEqual([CONFIRM])
  })

  test('waits for background work still in flight', async ($, on) => {
    const played = speaker(on)
    mock.clock(on)
    await say($)
    await stop($, { background_tasks: [{ id: 'a1', type: 'subagent', status: 'pending', description: 'review' }] })
    expect(played).toEqual([])
    await stop($)
    expect(played).toEqual([CONFIRM])
  })

  test('waits for a one-shot wakeup', async ($, on) => {
    const played = speaker(on)
    mock.clock(on)
    await say($)
    await stop($, { session_crons: [{ id: 'c1', schedule: '17 14 * * *', recurring: false, prompt: 'check CI' }] })
    expect(played).toEqual([])
  })

  // A dev server or a /loop never ends, so waiting on one would silence the sound for the session.
  test('does not wait for a background shell or a recurring loop', async ($, on) => {
    const played = speaker(on)
    mock.clock(on)
    await say($)
    await stop($, {
      background_tasks: [{ id: 's1', type: 'shell', status: 'running', description: 'dev server' }],
      session_crons: [{ id: 'c2', schedule: '*/5 * * * *', recurring: true, prompt: '/loop /babysit' }],
    })
    expect(played).toEqual([CONFIRM])
  })

  test('rings for a plan carried on with a cleared context', async ($, on) => {
    const played = speaker(on)
    mock.clock(on)
    await say($, 'auto-continuation')
    await stop($)
    expect(played).toEqual([CONFIRM])
  })

  test('counts a prompt a plugin sends as the person, and only that one', async ($, on) => {
    const played = speaker(on)
    const clock = mock.clock(on)
    await pluginSays($, false)
    await stop($)
    expect(played).toEqual([])
    await clock.advance(60_000)
    await pluginSays($, true)
    await stop($)
    expect(played).toEqual([CONFIRM])
  })

  test('stays silent at the end of a claude -p script', async ($, on) => {
    const played = speaker(on)
    mock.clock(on)
    await say($, 'sdk')
    await stop($)
    expect(played).toEqual([])
  })

  test('still rings when the work ends just after a decision', async ($, on) => {
    const played = speaker(on)
    mock.clock(on)
    await say($)
    await notify($, 'permission_prompt')
    await stop($)
    expect(played).toEqual([BOTTLE, CONFIRM])
  })

  test('stays silent for a turn nobody asked for', async ($, on) => {
    const played = speaker(on)
    mock.clock(on)
    await say($, 'task-notification')
    await stop($)
    await say($, 'peer')
    await stop($)
    expect(played).toEqual([])
  })
})

describe('a decision is waiting', () => {
  test('rings for every notification that needs an answer, not for reminders', async ($, on) => {
    const played = speaker(on)
    const clock = mock.clock(on)
    await notify($, 'idle_prompt')
    await notify($, 'auth_success')
    await notify($, 'agent_completed')
    expect(played).toEqual([])
    const asks = [
      'permission_prompt',
      'worker_permission_prompt',
      'elicitation_dialog',
      'elicitation_url_dialog',
      'agent_needs_input',
    ]
    for (const type of asks) {
      await notify($, type)
      await clock.advance(10_000)
    }
    expect(played).toEqual(asks.map(() => BOTTLE))
  })

  test('rings when the main thread asks a question or presents a plan', async ($, on) => {
    const played = speaker(on)
    const clock = mock.clock(on)
    await $.tool.call({ tool: 'AskUserQuestion', questions: [] } as never)
    await clock.advance(10_000)
    await $.tool.call({ tool: 'ExitPlanMode' } as never)
    expect(played).toEqual([BOTTLE, BOTTLE])
  })

  test('stays silent for a subagent question', async ($, on) => {
    const played = speaker(on)
    mock.clock(on)
    await $.tool.call({ tool: 'AskUserQuestion', questions: [], agentId: 'sub-1' } as never)
    expect(played).toEqual([])
  })

  test('rings once for a dialog that also raises a notification', async ($, on) => {
    const played = speaker(on)
    mock.clock(on)
    await $.tool.call({ tool: 'ExitPlanMode' } as never)
    await notify($, 'permission_prompt')
    expect(played).toEqual([BOTTLE])
  })
})

describe('compaction', () => {
  test('purrs when it compacts on its own, not when you asked', async ($, on) => {
    const played = speaker(on)
    mock.clock(on)
    await $.classic.PreCompact({ trigger: 'manual', custom_instructions: null } as never)
    await $.classic.PreCompact({ trigger: 'auto', custom_instructions: null } as never)
    expect(played).toEqual([PURR])
  })
})

// A macOS update that renames a system sound would otherwise silence the chime for good.
test('falls back to Glass when a sound is missing', async ($, on) => {
  const played = speaker(on, { missing: [BOTTLE] })
  mock.clock(on)
  await notify($, 'permission_prompt')
  expect(played).toEqual([GLASS])
})

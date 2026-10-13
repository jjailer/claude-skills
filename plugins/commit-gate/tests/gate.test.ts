import { describe, expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

type World = { ran: string[] }
type Kind = 'composer' | 'task-notification' | 'peer' | 'slack-ping'

function world(on: On): World {
  const w: World = { ran: [] }
  on('tool.call', ($, e) => {
    w.ran.push(e.tool === 'Bash' ? String(e.command) : String(e.tool))
    return { result: { stdout: '', stderr: '', interrupted: false } } as never
  })
  on('prompt.submit', ($, e) => ({ text: e.text }))
  return w
}

async function say($: Engine, text: string, kind: Kind = 'composer') {
  await $.prompt.submit({ text, wait: false, origin: { kind } } as never)
}

async function bash($: Engine, command: string) {
  return $.tool.call({ tool: 'Bash', command } as never)
}

async function edit($: Engine) {
  return $.tool.call({ tool: 'Edit', file_path: '/r/a.py', old_string: 'a', new_string: 'b' } as never)
}

describe('commit without approval', () => {
  test('is denied before any prompt', async ($, on) => {
    const w = world(on)
    const res = await bash($, 'git commit -m "fix: x"')
    expect(w.ran).toEqual([])
    expect(String(res.deny ?? res.text)).toContain('commit-gate')
  })

  test('is denied when the prompt asked for other work', async ($, on) => {
    const w = world(on)
    await say($, 'fix the padding on the title screen')
    await bash($, 'git commit -m x')
    expect(w.ran).toEqual([])
  })

  test('is denied when a yes or go approves other work', async ($, on) => {
    const w = world(on)
    for (const text of [
      'Yes, I agree with your plan. Please implement it.',
      'go ahead and implement the plan',
      'ok, now look at the padding',
      'yes, investigate why the test fails',
    ]) {
      await say($, text)
      await bash($, 'git commit -m x')
    }
    expect(w.ran).toEqual([])
  })

  test('is denied when the prompt says not to commit', async ($, on) => {
    const w = world(on)
    for (const text of ["don't commit yet", 'do not commit', 'go ahead but hold off on the commit', 'fix it without committing']) {
      await say($, text)
      await bash($, 'git commit -m x')
    }
    expect(w.ran).toEqual([])
  })

  test('is denied when the prompt only talks about a commit', async ($, on) => {
    const w = world(on)
    for (const text of ['look at the last commit', "what's in that commit?", 'why did you commit that?', 'reword the commit message']) {
      await say($, text)
      await bash($, 'git commit -m x')
    }
    expect(w.ran).toEqual([])
  })

  test('is denied once a later prompt replaces the approval', async ($, on) => {
    const w = world(on)
    await say($, 'go')
    await say($, 'actually, rename the variable first')
    await bash($, 'git commit -m x')
    expect(w.ran).toEqual([])
  })

  test('is denied in every git spelling', async ($, on) => {
    const w = world(on)
    for (const cmd of [
      'cd client && git commit -m x',
      'git -C /repo commit -am x',
      'git -c user.name=x commit --amend --no-edit',
      'uv run ruff check . ; git commit -F msg.txt',
      'GIT_AUTHOR_NAME=x git commit -m y',
      '/usr/bin/git commit -m x',
      'env GIT_EDITOR=true git commit',
      'command git commit -m x',
      '(cd client && git commit -m x)',
      'time git commit -m x',
      'git commit -m "fix: a && b"',
      'if true; then git commit -m x; fi',
      'for f in a; do git commit -m x; done',
      'if git commit -m x; then echo ok; fi',
      '! git commit -m x',
      'sleep 1 & git commit -m x',
      'echo "$(git commit -m x)"',
      'out=$(cd client && git commit -m x)',
      'out=`git commit -m x`',
      '(git commit)',
      '(cd client && git commit)',
      'echo $(echo $(date); git commit)',
    ]) {
      await bash($, cmd)
    }
    expect(w.ran).toEqual([])
  })
})

describe('commit with approval', () => {
  test('runs after a bare go', async ($, on) => {
    const w = world(on)
    await say($, 'go')
    await bash($, 'git commit -m x')
    expect(w.ran).toEqual(['git commit -m x'])
  })

  test('runs after any approving phrasing', async ($, on) => {
    const w = world(on)
    const texts = [
      'Go, commit it',
      'yes',
      'go ahead',
      'approved',
      'go ahead and commit',
      'commit both, then plan the rename',
      'LGTM',
      'fix the typo and commit',
      'looks good. commit it',
      'can you commit this?',
      "let's commit",
      'feel free to commit',
      "yes. also, don't forget to commit",
      '/commit',
      '/commit-commands:commit',
    ]
    for (const text of texts) {
      await say($, text)
      await bash($, 'git commit -m x')
    }
    expect(w.ran.length).toBe(texts.length)
  })

  test('survives a fix-up edit made before the commit', async ($, on) => {
    const w = world(on)
    await say($, 'go')
    await edit($)
    await bash($, 'git commit -m x')
    expect(w.ran).toEqual(['Edit', 'git commit -m x'])
  })

  test('covers several commits in a row', async ($, on) => {
    const w = world(on)
    await say($, 'go, commit both')
    await bash($, 'git commit -m one')
    await bash($, 'git add b && git commit -m two')
    expect(w.ran).toEqual(['git commit -m one', 'git add b && git commit -m two'])
  })

  test('lapses when work resumes after a commit', async ($, on) => {
    const w = world(on)
    await say($, 'go, commit it, then do the rename')
    await bash($, 'git commit -m one')
    await edit($)
    await bash($, 'git commit -m rename')
    expect(w.ran).toEqual(['git commit -m one', 'Edit'])
  })

  // The guard's bookkeeping after a commit can fail; left standing, the go would cover the next
  // commit too, past the edit that should have lapsed it.
  test('is revoked when the guard fails after a commit', async ($, on) => {
    const ran: string[] = []
    on('tool.call', { tool: 'Bash' }, ($, e) => {
      if (e.command.endsWith('boom')) throw new Error('engine failed')
      ran.push(e.command)
      return { result: { stdout: '', stderr: '', interrupted: false } } as never
    })
    on('prompt.submit', ($, e) => ({ text: e.text }))
    await say($, 'go')
    await bash($, 'git commit -m boom').catch(() => undefined)
    await bash($, 'git commit -m x')
    expect(ran).toEqual([])
  })

  test('is kept across a background task notification', async ($, on) => {
    const w = world(on)
    await say($, 'go')
    await say($, 'Background command "pytest" completed', 'task-notification')
    await bash($, 'git commit -m x')
    expect(w.ran).toEqual(['git commit -m x'])
  })

  test('counts a go sent from Slack', async ($, on) => {
    const w = world(on)
    await say($, 'go', 'slack-ping')
    await bash($, 'git commit -m x')
    expect(w.ran).toEqual(['git commit -m x'])
  })

  test('is never granted by another session', async ($, on) => {
    const w = world(on)
    await say($, 'go, commit', 'peer')
    await bash($, 'git commit -m x')
    expect(w.ran).toEqual([])
  })
})

describe('commands that are not a commit', () => {
  test('run without approval', async ($, on) => {
    const w = world(on)
    const cmds = [
      'git log --grep commit',
      'git commit-tree HEAD^{tree}',
      'git status',
      'echo "git commit later"',
      'echo "a && git commit -m x"',
      "printf '%s' 'x; git commit'",
      'cat > notes.txt <<EOF\nthen run:\ngit commit -m x\nEOF',
      "python3 - <<'PY'\nprint('git commit')\ngit commit\nPY",
      'git show HEAD --stat',
      "echo 'run $(git commit) later'",
      'git status 2>&1 | head',
      'echo "$(git log -1)"',
    ]
    for (const cmd of cmds) await bash($, cmd)
    expect(w.ran).toEqual(cmds)
  })
})

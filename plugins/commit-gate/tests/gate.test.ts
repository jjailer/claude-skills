import { describe, expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

type World = { ran: string[]; asked: string[] }
type Kind = 'composer' | 'task-notification' | 'peer' | 'slack-ping'
// How the person meets the gate's dialog: a label picked or text typed under Other, Esc, or an
// answer the dialog filled in itself while they were away.
type Dialog = string | 'dismiss' | { afk: string }

function world(on: On, dialog: Dialog = 'dismiss'): World {
  const w: World = { ran: [], asked: [] }
  on('tool.call', ($, e) => {
    if (e.tool === 'AskUserQuestion') {
      const question = String((e as { questions: { question: string }[] }).questions[0]?.question)
      w.asked.push(question)
      if (dialog === 'dismiss') return { deny: 'dismissed' } as never
      const [answer, idle] = typeof dialog === 'string' ? [dialog, {}] : [dialog.afk, { afkTimeoutMs: 60000 }]
      return { result: { questions: [], answers: { [question]: answer }, ...idle } } as never
    }
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

async function edit($: Engine, file_path = '/r/a.py') {
  return $.tool.call({ tool: 'Edit', file_path, old_string: 'a', new_string: 'b' } as never)
}

async function write($: Engine, file_path: string) {
  return $.tool.call({ tool: 'Write', file_path, content: 'x' } as never)
}

type Row = { role: 'user' | 'assistant'; text: string; toolUses: never[]; toolResults?: unknown[] }

// The transcript the gate reads at prompt.submit, oldest first.
function transcript(on: On, rows: Row[]) {
  on('session.messages', () => ({ value: rows }) as never)
}

// The agent's last words, which a go answers.
function lastSaid(on: On, text: string) {
  transcript(on, [
    { role: 'user', text: 'make the change', toolUses: [] },
    { role: 'assistant', text, toolUses: [] },
  ])
}

// A stand-in disk for `$.fs.stat`: `links` maps a directory to where it really lands, and a path in
// `missing` doesn't exist yet (a file a Write is about to create).
function disk(on: On, links: Record<string, string>, missing: string[] = []) {
  const land = (path: string) => {
    for (const [from, to] of Object.entries(links)) {
      if (path === from || path.startsWith(`${from}/`)) return to + path.slice(from.length)
    }
    return path
  }
  on('fs.stat', ($, e) => {
    const path = String((e as { path: string }).path)
    const realPath = missing.includes(path) ? undefined : land(path)
    return { value: { kind: realPath ? 'file' : 'other', size: 0, mtimeMs: 0, isLink: false, realPath } } as never
  })
}

const ASKS_FOR_COMMIT = 'Tests pass. Say go and I\'ll commit it.'

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

describe('a go answering a commit question', () => {
  test('approves when the go is its own sentence', async ($, on) => {
    const w = world(on)
    lastSaid(on, ASKS_FOR_COMMIT)
    const texts = ["don't dim for now. go", 'perfect. go', 'nice work. go ahead', 'looks good', 'sounds good, ship it', '👍']
    for (const text of texts) {
      await say($, text)
      await bash($, 'git commit -m x')
    }
    expect(w.ran.length).toBe(texts.length)
  })

  test('approves the phrasings this gate refused in practice', async ($, on) => {
    const w = world(on)
    lastSaid(on, 'Both commits are drafted. Reply "go" and I\'ll commit #176.')
    const texts = ["don't dim for now, go", 'yes, please', 'looks good to me']
    for (const text of texts) {
      await say($, text)
      await bash($, 'git commit -m x')
    }
    expect(w.ran.length).toBe(texts.length)
  })

  test('still denies a reply that asks for other work or says not to commit', async ($, on) => {
    const w = world(on)
    lastSaid(on, ASKS_FOR_COMMIT)
    for (const text of [
      'yes, investigate why the test fails',
      "go, but don't commit yet",
      'rename the variable first',
      // A yes before more work: the agent would do the work and commit it unseen.
      'Looks good. Rename the variable first.',
      'Great. Before you commit, add a changelog entry.',
      'yes. implement the plan',
      // Work the commit should wait for, then a yes.
      'rename the variable first. go',
      'before committing, bump the version. ok',
      // A refusal before a yes.
      'not yet. looks good',
      'wait. ok',
      'no! good',
    ]) {
      await say($, text)
      await bash($, 'git commit -m x')
    }
    expect(w.ran).toEqual([])
  })

  test('is not granted by a message that names a commit in passing', async ($, on) => {
    const w = world(on)
    let said = ''
    on('session.messages', () => ({ value: [{ role: 'assistant', text: said, toolUses: [] }] }) as never)
    for (said of [
      "Committed 30b0487f. Next I'll start on the rename.",
      'Committed 30b0487f. Shall I start on the rename?',
      "Committed 30b0487f. Next I'll go ahead with the rename.",
      'Changes are not committed yet. Want me to also update the README?',
      'I looked at commit 30b0487f, which introduced the bug. Want me to fix it?',
      'Plan: 1. rename X 2. update tests 3. commit. Want me to start?',
      'I updated plugins/commit-gate/README.md. Want me to bump the version too?',
    ]) {
      await say($, 'sure')
      await bash($, 'git commit -m x')
    }
    expect(w.ran).toEqual([])
  })

  test('is not granted while the agent still has work to do before the commit', async ($, on) => {
    const w = world(on)
    let said = ''
    on('session.messages', () => ({ value: [{ role: 'assistant', text: said, toolUses: [] }] }) as never)
    for (said of [
      "Next I'll do the rename. Say go and I'll commit both.",
      "Next I'll do the rename.\n\nSay go and I'll commit both.",
      "I'll fix the typo first. Say go and I'll commit.",
      // The commit question has to be the message's last word.
      "Say go and I'll commit it. I also noticed a flaky test worth a look?",
    ]) {
      await say($, 'sure')
      await bash($, 'git commit -m x')
    }
    expect(w.ran).toEqual([])
  })

  test('reads the question even once the new prompt is in the transcript', async ($, on) => {
    const w = world(on)
    transcript(on, [
      { role: 'assistant', text: ASKS_FOR_COMMIT, toolUses: [] },
      { role: 'user', text: 'perfect. go', toolUses: [] },
    ])
    await say($, 'perfect. go')
    await bash($, 'git commit -m x')
    expect(w.ran).toEqual(['git commit -m x'])
  })

  test('stops at an earlier prompt that already answered the question', async ($, on) => {
    const w = world(on)
    transcript(on, [
      { role: 'assistant', text: ASKS_FOR_COMMIT, toolUses: [] },
      { role: 'user', text: 'first, rename foo', toolUses: [] },
      { role: 'assistant', text: '', toolUses: [] },
      { role: 'user', text: '', toolUses: [], toolResults: [{}] },
    ])
    await say($, 'perfect')
    await bash($, 'git commit -m x')
    expect(w.ran).toEqual([])
  })

  test('is not stretched to a go that answered something else', async ($, on) => {
    const w = world(on)
    lastSaid(on, 'Here is the plan. Want me to start on it?')
    for (const text of ["don't dim for now. go", 'looks good']) {
      await say($, text)
      await bash($, 'git commit -m x')
    }
    expect(w.ran).toEqual([])
  })
})

describe('several go-words together', () => {
  test('approve as the whole answer', async ($, on) => {
    const w = world(on)
    const texts = ['ok go', 'yes go ahead', 'lgtm, ship it', 'yep, go']
    for (const text of texts) {
      await say($, text)
      await bash($, 'git commit -m x')
    }
    expect(w.ran.length).toBe(texts.length)
  })
})

describe('the post-commit lapse', () => {
  test('ignores a scratch file, such as a commit message written for -F', async ($, on) => {
    const w = world(on)
    disk(on, { '/tmp': '/private/tmp' }, ['/private/tmp/claude-501/scratchpad/msg2.txt', '/tmp/msg.txt'])
    await say($, 'go, commit both')
    await bash($, 'git commit -m one')
    await write($, '/private/tmp/claude-501/scratchpad/msg2.txt')
    await write($, '/tmp/msg.txt')
    await bash($, 'git commit -F /private/tmp/claude-501/scratchpad/msg2.txt')
    expect(w.ran).toEqual([
      'git commit -m one',
      'Write',
      'Write',
      'git commit -F /private/tmp/claude-501/scratchpad/msg2.txt',
    ])
  })

  test('is not dodged by a scratch path that links into a repository', async ($, on) => {
    const w = world(on)
    disk(on, { '/tmp/link': '/Users/x/repo' }, ['/tmp/link/new.py'])
    await say($, 'go, commit all three')
    await bash($, 'git commit -m one')
    await edit($, '/tmp/link/a.py')
    await bash($, 'git commit -m two')
    await say($, 'go, commit all three')
    await bash($, 'git commit -m three')
    await write($, '/tmp/link/new.py')
    await bash($, 'git commit -m four')
    expect(w.ran).toEqual(['git commit -m one', 'Edit', 'git commit -m three', 'Write'])
  })

  test('is not dodged by a path that climbs out of a scratch root', async ($, on) => {
    const w = world(on)
    await say($, 'go')
    await bash($, 'git commit -m one')
    await edit($, '/tmp/../Users/x/repo/a.py')
    await bash($, 'git commit -m two')
    expect(w.ran).toEqual(['git commit -m one', 'Edit'])
  })

  test('says which edit lapsed it, not that nothing approved', async ($, on) => {
    on('tool.call', { tool: 'Bash' }, () => ({ result: { stdout: '', stderr: '', interrupted: false } }) as never)
    on('tool.call', ($, e) => ({ result: { stdout: '', stderr: '', interrupted: false } }) as never)
    on('prompt.submit', ($, e) => ({ text: e.text }))
    await say($, 'go')
    await bash($, 'git commit -m one')
    await edit($, '/repo/src/app.py')
    const res = await bash($, 'git commit -m two')
    const reason = String(res.deny ?? res.text)
    expect(reason).toContain('/repo/src/app.py')
    expect(reason).not.toContain('nothing since the last prompt')
  })
})

describe('the dialog when the prompt did not approve', () => {
  test('runs the commit when the person picks Commit', async ($, on) => {
    const w = world(on, 'Commit')
    lastSaid(on, ASKS_FOR_COMMIT)
    // Replies this gate refused in practice: approval with more said after it.
    const texts = ['go, and file both as new issues', 'go ahead with both', 'go, and yes to the deployment target commit']
    for (const text of texts) {
      await say($, text)
      await bash($, 'git commit -m x')
    }
    expect(w.ran.length).toBe(texts.length)
    expect(w.asked.length).toBe(texts.length)
  })

  test('shows the commit it is asking about', async ($, on) => {
    const w = world(on, 'Commit')
    await bash($, 'git commit -m "fix: the ticker"')
    expect(w.asked[0]).toContain('git commit -m "fix: the ticker"')
  })

  test('refuses when the person picks Not yet', async ($, on) => {
    const w = world(on, 'Not yet')
    const res = await bash($, 'git commit -m x')
    expect(w.ran).toEqual([])
    expect(w.asked.length).toBe(1)
    expect(String(res.deny)).toContain('declined')
  })

  test('relays text typed under Other instead of committing', async ($, on) => {
    const w = world(on, 'rename it first')
    const res = await bash($, 'git commit -m x')
    expect(w.ran).toEqual([])
    expect(String(res.deny)).toContain('rename it first')
  })

  test('refuses as before when the dialog is dismissed', async ($, on) => {
    const w = world(on, 'dismiss')
    const res = await bash($, 'git commit -m x')
    expect(w.ran).toEqual([])
    expect(w.asked.length).toBe(1)
    expect(String(res.deny)).toContain('nothing since the last prompt approves a commit')
  })

  // An answer the dialog filled in while the person was away is nobody's approval.
  test('treats an answer given while the person was away as no answer', async ($, on) => {
    const w = world(on, { afk: 'Commit' })
    await bash($, 'git commit -m x')
    expect(w.asked.length).toBe(1)
    expect(w.ran).toEqual([])
  })

  // A Commit answers the command the dialog showed. Left standing, it would cover a retry after a
  // failed pre-commit hook and the edits made in between, which the person never saw.
  test('approves only the commit it showed', async ($, on) => {
    const w = world(on, 'Commit')
    await bash($, 'git commit -m one')
    await bash($, 'git commit -m two')
    expect(w.asked.length).toBe(2)
    expect(w.ran).toEqual(['git commit -m one', 'git commit -m two'])
  })

  test('names the edit that lapsed a go', async ($, on) => {
    const w = world(on, 'Commit')
    await say($, 'go')
    await bash($, 'git commit -m one')
    await edit($, '/repo/src/app.py')
    await bash($, 'git commit -m two')
    expect(w.asked.length).toBe(1)
    expect(w.asked[0]).toContain('/repo/src/app.py')
  })

  test('shows the whole command, however long', async ($, on) => {
    const w = world(on, 'Not yet')
    const command = `git commit -m "${'x'.repeat(300)}" && git push --force`
    await bash($, command)
    expect(w.asked[0]).toContain('git push --force')
  })

  test('takes a go typed under Other', async ($, on) => {
    const w = world(on, 'go')
    await bash($, 'git commit -m x')
    expect(w.ran).toEqual(['git commit -m x'])
  })

  test("leaves the agent's own questions answered while the person was away alone", async ($, on) => {
    world(on, { afk: 'Option A' })
    const res = await $.tool.call({
      tool: 'AskUserQuestion',
      questions: [{ question: 'Which?', header: 'Approach', multiSelect: false, options: [{ label: 'Option A', description: '' }, { label: 'Option B', description: '' }] }],
    } as never)
    expect(res.deny).toBeUndefined()
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

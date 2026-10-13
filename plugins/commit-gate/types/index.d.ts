export type CommitApproval = { isApproved: boolean; hasCommitted: boolean }

declare module 'claude-code' {
  interface PluginState {
    'commit-gate': { approval: CommitApproval }
  }
}

// `lapsedBy` is the file whose edit after a commit took the approval back, so the refusal can
// say why instead of claiming nothing approved.
export type CommitApproval = { isApproved: boolean; hasCommitted: boolean; lapsedBy?: string }

declare module 'claude-code' {
  interface PluginState {
    'commit-gate': { approval: CommitApproval }
  }
}

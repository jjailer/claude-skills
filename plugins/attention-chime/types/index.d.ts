export type ChimeState = { isArmed: boolean; lastDecisionAt: number | null }

declare module 'claude-code' {
  interface PluginState {
    'attention-chime': { chime: ChimeState }
  }
}

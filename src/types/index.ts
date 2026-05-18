export type PipelineStatus = 'idle' | 'running' | 'paused' | 'completed' | 'error'
export type SeedanceMode = 'manual' | 'kie'
export type Scenario = 'A' | 'B'
export type Duration = 1 | 2 | 4

export interface PipelineConfig {
  duration: Duration
  scenario: Scenario
  seedanceMode: SeedanceMode
  spots: string[]
  bgmPath?: string
}

export interface CostSummary {
  gptImages: number
  streetViews: number
  kieClips: number
  claudeCalls: number
  totalUsd: number
}

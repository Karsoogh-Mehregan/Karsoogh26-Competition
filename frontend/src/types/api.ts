export interface Holding {
  id: number
  node_code: string
  node_name: string
  level: string
  slot: number
  floor: number | null
  grade: number | null
  is_spawn: boolean
}

export interface Team {
  code: string
  name: string
  balance: number | null
  color: string | null
  holdings: Holding[]
}

export interface Me {
  id: number
  username: string
  is_staff: boolean
  is_mentor: boolean
  is_game_god: boolean
  is_designer: boolean
  team: { code: string; name: string } | null
}

export interface LoginCredentials {
  username: string
  password: string
}

export interface AssignQuestionResult {
  id: number
  team: { code: string; name: string; balance: number }
  node: { code: string; name: string; level: string }
  slot: number
  floor: number | null
  question_id: number | null
  question_assigned_at: string | null
  expires_at: string | null
  is_expired: boolean
}

export type AnswerType = 'text' | 'file' | 'numeric'

export interface QuestionForTeam {
  code: string
  title: string
  body: string
  answer_type: AnswerType
  attachment_url: string | null
  expires_at: string | null
  remaining_seconds: number
}

export type AttemptStatus = 'no_question' | 'open' | 'answered' | 'expired' | 'graded'

export interface AttemptSubmission {
  id: number
  submitted_at: string
}

export interface ActiveAttempt {
  id: number
  node_code: string
  node_name: string
  level: string
  slot: number
  floor: number | null
  is_spawn: boolean
  grade: number | null
  expires_at: string | null
  remaining_seconds: number
  is_expired: boolean
  question: QuestionForTeam | null
  submission: AttemptSubmission | null
  status: AttemptStatus
}

export interface SubmitCreated {
  id: number
  submitted_at: string
}

export interface LeaderboardRow {
  rank: number
  code: string
  name: string
  balance: number
}

export interface SubmissionRow {
  id: number
  submitted_at: string
  team_id: number
  team_code: string
  team_name: string
  node_code: string
  level: string
  question_id: number
  question_code: string
  question_title: string
  graded: boolean
}

export interface GradeResult {
  occupancy_id: number
  grade: number | null
  grade_multiplier: string | null
  points: number
  released_at: string | null
  release_reason: string
}

export type GameStatus = 'not_started' | 'running' | 'paused' | 'finished'

export interface GameState {
  status: GameStatus
  status_display: string
  is_running: boolean
  server_time: string
  started_at: string | null
  accumulated_seconds: number
  running_since: string | null
  duration_seconds: number
  elapsed_seconds: number | null
  remaining_seconds: number | null
  leaderboard_public: boolean
}

export interface GameSettings {
  status: GameStatus
  leaderboard_public: boolean
  duration_minutes: number
  initial_balance: number
}

export interface GameRestartResult {
  occupancies: number
  submissions: number
  entry_attempts: number
  teams: number
}

export interface EntryAttempt {
  position: number
  code: string
  title: string
  body: string
  answer: number | null
  is_correct: boolean | null
  answered_at: string | null
}

export interface EntrySheet {
  required_correct: number
  correct_count: number
  answered_count: number
  total_count: number
  qualified: boolean
  grace_over: boolean
  grace_ends_at: string | null
  can_claim_start: boolean
  draft_order: number | null
  retries_used: number
  retries_left: number
  questions: EntryAttempt[]
}

export interface EntryAnswerResult extends EntrySheet {
  is_correct: boolean
}

// ---- map design -----------------------------------------------------------

export type NeighborhoodTheme =
  | 'water'
  | 'fire'
  | 'lightning'
  | 'history'
  | 'sport'
  | 'knowledge'
  | 'unbuilt'
  | 'tribal'
  | 'soil'

export type RoadStyle = 'straight' | 'curved' | 'dashed'

export type NodeLevel = 'spawn' | 'easy' | 'medium' | 'hard' | 'toll'

export interface BalanceEvent {
  id: number
  delta: number
  balance_after: number
  reason: string
  reason_label: string
  detail: string
  created_at: string
}

export interface LevelConfigRow {
  level: NodeLevel
  entry_cost: number
  capacity: number
}

export interface Neighborhood {
  index: number
  name: string
  theme: NeighborhoodTheme
  color: string
}

export interface NodeDesign {
  code: string
  level: NodeLevel
  capacity: 1 | 2 | 3
  /** A Designer's pin; empty means the renderer chooses. */
  archetype: string
}

export interface MapDesign {
  road_style: RoadStyle
  tint_strength: number
  halo_strength: number
  neighborhoods: Neighborhood[]
  nodes: NodeDesign[]
}

export interface MapDesignPatch {
  road_style?: RoadStyle
  tint_strength?: number
  halo_strength?: number
  neighborhoods?: Array<Partial<Neighborhood> & { index: number }>
}

export interface NodeDesignPatch {
  level?: NodeLevel
  archetype?: string
}

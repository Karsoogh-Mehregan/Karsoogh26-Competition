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

export type MinesweeperDifficulty = 'easy' | 'medium' | 'hard'

export type MinesweeperStatus = 'in_progress' | 'won' | 'lost'

/** Unrevealed cell while the game is still in progress — no mine, no count. */
export interface MinesweeperHiddenCell {
  revealed: false
  flagged: boolean
}

/** Revealed cell while the game is still in progress — count only, never mine. */
export interface MinesweeperRevealedCell {
  revealed: true
  flagged: boolean
  adjacent_mines: number
}

export type MinesweeperActiveCell = MinesweeperHiddenCell | MinesweeperRevealedCell

/** Cell after won/lost — mine locations are part of the public result. */
export interface MinesweeperFinishedCell {
  revealed: boolean
  flagged: boolean
  adjacent_mines: number
  mine: boolean
}

export interface MinesweeperBoard<TCell> {
  cells: TCell[][]
}

interface MinesweeperGameBase {
  id: number
  attempt_id: number
  node: number
  difficulty: MinesweeperDifficulty
  width: number
  height: number
  mine_count: number
  score: number
  started_at: string
}

export interface MinesweeperActiveGame extends MinesweeperGameBase {
  status: 'in_progress'
  finished_at: null
  board: MinesweeperBoard<MinesweeperActiveCell>
}

export interface MinesweeperFinishedGame extends MinesweeperGameBase {
  status: 'won' | 'lost'
  finished_at: string
  board: MinesweeperBoard<MinesweeperFinishedCell>
}

export type MinesweeperGame = MinesweeperActiveGame | MinesweeperFinishedGame

export interface MinesweeperCellActionRequest {
  row: number
  col: number
}

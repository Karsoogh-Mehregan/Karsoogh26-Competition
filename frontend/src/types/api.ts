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

export interface OccupancyQuestion {
  occupancy_id: number
  expires_at: string | null
  remaining_seconds: number
  question: QuestionForTeam
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

export interface TerritoryTeam {
  code: string
  name: string
  color: string | null
}

export interface TerritoryPlayer extends TerritoryTeam {
  score: number
  has_selected_start: boolean
}

export interface TerritoryCell {
  row: number
  column: number
  value: number
  owner: TerritoryTeam | null
}

export type TerritoryAction =
  | 'starting_position'
  | 'neutral_capture'
  | 'opponent_attack'

export interface TerritoryTurn {
  number: number
  acting_player: TerritoryTeam
  target: { row: number; column: number }
  target_value: number
  action_type: TerritoryAction
  dice_result: number | null
  success: boolean
  attacker_score_change: number
  defender_score_change: number
  ownership_change: {
    previous_owner: TerritoryTeam | null
    new_owner: TerritoryTeam | null
  }
}

export interface TerritoryGame {
  id: number
  board: TerritoryCell[][]
  players: [TerritoryPlayer, TerritoryPlayer]
  active_player: TerritoryTeam | null
  turns_completed: number
  turns_remaining: number
  status: 'running' | 'finished'
  winner: TerritoryTeam | null
  is_draw: boolean
  previous_turn: TerritoryTurn | null
  created_at: string
  updated_at: string
}

export interface CreateTerritoryGameInput {
  player_one: string
  player_two: string
}

export interface PlayTerritoryTurnInput {
  row: number
  column: number
}

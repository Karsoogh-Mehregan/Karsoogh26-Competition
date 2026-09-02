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

export type CharityBagStatus = 'scheduled' | 'active' | 'resolving' | 'finished'
export type CharityBagAction = 'contribute' | 'request'

export interface CharityBagParticipation {
  team: { code: string; name: string; color: string | null }
  action: CharityBagAction
  amount: number
  stake_deducted: number
  final_payout: number
  submitted_at: string
  settled_at: string | null
}

export interface CharityBagEvent {
  id: number
  status: CharityBagStatus
  starts_at: string
  ends_at: string
  remaining_seconds: number
  can_participate: boolean
  my_participation: CharityBagParticipation | null
  participations: CharityBagParticipation[]
  total_contributed: number | null
  total_requested: number | null
  charity_succeeded: boolean | null
  settlement_started_at: string | null
  settled_at: string | null
}

export interface EnterCharityBagInput {
  action: CharityBagAction
  amount: number
}

export interface CreateCharityBagInput {
  starts_at?: string
  ends_at?: string
  duration_seconds?: number
}

export type CentipedeStatus = 'waiting_for_players' | 'active' | 'finished'
export type CentipedeAction = 'take' | 'continue'

export interface CentipedePlayer {
  code: string
  name: string
  color: string | null
  position: 1 | 2
  current_reward: number
  final_payout: number
}

export interface CentipedeDecision {
  sequence: number
  round_number: number
  actor: { code: string; name: string; color: string | null }
  action: CentipedeAction
  displayed_reward: number
  created_at: string
}

export interface CentipedeGame {
  id: number
  players: [CentipedePlayer, CentipedePlayer]
  round_number: number
  active_player: { code: string; name: string; color: string | null } | null
  actions_completed: number
  status: CentipedeStatus
  winner: { code: string; name: string; color: string | null } | null
  history: CentipedeDecision[]
  finished_at: string | null
  created_at: string
  updated_at: string
}

export interface CreateCentipedeGameInput {
  player_one: string
  player_two: string
}

export interface PlayCentipedeActionInput {
  action: CentipedeAction
}

export type OlympicsMiniGame = 'coin_near_wall' | 'marble_target'
export type OlympicsStatus = 'created' | 'active' | 'waiting_for_result' | 'tiebreak' | 'finished'
export type OlympicsOutcome = 'player_one' | 'player_two' | 'tie'

export interface OlympicsScoringZone {
  code: string
  label: string
  score: number
}

export interface OlympicsPlayer {
  code: string
  name: string
  color: string | null
  position: 1 | 2
}

export interface OlympicsAttempt {
  value: string | number
  score: number
}

export interface OlympicsResult {
  request_id: string
  round_number: number
  player_one_attempts: OlympicsAttempt[]
  player_two_attempts: OlympicsAttempt[]
  player_one_total: number | null
  player_two_total: number | null
  player_one_best_distance: string | null
  player_two_best_distance: string | null
  outcome: OlympicsOutcome
  recorded_by: string
  created_at: string
}

export interface OlympicsMatch {
  id: number
  mini_game: OlympicsMiniGame
  players: [OlympicsPlayer, OlympicsPlayer]
  scoring_zones: OlympicsScoringZone[]
  status: OlympicsStatus
  tiebreak_occurred: boolean
  winner: { code: string; name: string; color: string | null } | null
  results: OlympicsResult[]
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export interface CreateOlympicsMatchInput {
  mini_game: OlympicsMiniGame
  player_one: string
  player_two: string
  scoring_zones?: OlympicsScoringZone[]
}

export interface RecordOlympicsResultInput {
  request_id: string
  winner?: string | null
  is_tie?: boolean
  player_one_best_distance?: string | null
  player_two_best_distance?: string | null
  player_one_attempts?: Array<string | number>
  player_two_attempts?: Array<string | number>
}

export interface Holding {
  id: number
  node_code: string
  node_name: string
  level: string
  slot: number
  floor: number | null
  grade: number | null
  is_spawn: boolean
  source: 'attempt' | 'item'
}

export interface Team {
  code: string
  name: string
  balance: number | null
  color: string | null
  holdings: Holding[]
  /** Toll node codes this team has won Minesweeper on. Not holdings. */
  cleared_tolls: string[]
  active_tolls: string[]
}

export interface Me {
  id: number
  username: string
  is_staff: boolean
  is_mentor: boolean
  is_game_god: boolean
  is_announcer: boolean
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

export interface SubmissionQuestion {
  code: string
  title: string
  body: string
  answer_type: AnswerType
  answer_key: string | null
  attachment_url: string | null
}

export interface SubmissionDetail {
  id: number
  submitted_at: string
  submitted_by: number
  body: string
  file_url: string | null
  file_name: string | null
  team_code: string
  team_name: string
  node_code: string
  level: string
  floor: number | null
  grade: number | null
  points: number
  question: SubmissionQuestion
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
export type CentipedeAction = 'produce' | 'split' | 'steal' | 'preserve' | 'take' | 'continue'

export interface CentipedePlayer {
  has_chosen: boolean
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
  rules_version: number
  pot: number
  production_rounds: number
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
  round_number: number
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

export interface OlympicsPlayerRun {
  team: { code: string; name: string; color: string | null }
  round_number: number
  attempts: number[]
  best_distance: string | null
  completed_at: string
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
  player_runs: OlympicsPlayerRun[]
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

export interface SubmitOlympicsPlayerRunInput {
  round_number: number
  attempts?: number[]
  best_distance?: string | null
}

export interface AuctionBid { sequence: number; team: TerritoryTeam; amount: number; created_at: string }
export interface AuctionPair {
  id: number; team_one: TerritoryTeam; team_two: TerritoryTeam | null; rank_one: number; rank_two: number | null
  team_one_bid: number; team_two_bid: number; highest_bid: number; highest_bidder: TerritoryTeam | null
  winner: TerritoryTeam | null; status: 'active' | 'finished'; automatic_award: boolean; settled_at: string | null; bids: AuctionBid[]
}
export interface AuctionEvent {
  id: number; status: 'scheduled' | 'active' | 'finished' | 'cancelled'; reward: number; opening_bid: number
  duration_seconds: number; ranking_snapshot: Array<{ rank: number; code: string; name: string; balance: number }>
  starts_at: string; ends_at: string; remaining_seconds: number; settled_at: string | null; pairs: AuctionPair[]
}

export type WheelPrizeType = 'glorium' | 'merchandise' | 'grand_prize'
export interface WheelPrizeView { code: string; prize_type: WheelPrizeType; display_name: string; glorium_amount: number; available: boolean; stock: number | null; weight?: number }
export interface WheelSpin { id: number; request_id: string; team: TerritoryTeam; spin_cost: number; prize_type: WheelPrizeType; prize_name: string; glorium_payout: number; delivery_status: 'not_applicable' | 'pending' | 'delivered'; created_at: string; delivered_at: string | null }
export interface WheelEvent { id: number; status: 'scheduled' | 'active' | 'grand_prize_claimed' | 'finished' | 'cancelled'; spin_cost: number; total_collected: number; grand_prize_winner: TerritoryTeam | null; spins_available: boolean; prizes: WheelPrizeView[]; spins: WheelSpin[]; started_at: string | null; finished_at: string | null }
export interface WheelPrizeInput { code: string; prize_type: WheelPrizeType; display_name: string; glorium_amount?: number; weight: number; stock?: number | null; reward_data?: Record<string, unknown> }

export interface PigRoll { number: number; dice_result: number; amount_added: number; pot_after: number; created_at: string }
export interface PigGame { id: number; event_id: number; team: TerritoryTeam; entry_fee: number; max_pot: number; pot: number; rolls_count: number; status: 'active' | 'finished_cashed_out' | 'finished_rolled_one' | 'finished_max_pot'; final_payout: number; started_at: string; finished_at: string | null; rolls: PigRoll[] }
export interface PigEvent { id: number; status: 'active' | 'finished'; entry_fee: number; max_pot: number; created_at: string; finished_at: string | null; games: PigGame[] }

export type EventCode = 'territory_control' | 'charity_bag' | 'centipede' | 'olympics_coin' | 'olympics_marble' | 'limited_auction' | 'prize_wheel' | 'pig'
export interface EventConfiguration {
  code: EventCode
  label: string
  enabled: boolean
  duration_seconds: number | null
  settings: Record<string, unknown>
  supports_matchmaking: boolean
  has_time_limit: boolean
  updated_at: string
}
export interface MatchmakingTicket {
  id: number
  event_code: EventCode
  team: TerritoryTeam
  status: 'waiting' | 'matched' | 'cancelled'
  matched_team: TerritoryTeam | null
  match_id: number | null
  match_path: string | null
  created_at: string
  matched_at: string | null
  dismissed_at: string | null
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

// ---- notifications --------------------------------------------------------

export type MessageStatus = 'draft' | 'sent'
/** A whole category of recipients. Composes with explicit team/person picks. */
export type AudienceScope = 'all' | 'teams' | 'mentors' | 'designers'

export interface InboxItem {
  id: number
  title: string
  body: string
  excerpt: string
  sender: string
  sent_at: string | null
  created_at: string
  is_read: boolean
  read_at: string | null
}

export interface Inbox {
  unread: number
  total: number
  results: InboxItem[]
}

export interface ReadResult {
  marked: number
  unread: number
}

export interface AudienceChoice {
  value: AudienceScope
  label: string
}

export interface AudienceUser {
  id: number
  username: string
  label: string
  team_code: string | null
}

export interface AudienceOptions {
  choices: AudienceChoice[]
  teams: { code: string; name: string }[]
  users: AudienceUser[]
}

export interface Message {
  id: number
  status: MessageStatus
  title: string
  body: string
  excerpt: string
  scopes: AudienceScope[]
  /** Team codes. */
  teams: string[]
  /** User ids. */
  users: number[]
  audience_label: string
  sender: string
  created_at: string
  updated_at: string
  sent_at: string | null
  recipient_count: number
  read_count: number
}

/** What the composer submits. `send: true` writes and delivers in one call. */
export interface MessageDraft {
  title: string
  body: string
  scopes: AudienceScope[]
  teams: string[]
  users: number[]
  send?: boolean
}

/** Just the audience, for the composer's live "this would reach N people". */
export interface AudienceSelection {
  scopes: AudienceScope[]
  teams: string[]
  users: number[]
}

export interface AudiencePreview {
  count: number
  label: string
}

/** One delivery, from the sender's side. */
export interface Recipient {
  id: number
  user_id: number
  username: string
  label: string
  team_code: string | null
  team_name: string | null
  is_read: boolean
  read_at: string | null
}

export interface MessageRecipients {
  delivered: number
  read: number
  unread: number
  recipients: Recipient[]
}

export interface SendResult {
  message: Message
  delivered: number
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

export type ItemType = 'fake_document' | 'gel' | 'gilari_100'

export interface TeamItem {
  item_type: ItemType
  quantity: number
  display_name: string
}

export interface UseItemPayload {
  item_type: ItemType
  node_code?: string
}

export interface UseItemResult {
  detail: string
}

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
  /** Whether this node has an enabled minesweeper board behind it. */
  minesweeper: boolean
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

// ---- minesweeper ---------------------------------------------------------

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
  game_id: number
  attempt_id: number
  node: string
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

export interface MinesweeperEntry {
  entry: string
  node: string
}

export interface MinesweeperCellActionRequest {
  row: number
  col: number
}

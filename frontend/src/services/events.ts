import { get, patch, post } from '@/lib/http'
import type {
  CentipedeGame,
  CharityBagEvent,
  CreateCentipedeGameInput,
  CreateCharityBagInput,
  CreateTerritoryGameInput,
  EnterCharityBagInput,
  PlayCentipedeActionInput,
  PlayTerritoryTurnInput,
  CreateOlympicsMatchInput,
  OlympicsMatch,
  RecordOlympicsResultInput,
  SubmitOlympicsPlayerRunInput,
  TerritoryGame,
  AuctionEvent,
  PigEvent,
  PigGame,
  WheelEvent,
  WheelPrizeInput,
  WheelSpin,
  EventCode,
  EventConfiguration,
  MatchmakingTicket,
} from '@/types/api'

const GAMES_PATH = '/events/territory-control/games/'

export function listTerritoryGames(signal?: AbortSignal): Promise<TerritoryGame[]> {
  return get<TerritoryGame[]>(GAMES_PATH, signal)
}

export function getTerritoryGame(gameId: number, signal?: AbortSignal): Promise<TerritoryGame> {
  return get<TerritoryGame>(`${GAMES_PATH}${gameId}/`, signal)
}

export function createTerritoryGame(input: CreateTerritoryGameInput): Promise<TerritoryGame> {
  return post<TerritoryGame>(GAMES_PATH, input)
}

export function playTerritoryTurn(
  gameId: number,
  input: PlayTerritoryTurnInput,
): Promise<TerritoryGame> {
  return post<TerritoryGame>(`${GAMES_PATH}${gameId}/turns/`, input)
}

const CHARITY_PATH = '/events/charity-bag/instances/'

export function listCharityBags(signal?: AbortSignal): Promise<CharityBagEvent[]> {
  return get<CharityBagEvent[]>(CHARITY_PATH, signal)
}

export function getCharityBag(eventId: number, signal?: AbortSignal): Promise<CharityBagEvent> {
  return get<CharityBagEvent>(`${CHARITY_PATH}${eventId}/`, signal)
}

export function createCharityBag(input: CreateCharityBagInput): Promise<CharityBagEvent> {
  return post<CharityBagEvent>(CHARITY_PATH, input)
}

export function enterCharityBag(
  eventId: number,
  input: EnterCharityBagInput,
): Promise<CharityBagEvent> {
  return post<CharityBagEvent>(`${CHARITY_PATH}${eventId}/participate/`, input)
}

const CENTIPEDE_PATH = '/events/centipede/games/'

export function listCentipedeGames(signal?: AbortSignal): Promise<CentipedeGame[]> {
  return get<CentipedeGame[]>(CENTIPEDE_PATH, signal)
}

export function getCentipedeGame(gameId: number, signal?: AbortSignal): Promise<CentipedeGame> {
  return get<CentipedeGame>(`${CENTIPEDE_PATH}${gameId}/`, signal)
}

export function createCentipedeGame(input: CreateCentipedeGameInput): Promise<CentipedeGame> {
  return post<CentipedeGame>(CENTIPEDE_PATH, input)
}

export function playCentipedeAction(
  gameId: number,
  input: PlayCentipedeActionInput,
): Promise<CentipedeGame> {
  return post<CentipedeGame>(`${CENTIPEDE_PATH}${gameId}/actions/`, input)
}

const OLYMPICS_PATH = '/events/olympics/matches/'

export function listOlympicsMatches(signal?: AbortSignal): Promise<OlympicsMatch[]> {
  return get<OlympicsMatch[]>(OLYMPICS_PATH, signal)
}

export function getOlympicsMatch(matchId: number, signal?: AbortSignal): Promise<OlympicsMatch> {
  return get<OlympicsMatch>(`${OLYMPICS_PATH}${matchId}/`, signal)
}

export function createOlympicsMatch(input: CreateOlympicsMatchInput): Promise<OlympicsMatch> {
  return post<OlympicsMatch>(OLYMPICS_PATH, input)
}

export function startOlympicsMatch(matchId: number): Promise<OlympicsMatch> {
  return post<OlympicsMatch>(`${OLYMPICS_PATH}${matchId}/start/`, {})
}

export function recordOlympicsResult(
  matchId: number,
  input: RecordOlympicsResultInput,
): Promise<OlympicsMatch> {
  return post<OlympicsMatch>(`${OLYMPICS_PATH}${matchId}/results/`, input)
}

export function submitOlympicsPlayerRun(
  matchId: number,
  input: SubmitOlympicsPlayerRunInput,
): Promise<OlympicsMatch> {
  return post<OlympicsMatch>(`${OLYMPICS_PATH}${matchId}/player-run/`, input)
}

const AUCTION_PATH = '/events/limited-auction/events/'
export const listAuctionEvents = (signal?: AbortSignal) => get<AuctionEvent[]>(AUCTION_PATH, signal)
export const createAuctionEvent = (duration_seconds: number) => post<AuctionEvent>(AUCTION_PATH, { duration_seconds })
export const placeAuctionBid = (pairId: number, amount: number, request_id: string) => post<AuctionEvent>(`/events/limited-auction/pairs/${pairId}/bids/`, { amount, request_id })
export const resolveAuctionEvent = (eventId: number) => post<AuctionEvent>(`${AUCTION_PATH}${eventId}/resolve/`, {})

const WHEEL_PATH = '/events/prize-wheel/events/'
export const listWheelEvents = (signal?: AbortSignal) => get<WheelEvent[]>(WHEEL_PATH, signal)
export const createWheelEvent = (spin_cost: number, prizes: WheelPrizeInput[]) => post<WheelEvent>(WHEEL_PATH, { spin_cost, prizes })
export const startWheelEvent = (eventId: number) => post<WheelEvent>(`${WHEEL_PATH}${eventId}/start/`, {})
export const stopWheelEvent = (eventId: number, cancelled = false) => post<WheelEvent>(`${WHEEL_PATH}${eventId}/stop/`, { cancelled })
export const spinWheel = (eventId: number, request_id: string) => post<WheelSpin>(`${WHEEL_PATH}${eventId}/spins/`, { request_id })
export const deliverWheelSpin = (spinId: number) => post<WheelSpin>(`/events/prize-wheel/spins/${spinId}/deliver/`, {})

const PIG_PATH = '/events/pig/events/'
export const listPigEvents = (signal?: AbortSignal) => get<PigEvent[]>(PIG_PATH, signal)
export const createPigEvent = (max_pot: number) => post<PigEvent>(PIG_PATH, { max_pot })
export const finishPigEvent = (eventId: number) => post<PigEvent>(`${PIG_PATH}${eventId}/finish/`, {})
export const startPigGame = (eventId: number) => post<PigGame>(`${PIG_PATH}${eventId}/games/`, {})
export const playPigAction = (gameId: number, action: 'roll' | 'cash_out', request_id: string) => post<PigGame>(`/events/pig/games/${gameId}/actions/`, { action, request_id })

const CATALOG_PATH = '/events/catalog/'
export const listEventConfigurations = (signal?: AbortSignal) => get<EventConfiguration[]>(CATALOG_PATH, signal)
export const updateEventConfiguration = (code: EventCode, input: Partial<Pick<EventConfiguration, 'enabled' | 'duration_seconds' | 'settings'>>) => patch<EventConfiguration>(`${CATALOG_PATH}${code}/`, input)
export const listMatchmakingTickets = (signal?: AbortSignal) => get<MatchmakingTicket[]>('/events/matchmaking/', signal)
export const joinMatchmaking = (code: EventCode) => post<MatchmakingTicket>(`/events/matchmaking/${code}/join/`, {})
export const cancelMatchmaking = (code: EventCode) => post<MatchmakingTicket>(`/events/matchmaking/${code}/cancel/`, {})
export const dismissMatchmaking = (ticketId: number) => post<MatchmakingTicket>(`/events/matchmaking/${ticketId}/dismiss/`, {})

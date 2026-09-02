import { get, post } from '@/lib/http'
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
  TerritoryGame,
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

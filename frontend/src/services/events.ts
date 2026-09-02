import { get, post } from '@/lib/http'
import type {
  CharityBagEvent,
  CreateCharityBagInput,
  CreateTerritoryGameInput,
  EnterCharityBagInput,
  PlayTerritoryTurnInput,
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

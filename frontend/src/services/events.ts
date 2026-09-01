import { get, post } from '@/lib/http'
import type {
  CreateTerritoryGameInput,
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

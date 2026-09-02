import { get, post } from '@/lib/http'
import type {
  CreateMinesweeperGameRequest,
  MinesweeperCellActionRequest,
  MinesweeperDifficulty,
  MinesweeperGame,
} from '@/types/api'

export function createGame(difficulty: MinesweeperDifficulty): Promise<MinesweeperGame> {
  const body: CreateMinesweeperGameRequest = { difficulty }
  return post<MinesweeperGame>('/minesweeper/games/', body)
}

export function getGame(gameId: number, signal?: AbortSignal): Promise<MinesweeperGame> {
  return get<MinesweeperGame>(`/minesweeper/games/${gameId}/`, signal)
}

export function revealCell(gameId: number, row: number, col: number): Promise<MinesweeperGame> {
  const body: MinesweeperCellActionRequest = { row, col }
  return post<MinesweeperGame>(`/minesweeper/games/${gameId}/reveal/`, body)
}

export function toggleFlag(gameId: number, row: number, col: number): Promise<MinesweeperGame> {
  const body: MinesweeperCellActionRequest = { row, col }
  return post<MinesweeperGame>(`/minesweeper/games/${gameId}/flag/`, body)
}

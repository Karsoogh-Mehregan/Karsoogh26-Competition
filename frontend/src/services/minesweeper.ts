import { get, post } from '@/lib/http'
import type { MinesweeperCellActionRequest, MinesweeperGame } from '@/types/api'

export function joinGame(gameId: number): Promise<MinesweeperGame> {
  return post<MinesweeperGame>(`/minesweeper/games/${gameId}/join/`, {})
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

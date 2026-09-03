import { get, post } from '@/lib/http'
import type { MinesweeperCellActionRequest, MinesweeperGame } from '@/types/api'

export function startPlay(nodeId: number): Promise<MinesweeperGame> {
  return post<MinesweeperGame>(`/minesweeper/nodes/${nodeId}/start/`, {})
}

export function getAttempt(attemptId: number, signal?: AbortSignal): Promise<MinesweeperGame> {
  return get<MinesweeperGame>(`/minesweeper/attempts/${attemptId}/`, signal)
}

export function revealCell(
  attemptId: number,
  row: number,
  col: number,
): Promise<MinesweeperGame> {
  const body: MinesweeperCellActionRequest = { row, col }
  return post<MinesweeperGame>(`/minesweeper/attempts/${attemptId}/reveal/`, body)
}

export function toggleFlag(
  attemptId: number,
  row: number,
  col: number,
): Promise<MinesweeperGame> {
  const body: MinesweeperCellActionRequest = { row, col }
  return post<MinesweeperGame>(`/minesweeper/attempts/${attemptId}/flag/`, body)
}

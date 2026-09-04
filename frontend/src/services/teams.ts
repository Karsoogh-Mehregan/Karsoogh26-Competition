import { get, post } from '@/lib/http'
import type { BalanceEvent, Board, LeaderboardRow, Team } from '@/types/api'

export function listTeams(board: Board, signal?: AbortSignal): Promise<Team[]> {
  return get<Team[]>(`/teams/?board=${board}`, signal)
}

export function listBalanceEvents(teamCode: string, signal?: AbortSignal): Promise<BalanceEvent[]> {
  return get<BalanceEvent[]>(`/teams/${encodeURIComponent(teamCode)}/balance-events/`, signal)
}

export function claimStart(teamCode: string, node: string): Promise<Team> {
  return post<Team>(`/teams/${encodeURIComponent(teamCode)}/claim-start/`, { node })
}

export function getLeaderboard(board: Board, signal?: AbortSignal): Promise<LeaderboardRow[]> {
  return get<LeaderboardRow[]>(`/leaderboard/?board=${board}`, signal)
}

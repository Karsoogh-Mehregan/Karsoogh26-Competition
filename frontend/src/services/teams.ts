import { get, post } from '@/lib/http'
import type { BalanceEvent, LeaderboardRow, Team } from '@/types/api'

export function listTeams(signal?: AbortSignal): Promise<Team[]> {
  return get<Team[]>('/teams/', signal)
}

export function listBalanceEvents(teamCode: string, signal?: AbortSignal): Promise<BalanceEvent[]> {
  return get<BalanceEvent[]>(`/teams/${encodeURIComponent(teamCode)}/balance-events/`, signal)
}

export function claimStart(teamCode: string, node: string): Promise<Team> {
  return post<Team>(`/teams/${encodeURIComponent(teamCode)}/claim-start/`, { node })
}

export function getLeaderboard(signal?: AbortSignal): Promise<LeaderboardRow[]> {
  return get<LeaderboardRow[]>('/leaderboard/', signal)
}

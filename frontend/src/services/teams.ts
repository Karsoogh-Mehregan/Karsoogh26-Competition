import { get, post } from '@/lib/http'
import type { Team } from '@/types/api'

export function listTeams(signal?: AbortSignal): Promise<Team[]> {
  return get<Team[]>('/teams/', signal)
}

export function claimStart(teamCode: string, node: string): Promise<Team> {
  return post<Team>(`/teams/${encodeURIComponent(teamCode)}/claim-start/`, { node })
}

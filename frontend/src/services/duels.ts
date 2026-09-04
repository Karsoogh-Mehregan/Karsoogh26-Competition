import { get, post } from '@/lib/http'
import type { Duel, DuelBoard, DuelTarget } from '@/types/api'

/** The whole duel page in one call: live duel, history, and what a judge holds. */
export function getDuelBoard(signal?: AbortSignal): Promise<DuelBoard> {
  return get<DuelBoard>('/duels/', signal)
}

export function getDuelTargets(signal?: AbortSignal): Promise<DuelTarget[]> {
  return get<DuelTarget[]>('/duels/targets/', signal)
}

export function requestDuel(occupancyId: number): Promise<Duel> {
  return post<Duel>('/duels/', { occupancy: occupancyId })
}

export function resolveDuel(duelId: number, winnerCode: string): Promise<Duel> {
  return post<Duel>(`/duels/${duelId}/resolve/`, { winner: winnerCode })
}

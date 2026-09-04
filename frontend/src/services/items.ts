import { get, post } from '@/lib/http'
import type { TeamItem, UseItemPayload, UseItemResult } from '@/types/api'

export function listItems(signal?: AbortSignal): Promise<TeamItem[]> {
  return get<TeamItem[]>('/teams/me/items/', signal)
}

export function useItem(payload: UseItemPayload): Promise<UseItemResult> {
  return post<UseItemResult>('/teams/me/items/use/', payload)
}

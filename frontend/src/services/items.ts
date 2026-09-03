import { get } from '@/lib/http'
import type { TeamItem } from '@/types/api'

export function listItems(signal?: AbortSignal): Promise<TeamItem[]> {
  return get<TeamItem[]>('/teams/me/items/', signal)
}

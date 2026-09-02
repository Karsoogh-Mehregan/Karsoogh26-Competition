import { get } from '@/lib/http'
import type { ActiveAttempt } from '@/types/api'

export function listAttempts(teamCode: string, signal?: AbortSignal): Promise<ActiveAttempt[]> {
  return get<ActiveAttempt[]>(`/teams/${encodeURIComponent(teamCode)}/attempts/`, signal)
}

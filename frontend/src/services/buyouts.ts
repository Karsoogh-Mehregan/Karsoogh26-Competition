import { get, post } from '@/lib/http'
import type { BuyoutResult, BuyoutTarget } from '@/types/api'

export function getBuyoutTargets(signal?: AbortSignal): Promise<BuyoutTarget[]> {
  return get<BuyoutTarget[]>('/buyouts/targets/', signal)
}

export function buyOut(occupancyId: number): Promise<BuyoutResult> {
  return post<BuyoutResult>('/buyouts/', { occupancy: occupancyId })
}

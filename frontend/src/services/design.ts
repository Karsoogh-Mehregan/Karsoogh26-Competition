import { get, patch } from '@/lib/http'
import type { MapDesign, MapDesignPatch, NodeDesign, NodeDesignPatch } from '@/types/api'

export function getMapDesign(signal?: AbortSignal): Promise<MapDesign> {
  return get<MapDesign>('/map/design/', signal)
}

export function updateMapDesign(changes: MapDesignPatch): Promise<MapDesign> {
  return patch<MapDesign>('/map/design/', changes)
}

export function updateNodeDesign(nodeCode: string, changes: NodeDesignPatch): Promise<NodeDesign> {
  return patch<NodeDesign>(`/map/nodes/${encodeURIComponent(nodeCode)}/`, changes)
}

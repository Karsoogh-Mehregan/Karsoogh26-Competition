import { get, patch } from '@/lib/http'
import type { Board, MapDesign, MapDesignPatch, NodeDesign, NodeDesignPatch } from '@/types/api'

export function getMapDesign(board: Board, signal?: AbortSignal): Promise<MapDesign> {
  return get<MapDesign>(`/map/design/?board=${board}`, signal)
}

export function updateMapDesign(changes: MapDesignPatch): Promise<MapDesign> {
  return patch<MapDesign>('/map/design/', changes)
}

/** Applies to every board's copy of the node — the two maps must not drift. */
export function updateNodeDesign(nodeCode: string, changes: NodeDesignPatch): Promise<NodeDesign> {
  return patch<NodeDesign>(`/map/nodes/${encodeURIComponent(nodeCode)}/`, changes)
}

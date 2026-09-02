import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Which node the detail panel is looking at, and what the player may do with
 * it.
 *
 * The intent is decided on the map, where the adjacency and entry-sheet rules
 * already live, and carried here rather than re-derived in the panel — two
 * copies of "may this team take this node" is exactly the kind of duplication
 * that drifts apart mid-contest.
 */
export type InspectIntent =
  /** A free, reachable node: reserve it and take its question. */
  | 'reserve'
  /** The team holds no node yet and this is its own colour's spawn. */
  | 'claim_start'
  /** The team already has an open question here. */
  | 'solve'
  /** A spawn the team cannot take until the entry sheet is cleared. */
  | 'entry_gate'
  /** Look, but nothing to do. */
  | 'view'

export interface Inspection {
  nodeCode: string
  intent: InspectIntent
  /** Occupancy id, when the intent is `solve`. */
  occupancyId: number | null
}

export const useInspectorStore = defineStore('inspector', () => {
  const inspection = ref<Inspection | null>(null)

  function inspect(nodeCode: string, intent: InspectIntent, occupancyId: number | null = null) {
    inspection.value = { nodeCode, intent, occupancyId }
  }

  function clear() {
    inspection.value = null
  }

  return { inspection, inspect, clear }
})

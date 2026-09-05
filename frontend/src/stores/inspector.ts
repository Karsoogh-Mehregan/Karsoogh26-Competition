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
 *
 * It is a *snapshot*, though, and the rules under it keep moving: clearing the
 * entry sheet turns a spawn from `entry_gate` into `claim_start`, a neighbour's
 * grade opens a road, a duel loses a seat. `GraphView` therefore re-derives the
 * intent for whichever node is being inspected and writes it back here, so the
 * panel never offers the move that was legal when the node was clicked.
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
  /**
   * A spawn whose entry sheet is spent: every question answered, every retry
   * used, still short. Nothing to click — only the grace window opens this.
   */
  | 'entry_locked'
  /** A gateway node: it is played as minesweeper instead of answered. */
  | 'minesweeper'
  /** Look, but nothing to do. */
  | 'view'

/**
 * A union, not a struct with a nullable field: `solve` without the occupancy it
 * means to solve is not a state the panel can act on, so it is not a state the
 * type allows. The only producer is `GraphView.vue`, which is plain untyped JS,
 * hence the runtime check as well.
 */
export type Inspection =
  | { nodeCode: string; intent: 'solve'; occupancyId: number }
  | { nodeCode: string; intent: Exclude<InspectIntent, 'solve'>; occupancyId: null }

export const useInspectorStore = defineStore('inspector', () => {
  const inspection = ref<Inspection | null>(null)

  function inspect(nodeCode: string, intent: 'solve', occupancyId: number): void
  function inspect(
    nodeCode: string,
    intent: Exclude<InspectIntent, 'solve'>,
    occupancyId?: null,
  ): void
  function inspect(nodeCode: string, intent: InspectIntent, occupancyId: number | null = null) {
    if (intent !== 'solve') {
      inspection.value = { nodeCode, intent, occupancyId: null }
      return
    }
    if (occupancyId == null) {
      throw new Error(`inspect("${nodeCode}", "solve") needs an occupancyId.`)
    }
    inspection.value = { nodeCode, intent, occupancyId }
  }

  function clear() {
    inspection.value = null
  }

  return { inspection, inspect, clear }
})

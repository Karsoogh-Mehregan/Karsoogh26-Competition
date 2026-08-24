import { ref, computed } from 'vue'
import graphData from '../data/graph_data.json'

// Module-level singleton state so every component that calls useGraph()
// shares the exact same reactive traversal state.
let singleton = null

function createGraphState() {
  const nodes = graphData.nodes
  const edges = graphData.edges

  const nodeById = new Map(nodes.map((n) => [n.id, n]))

  // adjacency list: nodeId -> Set of neighbor nodeIds (direction-agnostic for connectivity)
  const adjacency = new Map()
  for (const n of nodes) adjacency.set(n.id, new Set())
  for (const e of edges) {
    adjacency.get(e.source)?.add(e.target)
    adjacency.get(e.target)?.add(e.source)
  }

  // Only pink diamonds (outward-arrow entry points) can start a traversal.
  // Gray squares are outer-to-inner gateways, not start nodes.
  const startEligibleIds = new Set(
    nodes.filter((n) => n.shape === 'diamond').map((n) => n.id)
  )

  // --- Reactive state ---
  // path: ordered list of selected node ids (the traversal history)
  const path = ref([])

  const currentNodeId = computed(() => path.value[path.value.length - 1] ?? null)

  const hasStarted = computed(() => path.value.length > 0)

  // Which node ids are currently clickable
  const selectableIds = computed(() => {
    if (!hasStarted.value) {
      return startEligibleIds
    }
    const cur = currentNodeId.value
    const neighbors = adjacency.get(cur) ?? new Set()
    // neighbors that are not already visited are selectable; the current node itself is excluded
    const result = new Set()
    for (const nb of neighbors) {
      result.add(nb)
    }
    return result
  })

  function isSelectable(nodeId) {
    return selectableIds.value.has(nodeId)
  }

  function isSelected(nodeId) {
    return path.value.includes(nodeId)
  }

  function isCurrent(nodeId) {
    return currentNodeId.value === nodeId
  }

  function selectNode(nodeId) {
    if (!isSelectable(nodeId)) return false
    path.value.push(nodeId)
    return true
  }

  function reset() {
    path.value = []
  }

  function undoLast() {
    if (path.value.length > 0) path.value.pop()
  }

  return {
    nodes,
    edges,
    nodeById,
    adjacency,
    path,
    currentNodeId,
    hasStarted,
    selectableIds,
    isSelectable,
    isSelected,
    isCurrent,
    selectNode,
    reset,
    undoLast,
  }
}

export function useGraph() {
  if (!singleton) {
    singleton = createGraphState()
  }
  return singleton
}

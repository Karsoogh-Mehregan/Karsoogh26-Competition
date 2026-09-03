/**
 * The map's look, resolved per node.
 *
 * One query (`GET /api/map/design/`) answers three questions the renderer and
 * the map both ask about every node: which tier is it (and so how many seats),
 * which neighbourhood is it in (and so which palette), and which building does
 * it wear. The first two are cheap lookups; the third is the adjacency-aware
 * assignment in `lib/mapArchetypes.ts`, memoised on the set of Designer pins so
 * it runs once per design change, not once per node.
 *
 * Before the query answers, everything falls back to the map JSON's own type,
 * so the map never blanks while waiting.
 */
import { computed } from 'vue'

import { useGraph } from '@/composables/useGraph.js'
import {
  archetypeByKey,
  fallbackArchetypeFor,
  type Archetype,
} from '@/lib/house/archetypes'
import type { NodeMeta } from '@/lib/house/spec'
import { DEFAULT_THEME, THEMES, type Theme } from '@/lib/house/themes'
import { assignArchetypes } from '@/lib/mapArchetypes'
import { LEVEL_CAPACITY, levelForType, type Level } from '@/lib/mapLevels'
import { SECTOR_COUNT, sectorOf, type PolarNode } from '@/lib/mapNeighborhoods'
import { useMeQuery } from '@/queries/auth'
import { useMapDesignQuery } from '@/queries/design'
import type { MapDesign, Neighborhood, RoadStyle } from '@/types/api'

interface MapNodeLike extends PolarNode {
  id: string
  type: string
}

/** Mirrors `DEFAULT_NEIGHBORHOODS` in the backend, for the moment before the query lands. */
const FALLBACK_NEIGHBORHOODS: Neighborhood[] = [
  { index: 0, name: 'محلهٔ آبی', theme: 'water', color: '#2f7fd6' },
  { index: 1, name: 'محلهٔ قرمز', theme: 'fire', color: '#d6412b' },
  { index: 2, name: 'محلهٔ نارنجی', theme: 'lightning', color: '#ef8f1f' },
  { index: 3, name: 'محلهٔ سبز', theme: 'history', color: '#4f9a3f' },
  { index: 4, name: 'محلهٔ زرد', theme: 'sport', color: '#e6c21c' },
  { index: 5, name: 'محلهٔ بنفش', theme: 'knowledge', color: '#7e4fc4' },
  { index: 6, name: 'محلهٔ خاکستری', theme: 'tribal', color: '#6b6b7a' },
  { index: 7, name: 'محلهٔ قهوه‌ای', theme: 'soil', color: '#9a5a2e' },
]

// The assignment is pure in (pins); cache it across every caller of this
// composable so GraphView, HousePanel and HouseCanvas share one run.
let assignmentKey = ''
let assignment: Map<string, string> = new Map()

export function useMapDesign() {
  const meQuery = useMeQuery()
  const enabled = () => meQuery.data.value != null
  const query = useMapDesignQuery(enabled)
  const { nodes, nodeById, adjacency } = useGraph()

  const design = computed<MapDesign | null>(() => query.data.value ?? null)
  const loading = computed(() => enabled() && query.isPending.value)

  const neighborhoods = computed<Neighborhood[]>(() => {
    const rows = design.value?.neighborhoods ?? []
    const byIndex = new Map(rows.map((row) => [row.index, row]))
    return Array.from(
      { length: SECTOR_COUNT },
      (_, index) => byIndex.get(index) ?? FALLBACK_NEIGHBORHOODS[index],
    )
  })

  const roadStyle = computed<RoadStyle>(() => design.value?.road_style ?? 'straight')
  /** 0..1, ready to drop into an SVG opacity. */
  const tintStrength = computed(() => (design.value?.tint_strength ?? 22) / 100)
  const haloStrength = computed(() => (design.value?.halo_strength ?? 60) / 100)

  /** code → the server's row, when it has one. */
  const nodeRows = computed(() => {
    const map = new Map<
      string,
      { level: Level; capacity: 1 | 2 | 3; archetype: string; minesweeper: boolean }
    >()
    for (const row of design.value?.nodes ?? []) {
      map.set(row.code, {
        level: row.level,
        capacity: row.capacity,
        archetype: row.archetype,
        minesweeper: row.minesweeper,
      })
    }
    return map
  })

  const pins = computed(() => {
    const map = new Map<string, string>()
    for (const [code, row] of nodeRows.value) {
      if (row.archetype) map.set(code, row.archetype)
    }
    return map
  })

  const assigned = computed(() => {
    const key = [...pins.value.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([code, archetype]) => `${code}=${archetype}`)
      .join(',')
    // Levels come from the server too, so a node moved to `toll` drops out of
    // the assignment; include them in the memo key.
    const levelKey = design.value
      ? design.value.nodes.map((row) => `${row.code}:${row.level}`).join(',')
      : 'fallback'
    const fullKey = `${levelKey}|${key}`
    if (fullKey !== assignmentKey) {
      assignment = assignArchetypes({
        nodes: nodes.map((node: MapNodeLike) => ({ id: node.id, level: levelOf(node.id, node.type) })),
        adjacency,
        pins: pins.value,
      })
      assignmentKey = fullKey
    }
    return assignment
  })

  function levelOf(code: string, fallbackType: string): Level {
    return nodeRows.value.get(code)?.level ?? levelForType(fallbackType)
  }

  function capacityOf(code: string, fallbackType: string): 1 | 2 | 3 {
    return nodeRows.value.get(code)?.capacity ?? LEVEL_CAPACITY[levelForType(fallbackType)]
  }

  /**
   * Whether a minesweeper board is actually playable here. False until the
   * query lands: the map JSON cannot know, and offering a board the API would
   * refuse is worse than offering it a moment late.
   */
  function hasMinesweeper(code: string): boolean {
    return nodeRows.value.get(code)?.minesweeper ?? false
  }

  function neighborhoodOf(node: PolarNode): Neighborhood {
    return neighborhoods.value[sectorOf(node)]
  }

  function themeOf(node: PolarNode): Theme {
    return THEMES[neighborhoodOf(node).theme] ?? DEFAULT_THEME
  }

  /** The Designer's pin on a node, or '' when the renderer is choosing. */
  function pinOf(code: string): string {
    return nodeRows.value.get(code)?.archetype ?? ''
  }

  function archetypeOf(node: MapNodeLike): Archetype {
    const level = levelOf(node.id, node.type)
    const key = assigned.value.get(node.id)
    return key ? archetypeByKey(key, level) : fallbackArchetypeFor(node.id, level)
  }

  function metaOf(node: MapNodeLike): NodeMeta {
    const neighborhood = neighborhoodOf(node)
    return {
      level: levelOf(node.id, node.type),
      capacity: capacityOf(node.id, node.type),
      archetype: archetypeOf(node),
      theme: THEMES[neighborhood.theme] ?? DEFAULT_THEME,
      neighborhoodName: neighborhood.name,
    }
  }

  function metaByCode(code: string): NodeMeta | null {
    const node = nodeById.get(code) as MapNodeLike | undefined
    return node ? metaOf(node) : null
  }

  return {
    design,
    loading,
    neighborhoods,
    roadStyle,
    tintStrength,
    haloStrength,
    sectorOf,
    levelOf,
    capacityOf,
    hasMinesweeper,
    neighborhoodOf,
    themeOf,
    pinOf,
    archetypeOf,
    metaOf,
    metaByCode,
  }
}

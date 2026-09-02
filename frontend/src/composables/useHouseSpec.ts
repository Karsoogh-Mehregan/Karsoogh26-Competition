/**
 * The inspected node, as a house.
 *
 * Everything the model needs is already on the board: the map JSON knows the
 * node's type, `GET /api/teams/` knows who sits on it. Nothing new is fetched,
 * so opening the panel costs one computed, and an SSE frame that refreshes the
 * team list flows straight through to the paint.
 */
import { computed } from 'vue'

import { useActing } from '@/composables/useActing'
import { useGraph } from '@/composables/useGraph.js'
import { buildSpec, type HouseSpec, type PaintedHolding } from '@/lib/house/spec'
import { useInspectorStore } from '@/stores/inspector'

export function useHouseSpec() {
  const inspector = useInspectorStore()
  const { teams, actingTeam } = useActing()
  const { nodeById } = useGraph()

  const inspection = computed(() => inspector.inspection)

  const node = computed(() => {
    const code = inspection.value?.nodeCode
    return code ? (nodeById.get(code) ?? null) : null
  })

  const teamNames = computed(() => new Map(teams.value.map((team) => [team.code, team.name])))

  /** Every holding sitting on the inspected node, tagged with its team. */
  const holdings = computed<PaintedHolding[]>(() => {
    const code = node.value?.id
    if (!code) return []
    const out: PaintedHolding[] = []
    for (const team of teams.value) {
      for (const holding of team.holdings) {
        if (holding.node_code !== code) continue
        out.push({ ...holding, color: team.color, team_code: team.code })
      }
    }
    return out
  })

  const spec = computed<HouseSpec | null>(() => {
    const current = node.value
    if (!current) return null
    return buildSpec(current, holdings.value, {
      ownTeamCode: actingTeam.value?.code ?? null,
      teamNames: teamNames.value,
    })
  })

  return { inspection, node, spec, holdings }
}

export type { HouseSpec }

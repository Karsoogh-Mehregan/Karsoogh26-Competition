/**
 * The description a house is built from. Everything here comes from data the
 * board already has: the map JSON gives the node's position, the design query
 * gives its level, its neighbourhood and any Designer pin, and `GET /api/teams/`
 * gives the holdings sitting on it.
 *
 * `structureKey` is the point of this file. A house is rebuilt only when its
 * *shape* changes; a team taking a floor changes only paint, and paint is a
 * material assignment, not a rebuild. Comparing this one string is how the
 * renderer tells the two apart, and it is what keeps a busy board — where
 * every grade fires an SSE frame — from rebuilding geometry on every event.
 */
import { isReservation } from '@/lib/holdings'
import { LEVEL_LABEL, type Level } from '@/lib/mapLevels'
import type { Archetype } from './archetypes'
import type { Theme } from './themes'

export type FloorStatus = 'empty' | 'reserved' | 'owned'

export interface FloorState {
  /** 1-based, and 1 is the *worst* unit — floor N is the penthouse. */
  floor: number
  status: FloorStatus
  teamCode: string | null
  teamName: string | null
  color: string | null
  grade: number | null
  isOwnTeam: boolean
  /** The seat's Occupancy id — what a duel challenge names as its target. */
  occupancyId: number | null
  /** How the seat was acquired; `duel`/`item` own a floor without a grade. */
  source: string | null
}

export interface HouseSpec {
  nodeCode: string
  nodeName: string
  level: Level
  levelLabel: string
  capacity: 1 | 2 | 3
  archetype: Archetype
  theme: Theme
  neighborhoodName: string
  floors: FloorState[]
  /** Seats with nobody in them, reserved or owned. */
  freeSlots: number
  structureKey: string
}

/** A holding as the map paints it — `Holding` plus the owning team's identity. */
export interface PaintedHolding {
  id: number
  node_code: string
  source?: string
  level: string
  slot: number
  floor: number | null
  grade: number | null
  is_spawn: boolean
  color: string | null
  team_code: string
}

/** What the design layer resolved for this node. */
export interface NodeMeta {
  level: Level
  capacity: 1 | 2 | 3
  archetype: Archetype
  theme: Theme
  neighborhoodName: string
}

function emptyFloor(floor: number): FloorState {
  return {
    floor,
    status: 'empty',
    teamCode: null,
    teamName: null,
    color: null,
    grade: null,
    isOwnTeam: false,
    occupancyId: null,
    source: null,
  }
}

/**
 * Seat the holdings on the node's floors.
 *
 * A holding with a floor owns it, however it got there: a grade, an item, or a
 * won duel. Only a *reservation* — no floor yet, because the floor is captured
 * at grading — is scaffolding, shown on the lowest seat still free, which is
 * where it would land if graded right now.
 */
export function buildSpec(
  nodeCode: string,
  meta: NodeMeta,
  holdings: PaintedHolding[],
  options: {
    nodeName?: string
    ownTeamCode?: string | null
    teamNames?: Map<string, string>
  } = {},
): HouseSpec {
  const { ownTeamCode = null, teamNames } = options
  const { level, capacity, archetype, theme } = meta

  const floors: FloorState[] = Array.from({ length: capacity }, (_, i) => emptyFloor(i + 1))

  const seat = (index: number, holding: PaintedHolding, status: FloorStatus) => {
    const slot = floors[index]
    if (!slot) return
    slot.status = status
    slot.teamCode = holding.team_code
    slot.teamName = teamNames?.get(holding.team_code) ?? holding.team_code
    slot.color = holding.color
    slot.grade = holding.grade
    slot.isOwnTeam = ownTeamCode != null && holding.team_code === ownTeamCode
    slot.occupancyId = holding.id ?? null
    slot.source = holding.source ?? null
  }

  for (const holding of holdings) {
    if (holding.floor == null) continue
    seat(holding.floor - 1, holding, 'owned')
  }

  for (const holding of holdings) {
    if (!isReservation(holding)) continue
    const index = floors.findIndex((slot) => slot.status === 'empty')
    if (index === -1) break
    seat(index, holding, 'reserved')
  }

  // A spawn is a seat with no question and no floor; it still owns its house.
  for (const holding of holdings) {
    if (!holding.is_spawn || holding.floor != null) continue
    const index = floors.findIndex((slot) => slot.status === 'empty')
    if (index === -1) break
    seat(index, holding, 'owned')
  }

  return {
    nodeCode,
    nodeName: options.nodeName || nodeCode,
    level,
    levelLabel: LEVEL_LABEL[level],
    capacity,
    archetype,
    theme,
    neighborhoodName: meta.neighborhoodName,
    floors,
    freeSlots: floors.filter((slot) => slot.status === 'empty').length,
    // Only what changes *geometry*: the building worn, the theme dressing it,
    // how many storeys, and which of them are scaffolded. A floor changing
    // hands is paint, and paint must never cost a rebuild.
    structureKey: `${archetype.key}:${theme.key}:${capacity}:${floors
      .map((slot) => (slot.status === 'reserved' ? '1' : '0'))
      .join('')}`,
  }
}

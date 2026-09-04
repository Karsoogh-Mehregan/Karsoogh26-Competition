/**
 * Which building each unpinned node wears, chosen so no two neighbours match.
 *
 * A greedy graph colouring with 26 colours: nodes are visited in a fixed order,
 * each takes the first type in its own hash-rotated preference list that none
 * of its already-decided neighbours took. The map's densest node (an L6, in a
 * K8 plus three L5s plus the centre) has degree 11, well under 26, so greedy
 * always finds one. Pins are honoured first and never moved, even if a pin
 * clashes with a neighbour — a Designer's choice wins over the tidiness rule.
 *
 * Deterministic on (node order, adjacency, pins), so every client agrees and
 * nothing is stored. Runs once per design load over 473 nodes: negligible.
 */
import { ASSIGNABLE_KEYS, hashCode } from '@/lib/house/archetypes'
import type { Level } from '@/lib/mapLevels'

export interface AssignableNode {
  id: string
  level: Level
}

export interface AssignmentInput {
  nodes: AssignableNode[]
  adjacency: ReadonlyMap<string, ReadonlySet<string>>
  /** Designer pins, node code → archetype key. */
  pins: ReadonlyMap<string, string>
}

/** The special plots never take part: they have their own fixed look. */
function isAssignable(node: AssignableNode): boolean {
  return node.level !== 'spawn' && node.level !== 'toll' && node.level !== 'center'
}

export function assignArchetypes(input: AssignmentInput): Map<string, string> {
  const result = new Map<string, string>()
  const keys = ASSIGNABLE_KEYS
  const count = keys.length

  for (const [code, key] of input.pins) {
    if (key) result.set(code, key)
  }

  const order = [...input.nodes].filter(isAssignable).sort((a, b) => a.id.localeCompare(b.id))

  for (const node of order) {
    if (result.has(node.id)) continue

    const taken = new Set<string>()
    for (const neighbour of input.adjacency.get(node.id) ?? []) {
      const key = result.get(neighbour)
      if (key) taken.add(key)
    }

    const start = hashCode(node.id) % count
    let chosen = keys[start]
    for (let offset = 0; offset < count; offset += 1) {
      const candidate = keys[(start + offset) % count]
      if (!taken.has(candidate)) {
        chosen = candidate
        break
      }
    }
    result.set(node.id, chosen)
  }

  return result
}

/**
 * What a holding *is*, decided in one place.
 *
 * The board has three kinds of seat and they were being told apart by three
 * different tests scattered across the map, which is how a duel-won floor came
 * to render as scaffolding and offer its owner a question it had already won:
 *
 * - **reservation** — the team paid for the slot and owes an answer. `floor` is
 *   null, because the floor is captured at grading, not at claiming.
 * - **owned by grade** — answered and judged. `floor` and `grade` are both set.
 * - **granted** — an item takeover, a won duel or a bought floor. `floor` is set and `grade`
 *   is null, because nothing was answered for it.
 *
 * So `grade == null` does **not** mean "reserved" — it means "no question was
 * graded here", which is equally true of a floor a team won in a duel. The
 * discriminator is `floor`, mirroring the server: `Occupancy.floor` is null
 * exactly while the seat is a reservation.
 *
 * `game.models.GRANTED_SOURCES` is the server-side twin of `GRANTED_SOURCES`
 * below; add to both when a fourth way of acquiring a floor appears.
 */

/** Seats a team was given rather than earned by answering. */
export const GRANTED_SOURCES = new Set(['item', 'duel', 'buyout'])

/** The shape both the map and the house panel read holdings through. */
interface HoldingLike {
  floor: number | null
  grade?: number | null
  is_spawn?: boolean
  source?: string
}

/** True while the team still owes an answer for this seat. */
export function isReservation(holding: HoldingLike): boolean {
  return holding.floor == null && holding.is_spawn !== true
}

/** True when the seat was granted — no question was ever answered for it. */
export function isGranted(holding: HoldingLike): boolean {
  return holding.source != null && GRANTED_SOURCES.has(holding.source)
}

/**
 * True when the seat lets the team move on to its neighbours.
 *
 * A reservation is a dead end until it is graded; a spawn starts open; a
 * granted floor expands exactly as a graded one does, without a grade. The
 * server decides the same thing in `movement.expandable_node_ids`.
 */
export function unlocksNeighbors(holding: HoldingLike): boolean {
  return holding.is_spawn === true || holding.grade != null || isGranted(holding)
}

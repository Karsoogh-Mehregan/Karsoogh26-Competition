/**
 * Node type -> playable level, mirroring `TYPE_TO_LEVEL` in the backend's
 * `game/management/commands/import_graph.py`.
 *
 * The map JSON carries 11 `type` values; the game only has five levels, and
 * capacity is a property of the level, not of the drawing. Both halves of the
 * app read this table so a node's slot count can never disagree between the
 * SVG map and the house model beside it.
 */
export type Level = 'spawn' | 'easy' | 'medium' | 'hard' | 'toll'

export const TYPE_TO_LEVEL: Record<string, Level> = {
  start: 'spawn',
  gateway: 'easy',
  l1: 'easy',
  l2: 'easy',
  l3: 'medium',
  l4: 'medium',
  l5: 'hard',
  l6: 'hard',
  center: 'hard',
  c34: 'toll',
  c45: 'toll',
}

/** Seats per level. `toll` is 1 only because the model checks 1..3. */
export const LEVEL_CAPACITY: Record<Level, 1 | 2 | 3> = {
  spawn: 1,
  easy: 1,
  medium: 2,
  hard: 3,
  toll: 1,
}

export const LEVEL_LABEL: Record<Level, string> = {
  spawn: 'شروع',
  easy: 'آسان',
  medium: 'متوسط',
  hard: 'سخت',
  toll: 'عوارضی',
}

export function levelForType(type: string): Level {
  return TYPE_TO_LEVEL[type] ?? 'easy'
}

export function capacityForType(type: string): 1 | 2 | 3 {
  return LEVEL_CAPACITY[levelForType(type)]
}

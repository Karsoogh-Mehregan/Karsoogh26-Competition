import type { LevelConfigRow } from '@/types/api'

/** Same mapping `import_graph` uses so the SPA can read LevelConfig by node type. */
export const TYPE_TO_LEVEL: Record<string, string> = {
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

export function entryCostForNodeType(
  type: string | undefined,
  levels: LevelConfigRow[] | undefined,
): number | null {
  if (!type || !levels) return null
  const level = TYPE_TO_LEVEL[type]
  if (!level) return null
  const row = levels.find((item) => item.level === level)
  return row == null ? null : row.entry_cost
}

import type { LevelConfigRow, NodeLevel } from '@/types/api'

export function entryCostForLevel(
  level: NodeLevel | null | undefined,
  configs: LevelConfigRow[] | undefined,
): number | null {
  if (!level || !configs?.length) return null
  const row = configs.find((item) => item.level === level)
  return row?.entry_cost ?? null
}

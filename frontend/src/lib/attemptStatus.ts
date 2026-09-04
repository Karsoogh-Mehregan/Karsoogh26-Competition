import type { ActiveAttempt } from '@/types/api'

/** Visual group on the solve page, matching the status icons. */
export type AttemptDisplayGroup = 'open' | 'pending' | 'passed' | 'failed'

const GROUP_RANK: Record<AttemptDisplayGroup, number> = {
  open: 0,
  pending: 1,
  passed: 2,
  failed: 3,
}

export function attemptDisplayGroup(
  attempt: Pick<ActiveAttempt, 'status' | 'grade' | 'is_expired'>,
  timedOut = false,
): AttemptDisplayGroup {
  if (attempt.status === 'graded') {
    return (attempt.grade ?? 0) === 0 ? 'failed' : 'passed'
  }
  if (attempt.status === 'expired' || timedOut || (attempt.status === 'open' && attempt.is_expired)) {
    return 'failed'
  }
  if (attempt.status === 'answered') return 'pending'
  if (attempt.status === 'open') return 'open'
  return 'failed'
}

export function compareAttemptsForSolve(a: ActiveAttempt, b: ActiveAttempt): number {
  const rank = GROUP_RANK[attemptDisplayGroup(a)] - GROUP_RANK[attemptDisplayGroup(b)]
  if (rank !== 0) return rank
  return a.id - b.id
}

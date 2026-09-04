import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed } from 'vue'
import { streamConnected } from '@/lib/boardStreamState'
import {
  getDuelBoard,
  getDuelTargets,
  requestDuel,
  resolveDuel,
} from '@/services/duels'
import type { Duel, DuelBoard, DuelTarget } from '@/types/api'
import { detach } from './invalidate'
import { queryKeys } from './keys'

/**
 * The stream is the live path; this only covers the window where it is down.
 *
 * Faster than the board's 15s, for the same reason the inbox is: a team sitting
 * on the duel page is waiting for exactly one thing — a challenge to land, or a
 * judge to call the result — and has nothing else to look at while it does.
 */
const DUEL_POLL_MS = 10_000

export function useDuelBoardQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.duelBoard(),
    queryFn: ({ signal }) => getDuelBoard(signal),
    enabled,
    refetchInterval: computed(() => (streamConnected.value ? false : DUEL_POLL_MS)),
    refetchOnWindowFocus: true,
  })
}

/**
 * Who this team may challenge.
 *
 * Kept separate from the board query rather than folded into it: the table
 * moves whenever anyone anywhere is graded or starts a duel, while the team's
 * own duel changes only when it acts. Merging them would refetch the cheap half
 * on every tick of the expensive one.
 */
export function useDuelTargetsQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.duelTargets(),
    queryFn: ({ signal }) => getDuelTargets(signal),
    enabled,
    refetchInterval: computed(() => (streamConnected.value ? false : DUEL_POLL_MS)),
  })
}

function invalidateDuels(queryClient: ReturnType<typeof useQueryClient>) {
  detach([
    queryClient.invalidateQueries({ queryKey: queryKeys.duelsRoot() }),
    // A duel moves money now and a floor when it closes, so the board and the
    // wallet log are both stale.
    queryClient.invalidateQueries({ queryKey: queryKeys.teamsRoot() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.balanceEventsRoot() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.leaderboardRoot() }),
  ])
}

export function useRequestDuelMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (occupancyId: number) => requestDuel(occupancyId),
    onSuccess: (_duel: Duel) => invalidateDuels(queryClient),
  })
}

export interface ResolveDuelVariables {
  duelId: number
  winnerCode: string
}

export function useResolveDuelMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ duelId, winnerCode }: ResolveDuelVariables) =>
      resolveDuel(duelId, winnerCode),
    onSuccess: (_duel: Duel) => invalidateDuels(queryClient),
  })
}

export type { Duel, DuelBoard, DuelTarget }

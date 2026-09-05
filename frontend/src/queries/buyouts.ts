import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed } from 'vue'
import { streamConnected } from '@/lib/boardStreamState'
import { buyOut, getBuyoutTargets } from '@/services/buyouts'
import type { BuyoutResult, BuyoutTarget } from '@/types/api'
import { detach } from './invalidate'
import { queryKeys } from './keys'

/** Same fallback cadence as the board: the stream is the live path. */
const BUYOUT_POLL_MS = 15_000

/**
 * What this team may buy.
 *
 * The table moves whenever anyone next door is graded, released or bought out,
 * so the board stream stales it on every seat-moving frame
 * (`useBoardStream.ROUTES`); this interval only covers the window where the
 * stream is down.
 */
export function useBuyoutTargetsQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.buyoutTargets(),
    queryFn: ({ signal }) => getBuyoutTargets(signal),
    enabled,
    refetchInterval: computed(() => (streamConnected.value ? false : BUYOUT_POLL_MS)),
  })
}

export function useBuyOutMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (occupancyId: number) => buyOut(occupancyId),
    onSuccess: (_result: BuyoutResult) =>
      detach([
        queryClient.invalidateQueries({ queryKey: queryKeys.buyoutsRoot() }),
        // A purchase moves a seat and two wallet entries at once, and the seat
        // it took may have been someone's duel target.
        queryClient.invalidateQueries({ queryKey: queryKeys.teamsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.balanceEventsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.leaderboardRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.duelsRoot() }),
      ]),
  })
}

export type { BuyoutResult, BuyoutTarget }

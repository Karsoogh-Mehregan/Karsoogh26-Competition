import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ApiError } from '@/lib/http'
import { ensureCsrf, getMe, login, logout } from '@/services/auth'
import type { LoginCredentials, Me } from '@/types/api'
import { detach } from './invalidate'
import { queryKeys } from './keys'

// Shared with the router guard (router.ts), which prefetches `me` via
// queryClient.ensureQueryData(meQueryOptions) before resolving a navigation.
export const meQueryOptions = {
  queryKey: queryKeys.me(),
  queryFn: async ({ signal }: { signal?: AbortSignal }): Promise<Me | null> => {
    try {
      return await getMe(signal)
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        return null
      }
      throw error
    }
  },
  retry: false,
}

export function useMeQuery() {
  return useQuery(meQueryOptions)
}

export function useLoginMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (credentials: LoginCredentials) => login(credentials),
    onSuccess: (me: Me) => {
      queryClient.setQueryData(queryKeys.me(), me)
      queryClient.removeQueries({ queryKey: queryKeys.minesweeperRoot() })
      detach([
        queryClient.invalidateQueries({ queryKey: queryKeys.teamsRoot() }),
        // The sheet is per-team and cached forever, so it must not outlive
        // the session that drew it.
        queryClient.invalidateQueries({ queryKey: queryKeys.entrySheet() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.balanceEventsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.territoryGames() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.charityBagsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.centipedeGames() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.olympicsMatches() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.auctionEventsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.wheelEventsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.pigEventsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.eventCatalog() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.matchmaking() }),
      ])
    },
  })
}

export function useLogoutMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => logout(),
    onSuccess: async () => {
      queryClient.setQueryData(queryKeys.me(), null)
      queryClient.removeQueries({ queryKey: queryKeys.teamsRoot() })
      queryClient.removeQueries({ queryKey: queryKeys.submissions() })
      queryClient.removeQueries({ queryKey: queryKeys.entrySheet() })
      queryClient.removeQueries({ queryKey: queryKeys.attemptsRoot() })
      queryClient.removeQueries({ queryKey: queryKeys.levels() })
      queryClient.removeQueries({ queryKey: queryKeys.balanceEventsRoot() })
      queryClient.removeQueries({ queryKey: queryKeys.minesweeperRoot() })
      queryClient.removeQueries({ queryKey: queryKeys.territoryGames() })
      queryClient.removeQueries({ queryKey: queryKeys.charityBagsRoot() })
      queryClient.removeQueries({ queryKey: queryKeys.centipedeGames() })
      queryClient.removeQueries({ queryKey: queryKeys.olympicsMatches() })
      queryClient.removeQueries({ queryKey: queryKeys.auctionEventsRoot() })
      queryClient.removeQueries({ queryKey: queryKeys.wheelEventsRoot() })
      queryClient.removeQueries({ queryKey: queryKeys.pigEventsRoot() })
      queryClient.removeQueries({ queryKey: queryKeys.eventCatalog() })
      queryClient.removeQueries({ queryKey: queryKeys.matchmaking() })
      await ensureCsrf()
    },
  })
}

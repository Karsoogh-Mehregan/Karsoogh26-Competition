import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ApiError } from '@/lib/http'
import { ensureCsrf, getMe, login, logout } from '@/services/auth'
import type { LoginCredentials, Me } from '@/types/api'
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
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.teams() }),
        // The sheet is per-team and cached forever, so it must not outlive
        // the session that drew it.
        queryClient.invalidateQueries({ queryKey: queryKeys.entrySheet() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.balanceEventsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.territoryGames() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.charityBags() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.centipedeGames() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.olympicsMatches() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.auctionEvents() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.wheelEvents() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.pigEvents() }),
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
      queryClient.removeQueries({ queryKey: queryKeys.teams() })
      queryClient.removeQueries({ queryKey: queryKeys.submissions() })
      queryClient.removeQueries({ queryKey: queryKeys.entrySheet() })
      queryClient.removeQueries({ queryKey: queryKeys.attemptsRoot() })
      queryClient.removeQueries({ queryKey: queryKeys.levels() })
      queryClient.removeQueries({ queryKey: queryKeys.balanceEventsRoot() })
      queryClient.removeQueries({ queryKey: queryKeys.minesweeperRoot() })
      queryClient.removeQueries({ queryKey: queryKeys.territoryGames() })
      queryClient.removeQueries({ queryKey: queryKeys.charityBags() })
      queryClient.removeQueries({ queryKey: queryKeys.centipedeGames() })
      queryClient.removeQueries({ queryKey: queryKeys.olympicsMatches() })
      queryClient.removeQueries({ queryKey: queryKeys.auctionEvents() })
      queryClient.removeQueries({ queryKey: queryKeys.wheelEvents() })
      queryClient.removeQueries({ queryKey: queryKeys.pigEvents() })
      queryClient.removeQueries({ queryKey: queryKeys.eventCatalog() })
      queryClient.removeQueries({ queryKey: queryKeys.matchmaking() })
      await ensureCsrf()
    },
  })
}

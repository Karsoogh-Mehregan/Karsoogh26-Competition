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
      queryClient.removeQueries({ queryKey: queryKeys.minesweeperRoot() })
      await ensureCsrf()
    },
  })
}

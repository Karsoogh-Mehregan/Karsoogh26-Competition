import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ApiError } from '@/lib/http'
import { ensureCsrf, getMe, login, logout } from '@/services/auth'
import type { LoginCredentials, Me } from '@/types/api'
import { queryKeys } from './keys'

export function useMeQuery() {
  return useQuery({
    queryKey: queryKeys.me(),
    queryFn: async ({ signal }): Promise<Me | null> => {
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
  })
}

export function useLoginMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (credentials: LoginCredentials) => login(credentials),
    onSuccess: (me: Me) => {
      queryClient.setQueryData(queryKeys.me(), me)
      return queryClient.invalidateQueries({ queryKey: queryKeys.teams() })
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
      await ensureCsrf()
    },
  })
}

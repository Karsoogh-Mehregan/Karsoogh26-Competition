import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type ComputedRef, type Ref } from 'vue'
import { streamConnected } from '@/lib/boardStreamState'
import { claimStart, getLeaderboard, listBalanceEvents, listTeams } from '@/services/teams'
import type { Team } from '@/types/api'
import { queryKeys } from './keys'

export function useTeamsQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.teams(),
    queryFn: ({ signal }) => listTeams(signal),
    enabled,
    // Only while the stream is down; SSE covers the live case.
    refetchInterval: computed(() => (streamConnected.value ? false : 15_000)),
  })
}

export function useLeaderboardQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.leaderboard(),
    queryFn: ({ signal }) => getLeaderboard(signal),
    enabled,
  })
}

export function useBalanceEventsQuery(
  teamCode: Ref<string | null> | ComputedRef<string | null>,
  enabled: () => boolean,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.balanceEvents(teamCode.value ?? '')),
    queryFn: ({ signal }) => listBalanceEvents(teamCode.value as string, signal),
    enabled: () => enabled() && teamCode.value != null,
    refetchInterval: computed(() => (streamConnected.value ? false : 15_000)),
  })
}

export interface ClaimStartVariables {
  teamCode: string
  node: string
}

export function useClaimStartMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ teamCode, node }: ClaimStartVariables) => claimStart(teamCode, node),
    onSuccess: (team: Team) => {
      queryClient.setQueryData<Team[]>(queryKeys.teams(), (teams) =>
        teams?.map((item) => (item.code === team.code ? team : item)),
      )
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.teams() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.balanceEventsRoot() }),
      ])
    },
  })
}

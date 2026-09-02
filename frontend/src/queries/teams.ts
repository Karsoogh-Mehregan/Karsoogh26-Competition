import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed } from 'vue'
import { streamConnected } from '@/lib/boardStreamState'
import { claimStart, getLeaderboard, listTeams } from '@/services/teams'
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
      return queryClient.invalidateQueries({ queryKey: queryKeys.teams() })
    },
  })
}

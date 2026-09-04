import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'
import { useBoard } from '@/composables/useBoard'
import { streamConnected } from '@/lib/boardStreamState'
import { claimStart, getLeaderboard, listBalanceEvents, listTeams } from '@/services/teams'
import type { Team } from '@/types/api'
import { queryKeys } from './keys'

export function useTeamsQuery(enabled: () => boolean) {
  const { board } = useBoard()
  return useQuery({
    queryKey: computed(() => queryKeys.teams(board.value)),
    queryFn: ({ signal }) => listTeams(board.value, signal),
    enabled,
    // Only while the stream is down; SSE covers the live case.
    refetchInterval: computed(() => (streamConnected.value ? false : 15_000)),
  })
}

export function useLeaderboardQuery(enabled: () => boolean) {
  const { board } = useBoard()
  return useQuery({
    queryKey: computed(() => queryKeys.leaderboard(board.value)),
    queryFn: ({ signal }) => getLeaderboard(board.value, signal),
    enabled,
  })
}

export interface ClaimStartVariables {
  teamCode: string
  node: string
}

export function useClaimStartMutation() {
  const queryClient = useQueryClient()
  const { board } = useBoard()
  return useMutation({
    mutationFn: ({ teamCode, node }: ClaimStartVariables) => claimStart(teamCode, node),
    onSuccess: (team: Team) => {
      queryClient.setQueryData<Team[]>(queryKeys.teams(board.value), (teams) =>
        teams?.map((item) => (item.code === team.code ? team : item)),
      )
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.teamsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.balanceEventsRoot() }),
      ])
    },
  })
}

export function useBalanceEventsQuery(enabled: () => boolean, teamCode: Ref<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.balanceEvents(teamCode.value)),
    queryFn: ({ signal }) => listBalanceEvents(teamCode.value, signal),
    enabled: computed(() => enabled() && !!teamCode.value),
  })
}

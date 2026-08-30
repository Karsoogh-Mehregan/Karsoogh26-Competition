import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { claimStart, listTeams } from '@/services/teams'
import type { Team } from '@/types/api'
import { queryKeys } from './keys'

export function useTeamsQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.teams(),
    queryFn: ({ signal }) => listTeams(signal),
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

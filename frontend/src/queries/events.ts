import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'
import {
  createTerritoryGame,
  getTerritoryGame,
  listTerritoryGames,
  playTerritoryTurn,
} from '@/services/events'
import type {
  CreateTerritoryGameInput,
  PlayTerritoryTurnInput,
  TerritoryGame,
} from '@/types/api'
import { queryKeys } from './keys'

export function useTerritoryGamesQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.territoryGames(),
    queryFn: ({ signal }) => listTerritoryGames(signal),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.some((game) => game.status === 'running') ? 5000 : false,
  })
}

export function useTerritoryGameQuery(gameId: Ref<number | null>, enabled: () => boolean) {
  return useQuery({
    queryKey: computed(() => queryKeys.territoryGame(gameId.value ?? 'none')),
    queryFn: ({ signal }) => {
      if (gameId.value == null) throw new Error('No territory game selected.')
      return getTerritoryGame(gameId.value, signal)
    },
    enabled: computed(() => enabled() && gameId.value != null),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 3000 : false),
  })
}

export function useCreateTerritoryGameMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateTerritoryGameInput) => createTerritoryGame(input),
    onSuccess: (game) => {
      queryClient.setQueryData(queryKeys.territoryGame(game.id), game)
      return queryClient.invalidateQueries({ queryKey: queryKeys.territoryGames() })
    },
  })
}

interface PlayTurnVariables extends PlayTerritoryTurnInput {
  gameId: number
}

export function usePlayTerritoryTurnMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ gameId, row, column }: PlayTurnVariables) =>
      playTerritoryTurn(gameId, { row, column }),
    onSuccess: (game: TerritoryGame) => {
      queryClient.setQueryData(queryKeys.territoryGame(game.id), game)
      queryClient.setQueryData<TerritoryGame[]>(queryKeys.territoryGames(), (games) =>
        games?.map((item) => (item.id === game.id ? game : item)),
      )
    },
  })
}

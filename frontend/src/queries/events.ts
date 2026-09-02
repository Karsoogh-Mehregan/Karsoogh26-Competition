import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'
import {
  createCentipedeGame,
  createCharityBag,
  createTerritoryGame,
  enterCharityBag,
  getCharityBag,
  getCentipedeGame,
  getTerritoryGame,
  listCharityBags,
  listCentipedeGames,
  listTerritoryGames,
  playTerritoryTurn,
  playCentipedeAction,
} from '@/services/events'
import type {
  CentipedeGame,
  CharityBagEvent,
  CreateCharityBagInput,
  CreateCentipedeGameInput,
  CreateTerritoryGameInput,
  EnterCharityBagInput,
  PlayTerritoryTurnInput,
  PlayCentipedeActionInput,
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

export function useCharityBagsQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.charityBags(),
    queryFn: ({ signal }) => listCharityBags(signal),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.some((event) => ['active', 'resolving'].includes(event.status))
        ? 2000
        : 15000,
  })
}

export function useCharityBagQuery(eventId: Ref<number | null>, enabled: () => boolean) {
  return useQuery({
    queryKey: computed(() => queryKeys.charityBag(eventId.value ?? 'none')),
    queryFn: ({ signal }) => {
      if (eventId.value == null) throw new Error('No Charity Bag selected.')
      return getCharityBag(eventId.value, signal)
    },
    enabled: computed(() => enabled() && eventId.value != null),
    refetchInterval: (query) =>
      query.state.data && ['active', 'resolving'].includes(query.state.data.status) ? 2000 : false,
  })
}

interface EnterCharityVariables extends EnterCharityBagInput {
  eventId: number
}

export function useEnterCharityBagMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ eventId, action, amount }: EnterCharityVariables) =>
      enterCharityBag(eventId, { action, amount }),
    onSuccess: (event: CharityBagEvent) => {
      queryClient.setQueryData(queryKeys.charityBag(event.id), event)
      queryClient.invalidateQueries({ queryKey: queryKeys.teams() })
      return queryClient.invalidateQueries({ queryKey: queryKeys.charityBags() })
    },
  })
}

export function useCreateCharityBagMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateCharityBagInput) => createCharityBag(input),
    onSuccess: (event) => {
      queryClient.setQueryData(queryKeys.charityBag(event.id), event)
      return queryClient.invalidateQueries({ queryKey: queryKeys.charityBags() })
    },
  })
}

export function useCentipedeGamesQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.centipedeGames(),
    queryFn: ({ signal }) => listCentipedeGames(signal),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.some((game) => game.status === 'active') ? 3000 : false,
  })
}

export function useCentipedeGameQuery(gameId: Ref<number | null>, enabled: () => boolean) {
  return useQuery({
    queryKey: computed(() => queryKeys.centipedeGame(gameId.value ?? 'none')),
    queryFn: ({ signal }) => {
      if (gameId.value == null) throw new Error('No Centipede game selected.')
      return getCentipedeGame(gameId.value, signal)
    },
    enabled: computed(() => enabled() && gameId.value != null),
    refetchInterval: (query) => (query.state.data?.status === 'active' ? 2000 : false),
  })
}

interface CentipedeActionVariables extends PlayCentipedeActionInput {
  gameId: number
}

export function usePlayCentipedeActionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ gameId, action }: CentipedeActionVariables) =>
      playCentipedeAction(gameId, { action }),
    onSuccess: (game: CentipedeGame) => {
      queryClient.setQueryData(queryKeys.centipedeGame(game.id), game)
      queryClient.invalidateQueries({ queryKey: queryKeys.teams() })
      return queryClient.invalidateQueries({ queryKey: queryKeys.centipedeGames() })
    },
  })
}

export function useCreateCentipedeGameMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateCentipedeGameInput) => createCentipedeGame(input),
    onSuccess: (game) => {
      queryClient.setQueryData(queryKeys.centipedeGame(game.id), game)
      return queryClient.invalidateQueries({ queryKey: queryKeys.centipedeGames() })
    },
  })
}

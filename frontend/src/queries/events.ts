import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'
import { useBoard } from '@/composables/useBoard'
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
  createOlympicsMatch,
  getOlympicsMatch,
  listOlympicsMatches,
  recordOlympicsResult,
  startOlympicsMatch,
  submitOlympicsPlayerRun,
  createAuctionEvent,
  createPigEvent,
  createWheelEvent,
  deliverWheelSpin,
  finishPigEvent,
  listAuctionEvents,
  listPigEvents,
  listWheelEvents,
  placeAuctionBid,
  playPigAction,
  resolveAuctionEvent,
  spinWheel,
  startPigGame,
  startWheelEvent,
  stopWheelEvent,
  cancelMatchmaking,
  dismissMatchmaking,
  joinMatchmaking,
  listEventConfigurations,
  listMatchmakingTickets,
  updateEventConfiguration,
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
  CreateOlympicsMatchInput,
  RecordOlympicsResultInput,
  WheelPrizeInput,
  EventCode,
  EventConfiguration,
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
  return useMutation({
    mutationFn: ({ gameId, row, column }: PlayTurnVariables) =>
      playTerritoryTurn(gameId, { row, column }),
  })
}

export function useCharityBagsQuery(enabled: () => boolean) {
  const { board } = useBoard()
  return useQuery({
    queryKey: computed(() => queryKeys.charityBags(board.value)),
    queryFn: ({ signal }) => listCharityBags(board.value, signal),
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
      queryClient.invalidateQueries({ queryKey: queryKeys.balanceEventsRoot() })
      queryClient.invalidateQueries({ queryKey: queryKeys.teamsRoot() })
      return queryClient.invalidateQueries({ queryKey: queryKeys.charityBagsRoot() })
    },
  })
}

export function useCreateCharityBagMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateCharityBagInput) => createCharityBag(input),
    onSuccess: (event) => {
      queryClient.setQueryData(queryKeys.charityBag(event.id), event)
      return queryClient.invalidateQueries({ queryKey: queryKeys.charityBagsRoot() })
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
    mutationFn: ({ gameId, action, round_number }: CentipedeActionVariables) =>
      playCentipedeAction(gameId, { action, round_number }),
    onSuccess: (game: CentipedeGame) => {
      queryClient.setQueryData(queryKeys.centipedeGame(game.id), game)
      queryClient.invalidateQueries({ queryKey: queryKeys.balanceEventsRoot() })
      queryClient.invalidateQueries({ queryKey: queryKeys.teamsRoot() })
      return queryClient.invalidateQueries({ queryKey: queryKeys.centipedeGames() })
    },
  })
}

export function useCreateCentipedeGameMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateCentipedeGameInput) => createCentipedeGame(input),
    onSuccess: (game) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.balanceEventsRoot() })
      queryClient.invalidateQueries({ queryKey: queryKeys.teamsRoot() })
      queryClient.setQueryData(queryKeys.centipedeGame(game.id), game)
      return queryClient.invalidateQueries({ queryKey: queryKeys.centipedeGames() })
    },
  })
}

export function useOlympicsMatchesQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.olympicsMatches(),
    queryFn: ({ signal }) => listOlympicsMatches(signal),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.some((match) => match.status !== 'finished') ? 5000 : false,
  })
}

export function useOlympicsMatchQuery(matchId: Ref<number | null>, enabled: () => boolean) {
  return useQuery({
    queryKey: computed(() => queryKeys.olympicsMatch(matchId.value ?? 'none')),
    queryFn: ({ signal }) => {
      if (matchId.value == null) throw new Error('No Olympics match selected.')
      return getOlympicsMatch(matchId.value, signal)
    },
    enabled: computed(() => enabled() && matchId.value != null),
    refetchInterval: (query) => (query.state.data?.status !== 'finished' ? 4000 : false),
  })
}

export function useCreateOlympicsMatchMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateOlympicsMatchInput) => createOlympicsMatch(input),
    onSuccess: (match) => {
      queryClient.setQueryData(queryKeys.olympicsMatch(match.id), match)
      return queryClient.invalidateQueries({ queryKey: queryKeys.olympicsMatches() })
    },
  })
}

export function useStartOlympicsMatchMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (matchId: number) => startOlympicsMatch(matchId),
    onSuccess: (match) => {
      queryClient.setQueryData(queryKeys.olympicsMatch(match.id), match)
      return queryClient.invalidateQueries({ queryKey: queryKeys.olympicsMatches() })
    },
  })
}

interface OlympicsResultVariables extends RecordOlympicsResultInput {
  matchId: number
}

export function useRecordOlympicsResultMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ matchId, ...input }: OlympicsResultVariables) =>
      recordOlympicsResult(matchId, input),
    onSuccess: (match) => {
      queryClient.setQueryData(queryKeys.olympicsMatch(match.id), match)
      return queryClient.invalidateQueries({ queryKey: queryKeys.olympicsMatches() })
    },
  })
}

export function useSubmitOlympicsPlayerRunMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ matchId, roundNumber, attempts, bestDistance }: { matchId: number; roundNumber: number; attempts?: number[]; bestDistance?: string }) =>
      submitOlympicsPlayerRun(matchId, { round_number: roundNumber, attempts, best_distance: bestDistance }),
    onSuccess: (match) => {
      queryClient.setQueryData(queryKeys.olympicsMatch(match.id), match)
      return refresh(queryClient, queryKeys.olympicsMatches())
    },
  })
}

const refresh = (queryClient: ReturnType<typeof useQueryClient>, key: readonly unknown[]) =>
  queryClient.invalidateQueries({ queryKey: key })

export function useAuctionEventsQuery(enabled: () => boolean) {
  const { board } = useBoard()
  return useQuery({
    queryKey: computed(() => queryKeys.auctionEvents(board.value)),
    queryFn: ({ signal }) => listAuctionEvents(board.value, signal),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.some((event) => event.status === 'active') ? 2000 : false,
  })
}

export function useCreateAuctionMutation() {
  const queryClient = useQueryClient()
  const { board } = useBoard()
  return useMutation({
    mutationFn: (duration: number) => createAuctionEvent(board.value, duration),
    onSuccess: () => Promise.all([
      refresh(queryClient, queryKeys.auctionEventsRoot()),
      refresh(queryClient, queryKeys.teamsRoot()),
      refresh(queryClient, queryKeys.balanceEventsRoot()),
    ]),
  })
}

export function useAuctionBidMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ pairId, amount, requestId }: { pairId: number; amount: number; requestId: string }) =>
      placeAuctionBid(pairId, amount, requestId),
    onSuccess: () => Promise.all([
      refresh(queryClient, queryKeys.auctionEventsRoot()),
      refresh(queryClient, queryKeys.teamsRoot()),
      refresh(queryClient, queryKeys.balanceEventsRoot()),
    ]),
  })
}

export function useResolveAuctionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (eventId: number) => resolveAuctionEvent(eventId),
    onSuccess: () => Promise.all([
      refresh(queryClient, queryKeys.auctionEventsRoot()),
      refresh(queryClient, queryKeys.teamsRoot()),
      refresh(queryClient, queryKeys.balanceEventsRoot()),
    ]),
  })
}

export function useWheelEventsQuery(enabled: () => boolean) {
  const { board } = useBoard()
  return useQuery({
    queryKey: computed(() => queryKeys.wheelEvents(board.value)),
    queryFn: ({ signal }) => listWheelEvents(board.value, signal),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.some((event) => event.status === 'active') ? 2500 : false,
  })
}

export function useCreateWheelMutation() {
  const queryClient = useQueryClient()
  const { board } = useBoard()
  return useMutation({
    mutationFn: ({ spinCost, prizes }: { spinCost: number; prizes: WheelPrizeInput[] }) =>
      createWheelEvent(board.value, spinCost, prizes),
    onSuccess: () => refresh(queryClient, queryKeys.wheelEventsRoot()),
  })
}

export function useWheelStateMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ eventId, action }: { eventId: number; action: 'start' | 'stop' }) =>
      action === 'start' ? startWheelEvent(eventId) : stopWheelEvent(eventId),
    onSuccess: () => refresh(queryClient, queryKeys.wheelEventsRoot()),
  })
}

export function useWheelSpinMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ eventId, requestId }: { eventId: number; requestId: string }) =>
      spinWheel(eventId, requestId),
    onSuccess: () => Promise.all([
      refresh(queryClient, queryKeys.wheelEventsRoot()),
      refresh(queryClient, queryKeys.teamsRoot()),
      refresh(queryClient, queryKeys.balanceEventsRoot()),
    ]),
  })
}

export function useWheelDeliveryMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (spinId: number) => deliverWheelSpin(spinId),
    onSuccess: () => refresh(queryClient, queryKeys.wheelEventsRoot()),
  })
}

export function usePigEventsQuery(enabled: () => boolean) {
  const { board } = useBoard()
  return useQuery({
    queryKey: computed(() => queryKeys.pigEvents(board.value)),
    queryFn: ({ signal }) => listPigEvents(board.value, signal),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.some((event) => event.games.some((game) => game.status === 'active'))
        ? 2500
        : false,
  })
}

export function useCreatePigMutation() {
  const queryClient = useQueryClient()
  const { board } = useBoard()
  return useMutation({
    mutationFn: (maxPot: number) => createPigEvent(board.value, maxPot),
    onSuccess: () => refresh(queryClient, queryKeys.pigEventsRoot()),
  })
}

export function useFinishPigMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (eventId: number) => finishPigEvent(eventId),
    onSuccess: () => refresh(queryClient, queryKeys.pigEventsRoot()),
  })
}

export function useStartPigGameMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (eventId: number) => startPigGame(eventId),
    onSuccess: () => Promise.all([
      refresh(queryClient, queryKeys.pigEventsRoot()),
      refresh(queryClient, queryKeys.teamsRoot()),
      refresh(queryClient, queryKeys.balanceEventsRoot()),
    ]),
  })
}

export function usePigActionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ gameId, action, requestId }: { gameId: number; action: 'roll' | 'cash_out'; requestId: string }) =>
      playPigAction(gameId, action, requestId),
    onSuccess: () => Promise.all([
      refresh(queryClient, queryKeys.pigEventsRoot()),
      refresh(queryClient, queryKeys.teamsRoot()),
      refresh(queryClient, queryKeys.balanceEventsRoot()),
    ]),
  })
}

export const eventCatalogQueryOptions = {
  queryKey: queryKeys.eventCatalog(),
  queryFn: ({ signal }: { signal: AbortSignal }) => listEventConfigurations(signal),
}

export function useEventCatalogQuery(enabled: () => boolean) {
  return useQuery({
    ...eventCatalogQueryOptions,
    enabled,
    refetchInterval: 5000,
  })
}

export function useUpdateEventConfigurationMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ code, input }: { code: EventCode; input: Partial<Pick<EventConfiguration, 'enabled' | 'duration_seconds' | 'settings'>> }) =>
      updateEventConfiguration(code, input),
    onSuccess: () => refresh(queryClient, queryKeys.eventCatalog()),
  })
}

export function useMatchmakingQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.matchmaking(),
    queryFn: ({ signal }) => listMatchmakingTickets(signal),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.some((ticket) => ticket.status === 'waiting') ? 2000 : false,
  })
}

export function useMatchmakingMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ code, action, ticketId }: { code: EventCode; action: 'join' | 'cancel' | 'dismiss'; ticketId?: number }) => {
      if (action === 'join') return joinMatchmaking(code)
      if (action === 'cancel') return cancelMatchmaking(code)
      if (ticketId == null) throw new Error('شناسه مسابقه موجود نیست.')
      return dismissMatchmaking(ticketId)
    },
    onSuccess: () => Promise.all([
      refresh(queryClient, queryKeys.matchmaking()),
      refresh(queryClient, queryKeys.teamsRoot()),
      refresh(queryClient, queryKeys.balanceEventsRoot()),
      refresh(queryClient, queryKeys.territoryGames()),
      refresh(queryClient, queryKeys.centipedeGames()),
      refresh(queryClient, queryKeys.olympicsMatches()),
    ]),
  })
}

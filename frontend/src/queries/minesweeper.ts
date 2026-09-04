import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type ComputedRef, type Ref } from 'vue'
import { enterPlay, getAttempt, revealCell, startPlay, toggleFlag } from '@/services/minesweeper'
import type { MinesweeperGame } from '@/types/api'
import { queryKeys } from './keys'

export function useMinesweeperAttemptQuery(
  attemptId: Ref<number | null> | ComputedRef<number | null>,
  enabled: () => boolean = () => true,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.minesweeperAttempt(attemptId.value ?? 0)),
    queryFn: ({ signal }) => getAttempt(attemptId.value as number, signal),
    enabled: () => enabled() && attemptId.value != null,
  })
}

function cacheAttempt(queryClient: QueryClient, game: MinesweeperGame): void {
  queryClient.setQueryData(queryKeys.minesweeperAttempt(game.attempt_id), game)
  // A win on a toll gate opens the road past it, and that reach travels on the
  // team row (`crossings`), not on this response — so the board has to be
  // refetched or the map keeps the far side greyed out until the next poll.
  if (game.status === 'won') {
    queryClient.invalidateQueries({ queryKey: queryKeys.teams() })
  }
}

export function useEnterMinesweeperMutation() {
  return useMutation({
    mutationFn: (nodeCode: string) => enterPlay(nodeCode),
  })
}

export interface MinesweeperStartVariables {
  nodeCode: string
  entry: string
}

export function useStartMinesweeperMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ nodeCode, entry }: MinesweeperStartVariables) => startPlay(nodeCode, entry),
    onSuccess: (game: MinesweeperGame) => {
      cacheAttempt(queryClient, game)
      // Starting a gate charges the toll, so the team's balance is now stale.
      queryClient.invalidateQueries({ queryKey: queryKeys.teams() })
    },
  })
}

export interface MinesweeperCellActionVariables {
  attemptId: number
  row: number
  col: number
}

export function useRevealMinesweeperCellMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ attemptId, row, col }: MinesweeperCellActionVariables) =>
      revealCell(attemptId, row, col),
    onSuccess: (game: MinesweeperGame) => {
      cacheAttempt(queryClient, game)
    },
  })
}

export function useToggleMinesweeperFlagMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ attemptId, row, col }: MinesweeperCellActionVariables) =>
      toggleFlag(attemptId, row, col),
    onSuccess: (game: MinesweeperGame) => {
      cacheAttempt(queryClient, game)
    },
  })
}

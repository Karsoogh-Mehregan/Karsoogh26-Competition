import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type ComputedRef, type Ref } from 'vue'
import { getAttempt, revealCell, startPlay, toggleFlag } from '@/services/minesweeper'
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
}

export function useStartMinesweeperMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (nodeId: number) => startPlay(nodeId),
    onSuccess: (game: MinesweeperGame) => {
      cacheAttempt(queryClient, game)
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

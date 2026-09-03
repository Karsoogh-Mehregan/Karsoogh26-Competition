import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type ComputedRef, type Ref } from 'vue'
import { createGame, getGame, revealCell, toggleFlag } from '@/services/minesweeper'
import type { MinesweeperDifficulty, MinesweeperGame } from '@/types/api'
import { queryKeys } from './keys'

export function useMinesweeperGameQuery(
  gameId: Ref<number | null> | ComputedRef<number | null>,
  enabled: () => boolean = () => true,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.minesweeperGame(gameId.value ?? 0)),
    queryFn: ({ signal }) => getGame(gameId.value as number, signal),
    enabled: () => enabled() && gameId.value != null,
  })
}

function cacheGame(queryClient: QueryClient, game: MinesweeperGame): void {
  queryClient.setQueryData(queryKeys.minesweeperGame(game.id), game)
}

export interface CreateMinesweeperGameVariables {
  node: number
  difficulty: MinesweeperDifficulty
}

export function useCreateMinesweeperGameMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ node, difficulty }: CreateMinesweeperGameVariables) =>
      createGame(node, difficulty),
    onSuccess: (game: MinesweeperGame) => {
      cacheGame(queryClient, game)
    },
  })
}

export interface MinesweeperCellActionVariables {
  gameId: number
  row: number
  col: number
}

export function useRevealMinesweeperCellMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ gameId, row, col }: MinesweeperCellActionVariables) =>
      revealCell(gameId, row, col),
    onSuccess: (game: MinesweeperGame) => {
      cacheGame(queryClient, game)
    },
  })
}

export function useToggleMinesweeperFlagMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ gameId, row, col }: MinesweeperCellActionVariables) =>
      toggleFlag(gameId, row, col),
    onSuccess: (game: MinesweeperGame) => {
      cacheGame(queryClient, game)
    },
  })
}

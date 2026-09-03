import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { getGameSettings, getGameState, restartGame, updateGameSettings } from '@/services/game'
import type { GameRestartResult, GameSettings, GameState } from '@/types/api'
import { queryKeys } from './keys'

// The clock is derived from `server_time`, so a slow refetch only shifts the
// offset, never the ticking. A minute is plenty to catch an admin's change even
// if the SSE `game.state` event is missed.
const STATE_REFETCH_MS = 60_000

export function useGameStateQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.gameState(),
    queryFn: ({ signal }) => getGameState(signal),
    enabled,
    refetchInterval: STATE_REFETCH_MS,
    refetchOnWindowFocus: true,
  })
}

export function useGameSettingsQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.gameSettings(),
    queryFn: ({ signal }) => getGameSettings(signal),
    enabled,
  })
}

export function useUpdateGameSettingsMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: Partial<GameSettings>) => updateGameSettings(changes),
    onSuccess: (settings: GameSettings) => {
      queryClient.setQueryData<GameSettings>(queryKeys.gameSettings(), settings)
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.gameState() }),
        // Publishing the leaderboard changes who may read it.
        queryClient.invalidateQueries({ queryKey: queryKeys.leaderboard() }),
      ])
    },
  })
}

export function useRestartGameMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => restartGame(),
    // A restart empties the board and refunds everyone, so nothing cached
    // survives it.
    onSuccess: (_result: GameRestartResult) => queryClient.invalidateQueries(),
  })
}

export type { GameState }

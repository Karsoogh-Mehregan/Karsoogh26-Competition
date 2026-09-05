import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import {
  extendGame,
  getGameSettings,
  getGameState,
  restartGame,
  updateGameSettings,
} from '@/services/game'
import type { GameExtendResult, GameRestartResult, GameSettings, GameState } from '@/types/api'
import { detach } from './invalidate'
import { queryKeys } from './keys'

// The clock is derived from `server_time`, so a slow refetch only shifts the
// offset, never the ticking. A minute is plenty to catch an admin's change even
// if the SSE `game.state` event is missed.
const STATE_REFETCH_MS = 60_000

// Shared with the router guard (router.ts), which needs `design_locked` before
// it may resolve a navigation to the Designer's page.
export const gameStateQueryOptions = {
  queryKey: queryKeys.gameState(),
  queryFn: ({ signal }: { signal?: AbortSignal }) => getGameState(signal),
}

export function useGameStateQuery(enabled: () => boolean) {
  return useQuery({
    ...gameStateQueryOptions,
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
      detach([
        queryClient.invalidateQueries({ queryKey: queryKeys.gameState() }),
        // Freeze (or thaw) changes what competing teams read from this list.
        queryClient.invalidateQueries({ queryKey: queryKeys.leaderboardRoot() }),
      ])
    },
  })
}

/**
 * Grant extra time. The response carries the new total, so the settings cache is
 * written from it rather than refetched — but the *clock* is invalidated, since
 * every client's countdown is derived from the state endpoint.
 */
export function useExtendGameMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (minutes: number) => extendGame(minutes),
    onSuccess: (result: GameExtendResult) => {
      queryClient.setQueryData<GameSettings>(queryKeys.gameSettings(), (previous) =>
        previous ? { ...previous, duration_minutes: result.duration_minutes } : previous,
      )
      detach(queryClient.invalidateQueries({ queryKey: queryKeys.gameState() }))
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

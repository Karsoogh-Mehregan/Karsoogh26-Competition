import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ApiError } from '@/lib/http'
import { useMeQuery } from '@/queries/auth'
import {
  useJoinMinesweeperGameMutation,
  useMinesweeperGameQuery,
  useRevealMinesweeperCellMutation,
  useToggleMinesweeperFlagMutation,
} from '@/queries/minesweeper'
import type { MinesweeperGame } from '@/types/api'

function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403 && error.detail === 'The game is not running.') {
      return 'مسابقه در حال برگزاری نیست.'
    }
    return error.detail
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'خطا در ارتباط با سرور.'
}

export function useMinesweeper(gameId: Ref<number | null> | ComputedRef<number | null>) {
  const meQuery = useMeQuery()
  const isPlayer = computed(() => meQuery.data.value?.team != null)

  const hasJoined = ref(false)
  const attemptId = ref<number | null>(null)
  const gameQuery = useMinesweeperGameQuery(
    gameId,
    () => isPlayer.value && hasJoined.value,
  )
  const joinMutation = useJoinMinesweeperGameMutation()
  const revealMutation = useRevealMinesweeperCellMutation()
  const flagMutation = useToggleMinesweeperFlagMutation()

  const actionError = ref('')

  const game = computed<MinesweeperGame | null>(() => gameQuery.data.value ?? null)
  const joining = computed(() => joinMutation.isPending.value)
  const loading = computed(
    () =>
      joining.value ||
      (hasJoined.value && isPlayer.value && gameQuery.isPending.value),
  )
  const revealing = computed(() => revealMutation.isPending.value)
  const flagging = computed(() => flagMutation.isPending.value)

  const error = computed(() => {
    if (actionError.value) {
      return actionError.value
    }
    return gameQuery.error.value ? messageOf(gameQuery.error.value) : ''
  })

  async function join(): Promise<MinesweeperGame | null> {
    const id = gameId.value
    hasJoined.value = false
    attemptId.value = null
    if (id == null) {
      actionError.value = 'بازی پیدا نشد.'
      return null
    }
    actionError.value = ''
    try {
      const result = await joinMutation.mutateAsync(id)
      if (gameId.value !== id) {
        return result
      }
      attemptId.value = result.attempt_id
      hasJoined.value = true
      return result
    } catch (err) {
      actionError.value = messageOf(err)
      return null
    }
  }

  async function reveal(row: number, col: number): Promise<MinesweeperGame | null> {
    const id = gameId.value
    if (id == null) {
      actionError.value = 'بازی پیدا نشد.'
      return null
    }
    actionError.value = ''
    try {
      return await revealMutation.mutateAsync({ gameId: id, row, col })
    } catch (err) {
      actionError.value = messageOf(err)
      return null
    }
  }

  async function toggleFlag(row: number, col: number): Promise<MinesweeperGame | null> {
    const id = gameId.value
    if (id == null) {
      actionError.value = 'بازی پیدا نشد.'
      return null
    }
    actionError.value = ''
    try {
      return await flagMutation.mutateAsync({ gameId: id, row, col })
    } catch (err) {
      actionError.value = messageOf(err)
      return null
    }
  }

  return {
    game,
    loading,
    joining,
    revealing,
    flagging,
    error,
    isPlayer,
    attemptId,
    join,
    reveal,
    toggleFlag,
  }
}

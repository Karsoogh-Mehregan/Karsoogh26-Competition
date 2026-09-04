import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ApiError } from '@/lib/http'
import { useMeQuery } from '@/queries/auth'
import {
  useMinesweeperAttemptQuery,
  useRevealMinesweeperCellMutation,
  useStartMinesweeperMutation,
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

export function useMinesweeper(nodeCode: Ref<string | null> | ComputedRef<string | null>) {
  const meQuery = useMeQuery()
  const isPlayer = computed(() => meQuery.data.value?.team != null)

  const hasStarted = ref(false)
  const attemptId = ref<number | null>(null)
  const gameQuery = useMinesweeperAttemptQuery(
    attemptId,
    () => isPlayer.value && hasStarted.value,
  )
  const startMutation = useStartMinesweeperMutation()
  const revealMutation = useRevealMinesweeperCellMutation()
  const flagMutation = useToggleMinesweeperFlagMutation()

  const actionError = ref('')

  const game = computed<MinesweeperGame | null>(() => gameQuery.data.value ?? null)
  const starting = computed(() => startMutation.isPending.value)
  const loading = computed(
    () =>
      starting.value ||
      (hasStarted.value && isPlayer.value && gameQuery.isPending.value),
  )
  const revealing = computed(() => revealMutation.isPending.value)
  const flagging = computed(() => flagMutation.isPending.value)

  const error = computed(() => {
    if (actionError.value) {
      return actionError.value
    }
    return gameQuery.error.value ? messageOf(gameQuery.error.value) : ''
  })

  async function start(entry: string): Promise<MinesweeperGame | null> {
    const code = nodeCode.value
    hasStarted.value = false
    attemptId.value = null
    if (code == null || !entry) {
      actionError.value = 'بازی پیدا نشد.'
      return null
    }
    actionError.value = ''
    try {
      const result = await startMutation.mutateAsync({ nodeCode: code, entry })
      if (nodeCode.value !== code) {
        return result
      }
      attemptId.value = result.attempt_id
      hasStarted.value = true
      return result
    } catch (err) {
      actionError.value = messageOf(err)
      return null
    }
  }

  async function reveal(row: number, col: number): Promise<MinesweeperGame | null> {
    const id = attemptId.value
    if (id == null) {
      actionError.value = 'بازی پیدا نشد.'
      return null
    }
    actionError.value = ''
    try {
      return await revealMutation.mutateAsync({ attemptId: id, row, col })
    } catch (err) {
      actionError.value = messageOf(err)
      return null
    }
  }

  async function toggleFlag(row: number, col: number): Promise<MinesweeperGame | null> {
    const id = attemptId.value
    if (id == null) {
      actionError.value = 'بازی پیدا نشد.'
      return null
    }
    actionError.value = ''
    try {
      return await flagMutation.mutateAsync({ attemptId: id, row, col })
    } catch (err) {
      actionError.value = messageOf(err)
      return null
    }
  }

  return {
    game,
    loading,
    starting,
    revealing,
    flagging,
    error,
    isPlayer,
    attemptId,
    start,
    reveal,
    toggleFlag,
  }
}

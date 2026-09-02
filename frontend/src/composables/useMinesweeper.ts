import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ApiError } from '@/lib/http'
import { useMeQuery } from '@/queries/auth'
import {
  useCreateMinesweeperGameMutation,
  useMinesweeperGameQuery,
  useRevealMinesweeperCellMutation,
  useToggleMinesweeperFlagMutation,
} from '@/queries/minesweeper'
import type { MinesweeperDifficulty, MinesweeperGame } from '@/types/api'

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

  const gameQuery = useMinesweeperGameQuery(gameId, () => isPlayer.value)
  const createMutation = useCreateMinesweeperGameMutation()
  const revealMutation = useRevealMinesweeperCellMutation()
  const flagMutation = useToggleMinesweeperFlagMutation()

  const actionError = ref('')

  const game = computed<MinesweeperGame | null>(() => gameQuery.data.value ?? null)
  const loading = computed(() => gameId.value != null && isPlayer.value && gameQuery.isPending.value)
  const creating = computed(() => createMutation.isPending.value)
  const revealing = computed(() => revealMutation.isPending.value)
  const flagging = computed(() => flagMutation.isPending.value)

  const error = computed(() => {
    if (actionError.value) {
      return actionError.value
    }
    return gameQuery.error.value ? messageOf(gameQuery.error.value) : ''
  })

  async function create(difficulty: MinesweeperDifficulty): Promise<MinesweeperGame | null> {
    actionError.value = ''
    try {
      return await createMutation.mutateAsync({ difficulty })
    } catch (err) {
      actionError.value = messageOf(err)
      return null
    }
  }

  async function reveal(row: number, col: number): Promise<MinesweeperGame | null> {
    const id = gameId.value
    if (id == null) {
      actionError.value = 'ابتدا یک بازی بسازید.'
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
      actionError.value = 'ابتدا یک بازی بسازید.'
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
    creating,
    revealing,
    flagging,
    error,
    isPlayer,
    create,
    reveal,
    toggleFlag,
  }
}

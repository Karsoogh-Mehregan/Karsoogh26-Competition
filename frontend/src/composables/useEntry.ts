import { computed, ref } from 'vue'
import { ApiError } from '@/lib/http'
import { useMeQuery } from '@/queries/auth'
import {
  useAnswerEntryMutation,
  useEntrySheetQuery,
  useRefreshEntryMutation,
} from '@/queries/entry'
import type { EntryAttempt, EntrySheet } from '@/types/api'

// Module-level so the map and the side panel drive the same dialog, the same
// way useGraph() shares one traversal state.
const isOpen = ref(false)

export function openEntrySheet(): void {
  isOpen.value = true
}

export function closeEntrySheet(): void {
  isOpen.value = false
}

function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'خطا در ارتباط با سرور.'
}

export function useEntry() {
  const meQuery = useMeQuery()
  const isPlayer = computed(() => meQuery.data.value?.team != null)
  const sheetQuery = useEntrySheetQuery(() => isPlayer.value)
  const answerMutation = useAnswerEntryMutation()
  const refreshMutation = useRefreshEntryMutation()

  const actionError = ref('')

  const sheet = computed<EntrySheet | null>(() => sheetQuery.data.value ?? null)
  const questions = computed<EntryAttempt[]>(() => sheet.value?.questions ?? [])
  const loading = computed(() => isPlayer.value && sheetQuery.isPending.value)
  const answering = computed(() => answerMutation.isPending.value)
  const refreshing = computed(() => refreshMutation.isPending.value)
  const refreshesLeft = computed(() => sheet.value?.refreshes_left ?? 0)

  // No sheet yet (still loading, or the game has not started) must not lock a
  // player out of a map they were already allowed to use.
  const canClaimStart = computed(() => sheet.value?.can_claim_start ?? false)
  const needsEntrySheet = computed(() => isPlayer.value && sheet.value !== null && !canClaimStart.value)

  const error = computed(() => {
    if (actionError.value) {
      return actionError.value
    }
    return sheetQuery.error.value ? messageOf(sheetQuery.error.value) : ''
  })

  async function answer(code: string, value: number): Promise<boolean | null> {
    actionError.value = ''
    try {
      const result = await answerMutation.mutateAsync({ code, answer: value })
      return result.is_correct
    } catch (err) {
      actionError.value = messageOf(err)
      return null
    }
  }

  async function refresh(code: string): Promise<boolean> {
    actionError.value = ''
    try {
      await refreshMutation.mutateAsync(code)
      return true
    } catch (err) {
      actionError.value = messageOf(err)
      return false
    }
  }

  return {
    isOpen,
    open: openEntrySheet,
    close: closeEntrySheet,
    sheet,
    questions,
    loading,
    answering,
    refreshing,
    refreshesLeft,
    error,
    isPlayer,
    canClaimStart,
    needsEntrySheet,
    answer,
    refresh,
  }
}

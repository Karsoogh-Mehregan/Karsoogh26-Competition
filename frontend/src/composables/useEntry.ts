import { computed, ref } from 'vue'
import { ApiError } from '@/lib/http'
import { useMeQuery } from '@/queries/auth'
import {
  useAnswerEntryMutation,
  useEntrySheetQuery,
  useRetryEntryMutation,
} from '@/queries/entry'
import type { EntryAnswerResult, EntryAttempt, EntrySheet } from '@/types/api'

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
  const retryMutation = useRetryEntryMutation()

  const actionError = ref('')

  const sheet = computed<EntrySheet | null>(() => sheetQuery.data.value ?? null)
  const questions = computed<EntryAttempt[]>(() => sheet.value?.questions ?? [])
  const loading = computed(() => isPlayer.value && sheetQuery.isPending.value)
  const answering = computed(() => answerMutation.isPending.value)
  const retrying = computed(() => retryMutation.isPending.value)
  const retriesLeft = computed(() => sheet.value?.retries_left ?? 0)

  // No sheet yet (still loading, or the game has not started) must not lock a
  // player out of a map they were already allowed to use.
  const canClaimStart = computed(() => sheet.value?.can_claim_start ?? false)
  const needsEntrySheet = computed(() => isPlayer.value && sheet.value !== null && !canClaimStart.value)

  /**
   * Every question answered, every retry spent, and still short of the required
   * count: the sheet holds nothing left to click.
   *
   * This is not a refusal the player can work around — the only thing that opens
   * the map now is `entry_grace_over`, a clock on the server. So the map must
   * stop offering the sheet and say what is actually being waited for, rather
   * than sending the team back into a dialog with no live question in it.
   */
  const exhausted = computed(() => {
    const current = sheet.value
    if (!current || current.can_claim_start) return false
    if (current.retries_left > 0) return false
    return current.total_count > 0 && current.answered_count >= current.total_count
  })

  /** Projected wall clock of the grace end; null while the game is paused. */
  const graceEndsAt = computed(() => sheet.value?.grace_ends_at ?? null)

  const error = computed(() => {
    if (actionError.value) {
      return actionError.value
    }
    return sheetQuery.error.value ? messageOf(sheetQuery.error.value) : ''
  })

  /**
   * The whole graded sheet, not just the verdict on this answer.
   *
   * The caller needs to know whether *this* answer was the one that qualified
   * the team, and reading that back off the cache means racing the query
   * client's batched notification. The response already says so.
   */
  async function answer(code: string, value: number): Promise<EntryAnswerResult | null> {
    actionError.value = ''
    try {
      return await answerMutation.mutateAsync({ code, answer: value })
    } catch (err) {
      actionError.value = messageOf(err)
      return null
    }
  }

  async function retry(code: string): Promise<boolean> {
    actionError.value = ''
    try {
      await retryMutation.mutateAsync(code)
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
    retrying,
    retriesLeft,
    error,
    isPlayer,
    canClaimStart,
    needsEntrySheet,
    exhausted,
    graceEndsAt,
    answer,
    retry,
  }
}

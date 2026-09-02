import { computed, watch } from 'vue'
import { ApiError } from '@/lib/http'
import { useAttemptsQuery } from '@/queries/attempts'
import { useAttemptStore } from '@/stores/attempt'
import type { ActiveAttempt } from '@/types/api'
import { useActing } from './useActing'

function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'خطا در ارتباط با سرور.'
}

export function useAttempts() {
  const { me, actingTeam, isPlayer } = useActing()
  const store = useAttemptStore()

  const teamCode = computed(() => actingTeam.value?.code ?? me.value?.team?.code ?? null)
  const enabled = () => isPlayer.value && teamCode.value != null

  const attemptsQuery = useAttemptsQuery(teamCode, enabled)

  const questionAttempts = computed<ActiveAttempt[]>(() =>
    (attemptsQuery.data.value ?? []).filter((attempt) => attempt.status !== 'no_question'),
  )

  const selected = computed<ActiveAttempt | null>(() => {
    const id = store.selectedOccupancyId
    return questionAttempts.value.find((attempt) => attempt.id === id) ?? null
  })

  watch(questionAttempts, (list) => {
    if (list.length === 0) {
      store.select(null)
      return
    }
    if (!list.some((attempt) => attempt.id === store.selectedOccupancyId)) {
      store.select(list[0].id)
    }
  })

  const loading = computed(() => attemptsQuery.isPending.value)
  const error = computed(() =>
    attemptsQuery.error.value ? messageOf(attemptsQuery.error.value) : '',
  )

  function select(occupancyId: number | null): void {
    store.select(occupancyId)
  }

  return {
    questionAttempts,
    selected,
    loading,
    error,
    select,
  }
}

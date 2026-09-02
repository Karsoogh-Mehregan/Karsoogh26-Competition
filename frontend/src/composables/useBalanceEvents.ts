import { computed } from 'vue'
import { ApiError } from '@/lib/http'
import { useBalanceEventsQuery } from '@/queries/teams'
import type { BalanceEvent } from '@/types/api'
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

export function useBalanceEvents() {
  const { me, actingTeam, isPlayer } = useActing()
  const teamCode = computed(() => actingTeam.value?.code ?? me.value?.team?.code ?? null)
  const enabled = () => isPlayer.value && teamCode.value != null
  const query = useBalanceEventsQuery(teamCode, enabled)

  const events = computed<BalanceEvent[]>(() => query.data.value ?? [])
  const loading = computed(() => query.isPending.value)
  const error = computed(() => (query.error.value ? messageOf(query.error.value) : ''))

  return { events, loading, error }
}

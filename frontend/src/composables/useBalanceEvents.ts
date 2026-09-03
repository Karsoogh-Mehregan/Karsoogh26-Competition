import { computed } from 'vue'
import { useBalanceEventsQuery } from '@/queries/teams'
import { useActing } from './useActing'

export function useBalanceEvents() {
  const { actingTeam, isPlayer } = useActing()
  const teamCode = computed(() => actingTeam.value?.code ?? '')

  const query = useBalanceEventsQuery(() => isPlayer.value && !!teamCode.value, teamCode)

  return {
    balanceEvents: computed(() => query.data.value ?? []),
    ledgerLoading: query.isPending,
    ledgerError: computed(() =>
      query.error.value instanceof Error ? query.error.value.message : null,
    ),
  }
}

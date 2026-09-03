import { useQuery } from '@tanstack/vue-query'
import { computed, type ComputedRef, type Ref } from 'vue'
import { listAttempts } from '@/services/attempts'
import { queryKeys } from './keys'

export function useAttemptsQuery(
  teamCode: Ref<string | null> | ComputedRef<string | null>,
  enabled: () => boolean,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.attempts(teamCode.value ?? '')),
    queryFn: ({ signal }) => listAttempts(teamCode.value as string, signal),
    enabled: () => enabled() && teamCode.value != null,
    refetchInterval: 15_000,
  })
}

import { computed } from 'vue'
import { ApiError } from '@/lib/http'
import { useItemsQuery } from '@/queries/items'
import type { TeamItem } from '@/types/api'
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

export function useItems() {
  const { isPlayer } = useActing()
  const query = useItemsQuery(() => isPlayer.value)

  return {
    items: computed<TeamItem[]>(() => query.data.value ?? []),
    loading: computed(() => query.isPending.value),
    error: computed(() => (query.error.value ? messageOf(query.error.value) : '')),
  }
}

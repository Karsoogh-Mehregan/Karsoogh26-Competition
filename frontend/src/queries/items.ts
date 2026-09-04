import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { listItems, useItem } from '@/services/items'
import type { UseItemPayload, UseItemResult } from '@/types/api'
import { detach } from './invalidate'
import { queryKeys } from './keys'

export function useItemsQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.items(),
    queryFn: ({ signal }) => listItems(signal),
    enabled,
  })
}

export function useItemMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: UseItemPayload) => useItem(payload),
    onSuccess: (_result: UseItemResult, payload: UseItemPayload) => {
      const tasks = [queryClient.invalidateQueries({ queryKey: queryKeys.items() })]
      if (payload.item_type !== 'gilari_100') {
        tasks.push(
          queryClient.invalidateQueries({ queryKey: queryKeys.teamsRoot() }),
          queryClient.invalidateQueries({ queryKey: queryKeys.attemptsRoot() }),
        )
      }
      detach(tasks)
    },
  })
}

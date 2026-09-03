import { useQuery } from '@tanstack/vue-query'
import { listItems } from '@/services/items'
import { queryKeys } from './keys'

export function useItemsQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.items(),
    queryFn: ({ signal }) => listItems(signal),
    enabled,
  })
}

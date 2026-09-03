import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { getMapDesign, updateMapDesign, updateNodeDesign } from '@/services/design'
import type { MapDesign, MapDesignPatch, NodeDesign, NodeDesignPatch } from '@/types/api'
import { queryKeys } from './keys'

export function useMapDesignQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.mapDesign(),
    queryFn: ({ signal }) => getMapDesign(signal),
    enabled,
    // Changes arrive as `map.design` SSE frames; there is nothing to poll for.
    staleTime: Infinity,
  })
}

export function useUpdateMapDesignMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: MapDesignPatch) => updateMapDesign(changes),
    onSuccess: (design: MapDesign) => {
      queryClient.setQueryData<MapDesign>(queryKeys.mapDesign(), design)
    },
  })
}

export interface UpdateNodeDesignVariables {
  nodeCode: string
  changes: NodeDesignPatch
}

export function useUpdateNodeDesignMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ nodeCode, changes }: UpdateNodeDesignVariables) =>
      updateNodeDesign(nodeCode, changes),
    onSuccess: (node: NodeDesign) => {
      // Patch the one row in place rather than refetching 473 of them.
      queryClient.setQueryData<MapDesign>(queryKeys.mapDesign(), (design) =>
        design
          ? { ...design, nodes: design.nodes.map((row) => (row.code === node.code ? node : row)) }
          : design,
      )
    },
  })
}

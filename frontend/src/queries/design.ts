import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useBoard } from '@/composables/useBoard'
import { streamConnected } from '@/lib/boardStreamState'
import { getMapDesign, updateMapDesign, updateNodeDesign } from '@/services/design'
import type { MapDesign, MapDesignPatch, NodeDesign, NodeDesignPatch } from '@/types/api'
import { queryKeys } from './keys'

export function useMapDesignQuery(enabled: () => boolean) {
  const { board } = useBoard()
  return useQuery({
    queryKey: computed(() => queryKeys.mapDesign(board.value)),
    queryFn: ({ signal }) => getMapDesign(board.value, signal),
    enabled,
    // Changes arrive as `map.design` SSE frames; polling only covers the gap
    // while the stream is down.
    staleTime: Infinity,
    refetchInterval: computed(() => (streamConnected.value ? false : 60_000)),
  })
}

export function useUpdateMapDesignMutation() {
  const queryClient = useQueryClient()
  const { board } = useBoard()
  return useMutation({
    mutationFn: (changes: MapDesignPatch) => updateMapDesign(changes),
    onSuccess: (design: MapDesign) => {
      queryClient.setQueryData<MapDesign>(queryKeys.mapDesign(board.value), design)
      // The settings half is shared by both boards, so the other board's cached
      // copy is now stale. Mark it, but do not refetch what nobody is looking at.
      void queryClient.invalidateQueries({
        queryKey: queryKeys.mapDesignRoot(),
        refetchType: 'none',
      })
    },
  })
}

export interface UpdateNodeDesignVariables {
  nodeCode: string
  changes: NodeDesignPatch
}

export function useUpdateNodeDesignMutation() {
  const queryClient = useQueryClient()
  const { board } = useBoard()
  return useMutation({
    mutationFn: ({ nodeCode, changes }: UpdateNodeDesignVariables) =>
      updateNodeDesign(nodeCode, changes),
    onSuccess: (node: NodeDesign) => {
      // Patch the one row in place rather than refetching hundreds of them.
      queryClient.setQueryData<MapDesign>(queryKeys.mapDesign(board.value), (design) =>
        design
          ? { ...design, nodes: design.nodes.map((row) => (row.code === node.code ? node : row)) }
          : design,
      )
      // The write landed on every board's copy of the node, so the board that
      // is not on screen now holds a stale row.
      void queryClient.invalidateQueries({
        queryKey: queryKeys.mapDesignRoot(),
        refetchType: 'none',
      })
    },
  })
}

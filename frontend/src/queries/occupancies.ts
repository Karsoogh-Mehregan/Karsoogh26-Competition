import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import type { Ref } from 'vue'
import { getOccupancyQuestion, submitAnswer } from '@/services/occupancies'
import type { SubmitAnswerPayload } from '@/services/occupancies'
import type { SubmitCreated } from '@/types/api'
import { queryKeys } from './keys'

export function useOccupancyQuestionQuery(occupancyId: Ref<number | null>) {
  return useQuery({
    queryKey: [...queryKeys.occupancyQuestion(), occupancyId] as const,
    queryFn: ({ signal }) => getOccupancyQuestion(occupancyId.value as number, signal),
    enabled: () => occupancyId.value !== null,
  })
}

export interface SubmitAnswerVariables {
  occupancyId: number
  payload: SubmitAnswerPayload
}

export function useSubmitAnswerMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ occupancyId, payload }: SubmitAnswerVariables) =>
      submitAnswer(occupancyId, payload),
    onSuccess: (_result: SubmitCreated) => {
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.occupancyQuestion() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.submissions() }),
      ])
    },
  })
}

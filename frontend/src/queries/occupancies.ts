import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { submitAnswer } from '@/services/occupancies'
import type { SubmitAnswerPayload } from '@/services/occupancies'
import type { SubmitCreated } from '@/types/api'
import { detach } from './invalidate'
import { queryKeys } from './keys'

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
      detach([
        queryClient.invalidateQueries({ queryKey: queryKeys.attemptsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.teamsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.submissions() }),
      ])
    },
  })
}

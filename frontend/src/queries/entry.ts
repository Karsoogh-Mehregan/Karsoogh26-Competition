import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { answerEntryQuestion, getEntrySheet, retryEntryQuestion } from '@/services/entry'
import type { EntryAnswerResult, EntrySheet } from '@/types/api'
import { detach } from './invalidate'
import { queryKeys } from './keys'

export function useEntrySheetQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.entrySheet(),
    queryFn: ({ signal }) => getEntrySheet(signal),
    enabled,
    // The sheet's *questions* are drawn once and only ever change when this
    // client answers — but `can_claim_start` is not only about answers: it also
    // flips on its own when `entry_grace_over` does, on a clock the server owns.
    // A team that spent every retry is waiting on exactly that, so poll while
    // the gate is still shut and stop the moment it opens.
    staleTime: 15_000,
    refetchInterval: (query) => (query.state.data?.can_claim_start ? false : 15_000),
    retry: false,
  })
}

export interface AnswerEntryVariables {
  code: string
  answer: number
}

export function useAnswerEntryMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ code, answer }: AnswerEntryVariables) => answerEntryQuestion(code, answer),
    onSuccess: (result: EntryAnswerResult) => {
      queryClient.setQueryData(queryKeys.entrySheet(), result)
      // Qualifying stamps draft_order on the team row.
      detach(queryClient.invalidateQueries({ queryKey: queryKeys.teamsRoot() }))
    },
  })
}

export function useRetryEntryMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (code: string) => retryEntryQuestion(code),
    onSuccess: (sheet: EntrySheet) => {
      queryClient.setQueryData(queryKeys.entrySheet(), sheet)
    },
  })
}

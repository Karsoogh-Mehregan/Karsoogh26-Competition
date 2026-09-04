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
    // The sheet is drawn on the first read and only ever changes when this
    // client answers, so there is nothing to poll for.
    staleTime: Infinity,
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

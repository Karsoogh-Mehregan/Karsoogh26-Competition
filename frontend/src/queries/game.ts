import { computed } from 'vue'
import { streamConnected } from '@/lib/boardStreamState'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import {
  assignQuestion,
  getSubmission,
  gradeSubmission,
  listLevels,
  listSubmissions,
} from '@/services/game'
import type { AssignQuestionResult, GradeResult } from '@/types/api'
import { detach } from './invalidate'
import { queryKeys } from './keys'

export interface AssignQuestionVariables {
  teamCode: string
  nodeCode: string
}

export function useAssignQuestionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ teamCode, nodeCode }: AssignQuestionVariables) =>
      assignQuestion(teamCode, nodeCode),
    onSuccess: (_result: AssignQuestionResult) => {
      detach([
        queryClient.invalidateQueries({ queryKey: queryKeys.teamsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.attemptsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.submissions() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.balanceEventsRoot() }),
      ])
    },
  })
}

export function useSubmissionsQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.submissions(),
    queryFn: ({ signal }) => listSubmissions(signal),
    enabled,
    // A mentor sits on this page waiting for work to arrive, so the queue must
    // not depend on the stream alone.
    refetchInterval: computed(() => (streamConnected.value ? false : 10_000)),
  })
}

export function useSubmissionQuery(id: () => number | null) {
  return useQuery({
    queryKey: computed(() => queryKeys.submission(id() ?? 0)),
    queryFn: ({ signal }) => getSubmission(id() as number, signal),
    enabled: () => id() != null,
  })
}

export interface GradeSubmissionVariables {
  submissionId: number
  grade: number
  weakReasoning?: boolean
}

export function useGradeSubmissionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ submissionId, grade, weakReasoning }: GradeSubmissionVariables) =>
      gradeSubmission(submissionId, grade, { weakReasoning }),
    onSuccess: (_result: GradeResult) => {
      detach([
        queryClient.invalidateQueries({ queryKey: queryKeys.submissions() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.teamsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.attemptsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.balanceEventsRoot() }),
      ])
    },
  })
}

export function useLevelsQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.levels(),
    queryFn: ({ signal }) => listLevels(signal),
    enabled,
    staleTime: Infinity,
  })
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { assignQuestion, gradeSubmission, listLevels, listSubmissions } from '@/services/game'
import type { AssignQuestionResult, GradeResult } from '@/types/api'
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
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.teams() }),
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
  })
}

export interface GradeSubmissionVariables {
  submissionId: number
  grade: number
}

export function useGradeSubmissionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ submissionId, grade }: GradeSubmissionVariables) =>
      gradeSubmission(submissionId, grade),
    onSuccess: (_result: GradeResult) => {
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.submissions() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.teams() }),
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

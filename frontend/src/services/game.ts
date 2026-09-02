import { get, post } from '@/lib/http'
import type { AssignQuestionResult, GradeResult, LevelConfigRow, SubmissionRow } from '@/types/api'

export function listLevels(signal?: AbortSignal): Promise<LevelConfigRow[]> {
  return get<LevelConfigRow[]>('/levels/', signal)
}

export function assignQuestion(
  teamCode: string,
  nodeCode: string,
): Promise<AssignQuestionResult> {
  return post<AssignQuestionResult>(
    `/teams/${encodeURIComponent(teamCode)}/nodes/${encodeURIComponent(nodeCode)}/assign-question/`,
    {},
  )
}

export function listSubmissions(signal?: AbortSignal): Promise<SubmissionRow[]> {
  return get<SubmissionRow[]>('/submissions/', signal)
}

export function gradeSubmission(submissionId: number, grade: number): Promise<GradeResult> {
  return post<GradeResult>(`/submissions/${submissionId}/grade/`, { grade })
}

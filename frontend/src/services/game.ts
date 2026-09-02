import { get, patch, post } from '@/lib/http'
import type {
  AssignQuestionResult,
  GameRestartResult,
  GameSettings,
  GameState,
  GradeResult,
  SubmissionRow,
} from '@/types/api'

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

export function getGameState(signal?: AbortSignal): Promise<GameState> {
  return get<GameState>('/game/state/', signal)
}

export function getGameSettings(signal?: AbortSignal): Promise<GameSettings> {
  return get<GameSettings>('/game/settings/', signal)
}

export function updateGameSettings(changes: Partial<GameSettings>): Promise<GameSettings> {
  return patch<GameSettings>('/game/settings/', changes)
}

export function restartGame(): Promise<GameRestartResult> {
  return post<GameRestartResult>('/game/restart/', { confirm: true })
}

import { get, patch, post } from '@/lib/http'
import type {
  AssignQuestionResult,
  GameExtendResult,
  GameRestartResult,
  GameSettings,
  GameState,
  GradeResult,
  LevelConfigRow,
  SubmissionDetail,
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

export function getSubmission(id: number, signal?: AbortSignal): Promise<SubmissionDetail> {
  return get<SubmissionDetail>(`/submissions/${id}/`, signal)
}

export function gradeSubmission(
  submissionId: number,
  grade: number,
  options?: { weakReasoning?: boolean },
): Promise<GradeResult> {
  return post<GradeResult>(`/submissions/${submissionId}/grade/`, {
    grade,
    ...(options?.weakReasoning ? { weak_reasoning: true } : {}),
  })
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

/**
 * Grant `minutes` more play, counted from now.
 *
 * Deliberately not a PATCH of `duration_minutes`: the new total depends on how
 * much has been played at the instant it lands, and a client that computed it
 * would be racing a clock that moves while the organiser types.
 */
export function extendGame(minutes: number): Promise<GameExtendResult> {
  return post<GameExtendResult>('/game/extend/', { minutes })
}

export function restartGame(): Promise<GameRestartResult> {
  return post<GameRestartResult>('/game/restart/', { confirm: true })
}

export function listLevels(signal?: AbortSignal): Promise<LevelConfigRow[]> {
  return get<LevelConfigRow[]>('/levels/', signal)
}

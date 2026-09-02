import { post, postForm } from '@/lib/http'
import type { SubmitCreated } from '@/types/api'

export interface SubmitAnswerPayload {
  body?: string
  file?: File | null
}

export function submitAnswer(
  occupancyId: number,
  payload: SubmitAnswerPayload,
): Promise<SubmitCreated> {
  if (payload.file) {
    const form = new FormData()
    if (payload.body) {
      form.append('body', payload.body)
    }
    form.append('file', payload.file)
    return postForm<SubmitCreated>(`/occupancies/${occupancyId}/submit/`, form)
  }
  return post<SubmitCreated>(`/occupancies/${occupancyId}/submit/`, { body: payload.body ?? '' })
}

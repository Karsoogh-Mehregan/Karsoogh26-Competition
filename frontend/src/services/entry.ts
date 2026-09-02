import { get, post } from '@/lib/http'
import type { EntryAnswerResult, EntrySheet } from '@/types/api'

export function getEntrySheet(signal?: AbortSignal): Promise<EntrySheet> {
  return get<EntrySheet>('/entry/sheet/', signal)
}

export function answerEntryQuestion(code: string, answer: number): Promise<EntryAnswerResult> {
  return post<EntryAnswerResult>(`/entry/questions/${encodeURIComponent(code)}/answer/`, {
    answer,
  })
}

export function retryEntryQuestion(code: string): Promise<EntrySheet> {
  return post<EntrySheet>(`/entry/questions/${encodeURIComponent(code)}/retry/`)
}

import { del, get, patch, post } from '@/lib/http'
import type {
  AudienceOptions,
  AudiencePreview,
  AudienceSelection,
  Inbox,
  Message,
  MessageDraft,
  ReadResult,
  SendResult,
} from '@/types/api'

export function getInbox(signal?: AbortSignal): Promise<Inbox> {
  return get<Inbox>('/notifications/', signal)
}

export function markRead(ids: number[]): Promise<ReadResult> {
  return post<ReadResult>('/notifications/read/', { ids })
}

export function markAllRead(): Promise<ReadResult> {
  return post<ReadResult>('/notifications/read-all/')
}

export function listMessages(
  status?: 'draft' | 'sent',
  signal?: AbortSignal,
): Promise<Message[]> {
  const query = status ? `?status=${status}` : ''
  return get<Message[]>(`/messages/${query}`, signal)
}

export function getAudienceOptions(signal?: AbortSignal): Promise<AudienceOptions> {
  return get<AudienceOptions>('/messages/audiences/', signal)
}

export function createMessage(draft: MessageDraft): Promise<Message | SendResult> {
  return post<Message | SendResult>('/messages/', draft)
}

export function updateMessage(id: number, draft: Partial<MessageDraft>): Promise<Message> {
  return patch<Message>(`/messages/${id}/`, draft)
}

export function deleteMessage(id: number): Promise<void> {
  return del<void>(`/messages/${id}/`)
}

export function previewAudience(selection: AudienceSelection): Promise<AudiencePreview> {
  return post<AudiencePreview>('/messages/audience-preview/', selection)
}

export function sendMessage(id: number): Promise<SendResult> {
  return post<SendResult>(`/messages/${id}/send/`)
}

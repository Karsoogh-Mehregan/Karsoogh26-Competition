import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed } from 'vue'
import { streamConnected } from '@/lib/boardStreamState'
import {
  createMessage,
  deleteMessage,
  getAudienceOptions,
  getInbox,
  listMessages,
  markAllRead,
  markRead,
  sendMessage,
  updateMessage,
} from '@/services/notifications'
import type { Inbox, Message, MessageDraft, ReadResult, SendResult } from '@/types/api'
import { queryKeys } from './keys'

// The stream is the live path; this only covers the window where it is down.
// Shorter than the board's 15s because an unseen message is worse than a stale
// balance — a team waiting on an announcement is waiting on nothing else.
const INBOX_POLL_MS = 10_000

export function useInboxQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.inbox(),
    queryFn: ({ signal }) => getInbox(signal),
    enabled,
    refetchInterval: computed(() => (streamConnected.value ? false : INBOX_POLL_MS)),
    refetchOnWindowFocus: true,
  })
}

export function useMarkReadMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (ids: number[]) => markRead(ids),
    // Grey the card the instant it is opened; the refetch below settles it.
    onMutate: (ids: number[]) => {
      const marked = new Set(ids)
      queryClient.setQueryData<Inbox>(queryKeys.inbox(), (inbox) => {
        if (!inbox) return inbox
        const now = new Date().toISOString()
        const results = inbox.results.map((item) =>
          marked.has(item.id) && !item.is_read
            ? { ...item, is_read: true, read_at: now }
            : item,
        )
        const unread = results.filter((item) => !item.is_read).length
        return { ...inbox, results, unread }
      })
    },
    onSettled: (_result?: ReadResult) =>
      queryClient.invalidateQueries({ queryKey: queryKeys.inbox() }),
  })
}

export function useMarkAllReadMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => markAllRead(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.inbox() }),
  })
}

// ---- composer --------------------------------------------------------------

export function useMessagesQuery(status: 'draft' | 'sent', enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.messages(status),
    queryFn: ({ signal }) => listMessages(status, signal),
    enabled,
  })
}

export function useAudienceOptionsQuery(enabled: () => boolean) {
  return useQuery({
    queryKey: queryKeys.audienceOptions(),
    queryFn: ({ signal }) => getAudienceOptions(signal),
    enabled,
    // Teams and accounts are made before kick-off and barely move after.
    staleTime: 5 * 60_000,
  })
}

function invalidateBoxes(queryClient: ReturnType<typeof useQueryClient>) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.messagesRoot() }),
    // The author is not a recipient, but a send changes what everyone else
    // sees — and an announcer reading their own inbox in another tab counts.
    queryClient.invalidateQueries({ queryKey: queryKeys.inbox() }),
  ])
}

export function useCreateMessageMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (draft: MessageDraft) => createMessage(draft),
    onSuccess: () => invalidateBoxes(queryClient),
  })
}

export interface UpdateMessageVariables {
  id: number
  draft: Partial<MessageDraft>
}

export function useUpdateMessageMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, draft }: UpdateMessageVariables) => updateMessage(id, draft),
    onSuccess: (_message: Message) => invalidateBoxes(queryClient),
  })
}

export function useDeleteMessageMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteMessage(id),
    onSuccess: () => invalidateBoxes(queryClient),
  })
}

export function useSendMessageMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => sendMessage(id),
    onSuccess: (_result: SendResult) => invalidateBoxes(queryClient),
  })
}

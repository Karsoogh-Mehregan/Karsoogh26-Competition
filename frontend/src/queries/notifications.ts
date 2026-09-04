import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed } from 'vue'
import { streamConnected } from '@/lib/boardStreamState'
import {
  createMessage,
  deleteMessage,
  getAudienceOptions,
  getInbox,
  getMessageRecipients,
  getNotification,
  listMessages,
  markAllRead,
  markRead,
  previewAudience,
  sendMessage,
  updateMessage,
} from '@/services/notifications'
import type {
  AudienceSelection,
  Inbox,
  Message,
  MessageDraft,
  ReadResult,
  SendResult,
} from '@/types/api'
import { detach } from './invalidate'
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

/**
 * One message for its own page.
 *
 * Seeded from the inbox list when that is already cached, so opening a card is
 * instant and the request only fills in what a deep link cannot know.
 */
export function useNotificationQuery(id: () => number, enabled: () => boolean) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: computed(() => queryKeys.notification(id())),
    queryFn: ({ signal }) => getNotification(id(), signal),
    enabled,
    initialData: () =>
      queryClient
        .getQueryData<Inbox>(queryKeys.inbox())
        ?.results.find((item) => item.id === id()),
  })
}

export function useMessageRecipientsQuery(id: () => number, enabled: () => boolean) {
  return useQuery({
    queryKey: computed(() => queryKeys.messageRecipients(id())),
    queryFn: ({ signal }) => getMessageRecipients(id(), signal),
    enabled,
    // Read receipts age quickly while a sender is watching them.
    refetchInterval: 15_000,
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
      Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.inbox() }),
        // The detail page shows its own read state, and the sender's receipts
        // list is now stale for whoever is watching it.
        queryClient.invalidateQueries({ queryKey: ['notification'] }),
        queryClient.invalidateQueries({ queryKey: ['message-recipients'] }),
      ]),
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
  detach([
    queryClient.invalidateQueries({ queryKey: queryKeys.messagesRoot() }),
    // The author is not a recipient, but a send changes what everyone else
    // sees — and an announcer reading their own inbox in another tab counts.
    queryClient.invalidateQueries({ queryKey: queryKeys.inbox() }),
  ])
}

/**
 * "This would reach N people", recomputed as the picker changes.
 *
 * A query rather than a mutation so the answer is cached per selection: tick a
 * box, untick it, and the first result comes straight back. `enabled` keeps it
 * quiet while nothing is selected, where the answer is trivially zero.
 */
export function useAudiencePreviewQuery(
  selection: () => AudienceSelection,
  enabled: () => boolean,
) {
  return useQuery({
    queryKey: computed(() => {
      const { scopes, teams, users } = selection()
      return queryKeys.audiencePreview(
        [scopes.join('+'), teams.join('+'), users.join('+')].join('|'),
      )
    }),
    queryFn: () => previewAudience(selection()),
    enabled,
    staleTime: 30_000,
  })
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

/**
 * The bell, the panel behind it, and the interruption when something arrives.
 *
 * Split in two on purpose. `useNotifications()` is safe to call from any
 * component — TanStack dedupes the query by key, so the bell and the panel
 * share one request. `useNotificationAnnouncer()` owns the side effects (the
 * toast and the browser's own tray) and must be called exactly once, from a
 * component that outlives the session: App.vue. Mounting the watcher in the
 * panel instead would mean no toast whenever the panel happened to be closed,
 * which is precisely when one is wanted.
 */
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'

import * as desktop from '@/lib/browserNotify'
import { useMeQuery } from '@/queries/auth'
import {
  useInboxQuery,
  useMarkAllReadMutation,
  useMarkReadMutation,
} from '@/queries/notifications'
import type { InboxItem } from '@/types/api'

/** Panel visibility is UI state shared by two sibling components, nothing more. */
const panelOpen = ref(false)

/**
 * Ids already accounted for. Seeded on the first successful load so a page
 * refresh does not replay a backlog as fresh arrivals.
 */
const seen = new Set<number>()
let seeded = false

export function useNotifications() {
  const meQuery = useMeQuery()
  const enabled = () => meQuery.data.value != null
  const inboxQuery = useInboxQuery(enabled)

  const markReadMutation = useMarkReadMutation()
  const markAllReadMutation = useMarkAllReadMutation()

  const items = computed<InboxItem[]>(() => inboxQuery.data.value?.results ?? [])
  const unread = computed(() => inboxQuery.data.value?.unread ?? 0)
  const hasUnread = computed(() => unread.value > 0)
  const loading = computed(() => enabled() && inboxQuery.isPending.value)

  function open() {
    panelOpen.value = true
  }

  function close() {
    panelOpen.value = false
  }

  function toggle() {
    panelOpen.value = !panelOpen.value
  }

  /** Opening a card is what marks it read; an unread one is only sent once. */
  function read(item: InboxItem) {
    if (item.is_read) return
    markReadMutation.mutate([item.id])
  }

  function readAll() {
    if (!hasUnread.value) return
    markAllReadMutation.mutate()
  }

  return {
    items,
    unread,
    hasUnread,
    loading,
    error: computed(() => inboxQuery.error.value),
    panelOpen,
    open,
    close,
    toggle,
    read,
    readAll,
    markingAll: computed(() => markAllReadMutation.isPending.value),
  }
}

/** Call once, from App.vue. */
export function useNotificationAnnouncer() {
  const { items, open } = useNotifications()

  watch(
    items,
    (current) => {
      if (current.length === 0 && !seeded) return

      const fresh = current.filter((item) => !item.is_read && !seen.has(item.id))
      for (const item of current) {
        seen.add(item.id)
      }

      // First load is history, not news.
      if (!seeded) {
        seeded = true
        return
      }
      if (fresh.length === 0) return

      announce(fresh, open)
    },
    { immediate: true },
  )
}

function announce(fresh: InboxItem[], open: () => void): void {
  const newest = fresh[0]

  const title =
    fresh.length === 1 ? newest.title : `${fresh.length} پیام تازه دارید`
  const description = fresh.length === 1 ? newest.excerpt : newest.title

  toast.info(title, {
    description,
    duration: 8000,
    action: {
      label: 'دیدن',
      onClick: () => open(),
    },
  })

  // The tray only fires if the user granted it from the panel's own button.
  // One notice per burst, tagged so a second replaces rather than stacks.
  desktop.show({
    title: fresh.length === 1 ? newest.title : `${fresh.length} پیام تازه`,
    body: fresh.length === 1 ? newest.excerpt : newest.title,
    tag: 'karsoogh-inbox',
  })
}

/**
 * The tray permission, as the panel's button sees it. Kept here rather than in
 * the component so the label re-renders after the browser answers.
 */
export function useDesktopPermission() {
  const state = ref<desktop.NotifyPermission>(desktop.permission())

  async function request() {
    state.value = await desktop.requestPermission()
    if (state.value === 'granted') {
      toast.success('اعلان مرورگر فعال شد')
    } else if (state.value === 'denied') {
      toast.error('اعلان مرورگر رد شد. از تنظیمات مرورگر می‌توانید دوباره اجازه دهید.')
    }
  }

  return {
    state,
    canAsk: computed(() => state.value === 'default'),
    isGranted: computed(() => state.value === 'granted'),
    isDenied: computed(() => state.value === 'denied'),
    isSupported: computed(() => state.value !== 'unsupported'),
    request,
  }
}

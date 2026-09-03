<script setup lang="ts">
/**
 * The inbox, as a drawer.
 *
 * Reads like mail: unread cards sit on the card background with an accent bar
 * and a filled dot, read ones fade back into the page. Clicking one expands it
 * in place and marks it read — the body already shipped with the list, so
 * opening a message costs nothing.
 */
import {
  BellIcon,
  BellOffIcon,
  CheckCheckIcon,
  ChevronDownIcon,
  InboxIcon,
  Loader2Icon,
  MegaphoneIcon,
  SettingsIcon,
} from '@lucide/vue'
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { useDesktopPermission, useNotifications } from '@/composables/useNotifications'
import { formatRelativeTime } from '@/lib/format'
import type { InboxItem } from '@/types/api'

const { items, unread, hasUnread, loading, panelOpen, close, read, readAll, markingAll } =
  useNotifications()
const permission = useDesktopPermission()
const { isAnnouncer } = useActing()
const router = useRouter()

const expanded = ref<number | null>(null)

// A relative timestamp that never updates is a lie within the minute. One
// ticking clock for the whole list, and only while the drawer is open.
const now = ref(Date.now())
let ticker: ReturnType<typeof setInterval> | null = null

watch(panelOpen, (open) => {
  if (open) {
    now.value = Date.now()
    ticker ??= setInterval(() => (now.value = Date.now()), 30_000)
  } else if (ticker !== null) {
    clearInterval(ticker)
    ticker = null
    expanded.value = null
  }
})

function onOpenChange(open: boolean) {
  if (!open) close()
}

function toggleCard(item: InboxItem) {
  expanded.value = expanded.value === item.id ? null : item.id
  read(item)
}

function goToComposer() {
  close()
  router.push({ name: 'messages' })
}

/** A rough sense of what the message is about, before reading it. */
function iconFor(item: InboxItem) {
  return item.kind === 'announcement' ? MegaphoneIcon : InboxIcon
}
</script>

<template>
  <Sheet :open="panelOpen" @update:open="onOpenChange">
    <SheetContent side="left" class="inbox-sheet sm:max-w-md" dir="rtl">
      <SheetHeader class="inbox-head">
        <SheetTitle class="flex items-center gap-2 text-base">
          <BellIcon class="size-4" aria-hidden="true" />
          پیام‌ها
          <span v-if="hasUnread" class="inbox-count">{{ unread }}</span>
        </SheetTitle>
        <SheetDescription class="text-xs">
          اعلان‌های خودکار بازی و پیام‌های مدیران.
        </SheetDescription>

        <div class="inbox-actions">
          <Button
            variant="ghost"
            size="sm"
            :disabled="!hasUnread || markingAll"
            @click="readAll"
          >
            <Loader2Icon v-if="markingAll" class="size-3.5 animate-spin" />
            <CheckCheckIcon v-else class="size-3.5" />
            خواندن همه
          </Button>
          <Button v-if="isAnnouncer" variant="ghost" size="sm" @click="goToComposer">
            <SettingsIcon class="size-3.5" />
            ارسال پیام
          </Button>
        </div>

        <!-- Asked for behind a button, never on load: an unprompted permission
             prompt is the fastest route to a permanent block. -->
        <button
          v-if="permission.canAsk.value"
          type="button"
          class="inbox-permission"
          @click="permission.request()"
        >
          <BellIcon class="size-3.5 shrink-0" aria-hidden="true" />
          <span>برای دریافت اعلان روی مرورگر، اجازه دهید</span>
        </button>
        <p v-else-if="permission.isDenied.value" class="inbox-permission is-denied">
          <BellOffIcon class="size-3.5 shrink-0" aria-hidden="true" />
          <span>اعلان مرورگر رد شده است؛ از تنظیمات سایت می‌توانید دوباره اجازه دهید.</span>
        </p>
      </SheetHeader>

      <div class="inbox-list">
        <template v-if="loading">
          <Skeleton v-for="n in 4" :key="n" class="h-20 w-full rounded-lg" />
        </template>

        <p v-else-if="items.length === 0" class="inbox-empty">
          <InboxIcon class="size-8 opacity-40" aria-hidden="true" />
          هنوز پیامی ندارید.
        </p>

        <article
          v-for="item in items"
          v-else
          :key="item.id"
          class="inbox-card"
          :class="{ 'is-read': item.is_read, 'is-open': expanded === item.id }"
        >
          <button
            type="button"
            class="inbox-card-head"
            :aria-expanded="expanded === item.id"
            @click="toggleCard(item)"
          >
            <span class="inbox-card-icon" aria-hidden="true">
              <component :is="iconFor(item)" class="size-4" />
            </span>

            <span class="inbox-card-text">
              <span class="inbox-card-meta">
                <span class="inbox-card-sender">{{ item.sender }}</span>
                <span class="inbox-card-time">{{
                  formatRelativeTime(item.sent_at ?? item.created_at, now)
                }}</span>
              </span>
              <span class="inbox-card-title">{{ item.title }}</span>
              <span v-if="expanded !== item.id" class="inbox-card-excerpt">{{ item.excerpt }}</span>
            </span>

            <span class="inbox-card-side">
              <!-- The unread mark the brief asked for: greyness alone is not a
                   symbol, and colour alone is not accessible. -->
              <span
                v-if="!item.is_read"
                class="inbox-card-unread"
                title="خوانده‌نشده"
                aria-label="خوانده‌نشده"
              />
              <ChevronDownIcon class="inbox-card-chevron size-4" aria-hidden="true" />
            </span>
          </button>

          <p v-if="expanded === item.id" class="inbox-card-body">{{ item.body || '—' }}</p>
        </article>
      </div>
    </SheetContent>
  </Sheet>
</template>

<style scoped>
.inbox-sheet {
  gap: 0;
  padding: 0;
}

.inbox-head {
  gap: 0.4rem;
  padding: 1rem 1rem 0.75rem;
  border-block-end: 1px solid var(--border);
}

.inbox-count {
  display: inline-grid;
  place-items: center;
  min-inline-size: 1.25rem;
  padding-inline: 0.35rem;
  border-radius: 9999px;
  background: var(--destructive);
  color: #fff;
  font-size: 0.6875rem;
  font-weight: 700;
}

.inbox-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-block-start: 0.15rem;
}

.inbox-permission {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-block-start: 0.35rem;
  padding: 0.45rem 0.6rem;
  border: 1px dashed var(--border);
  border-radius: 0.5rem;
  background: color-mix(in oklab, var(--muted) 45%, transparent);
  color: var(--muted-foreground);
  font-size: 0.72rem;
  text-align: start;
}
button.inbox-permission:hover {
  color: var(--foreground);
  border-color: var(--ring);
}
.inbox-permission.is-denied {
  border-style: solid;
}

.inbox-list {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  min-block-size: 0;
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 0.6rem;
}

.inbox-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  margin: 3rem 0;
  color: var(--muted-foreground);
  font-size: 0.8rem;
}

/* ---- card ---- */
.inbox-card {
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  background: var(--card);
  overflow: hidden;
  /* The accent bar runs down the reading edge, which is the right in RTL. */
  border-inline-start: 3px solid var(--primary);
  transition: opacity 0.15s ease, border-color 0.15s ease;
}
.inbox-card.is-read {
  border-inline-start-color: transparent;
  background: transparent;
  opacity: 0.62;
}
.inbox-card.is-read:hover {
  opacity: 0.85;
}

.inbox-card-head {
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  inline-size: 100%;
  padding: 0.6rem 0.7rem;
  text-align: start;
  cursor: pointer;
}

.inbox-card-icon {
  display: grid;
  place-items: center;
  inline-size: 1.75rem;
  block-size: 1.75rem;
  flex-shrink: 0;
  border-radius: 9999px;
  background: var(--muted);
  color: var(--muted-foreground);
}
.inbox-card:not(.is-read) .inbox-card-icon {
  background: color-mix(in oklab, var(--primary) 16%, transparent);
  color: var(--primary);
}

.inbox-card-text {
  display: flex;
  min-inline-size: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 0.1rem;
}

.inbox-card-meta {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
  font-size: 0.6875rem;
  color: var(--muted-foreground);
}
.inbox-card-sender {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.inbox-card-time {
  margin-inline-start: auto;
  flex-shrink: 0;
}

.inbox-card-title {
  font-size: 0.82rem;
  font-weight: 700;
  line-height: 1.45;
}
.inbox-card.is-read .inbox-card-title {
  font-weight: 500;
}

.inbox-card-excerpt {
  color: var(--muted-foreground);
  font-size: 0.72rem;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.inbox-card-side {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  flex-shrink: 0;
  padding-block-start: 0.15rem;
  color: var(--muted-foreground);
}

.inbox-card-unread {
  inline-size: 0.5rem;
  block-size: 0.5rem;
  border-radius: 9999px;
  background: var(--destructive);
}

.inbox-card-chevron {
  transition: transform 0.15s ease;
}
.inbox-card.is-open .inbox-card-chevron {
  transform: rotate(180deg);
}

.inbox-card-body {
  margin: 0;
  padding: 0 0.7rem 0.7rem 3rem;
  color: var(--foreground);
  font-size: 0.78rem;
  line-height: 1.75;
  white-space: pre-wrap;
}

@media (prefers-reduced-motion: reduce) {
  .inbox-card,
  .inbox-card-chevron {
    transition: none;
  }
}
</style>

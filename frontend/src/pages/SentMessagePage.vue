<script setup lang="ts">
/**
 * One sent message and its read receipts.
 *
 * The Sent list can only say "3 of 8". The question a sender actually has is
 * *which* five have not seen it, minutes before chasing them — so the unread
 * are listed first and by team name, which is who gets chased, rather than by
 * login.
 */
import { ArrowRightIcon, CheckIcon, RefreshCwIcon, UsersIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useActing } from '@/composables/useActing'
import { formatRelativeTime } from '@/lib/format'
import { useMessageRecipientsQuery, useMessagesQuery } from '@/queries/notifications'
import type { Recipient } from '@/types/api'

const route = useRoute()
const { isAnnouncer } = useActing()

const id = computed(() => Number(route.params.id))
const enabled = () => isAnnouncer.value && !!id.value

const receiptsQuery = useMessageRecipientsQuery(() => id.value, enabled)
// The message body itself comes from the Sent list, which the composer already
// caches; no second endpoint for something we have.
const sentQuery = useMessagesQuery('sent', enabled)

const message = computed(() => sentQuery.data.value?.find((row) => row.id === id.value) ?? null)
const receipts = computed(() => receiptsQuery.data.value ?? null)

const onlyUnread = ref(true)

const shown = computed<Recipient[]>(() => {
  const rows = receipts.value?.recipients ?? []
  return onlyUnread.value ? rows.filter((row) => !row.is_read) : rows
})

const progress = computed(() => {
  const data = receipts.value
  if (!data || data.delivered === 0) return 0
  return Math.round((data.read / data.delivered) * 100)
})
</script>

<template>
  <article class="sent-page" dir="rtl">
    <header class="sent-page-head">
      <Button as-child variant="ghost" size="sm">
        <RouterLink to="/messages">
          <ArrowRightIcon class="size-4" />
          بازگشت به پیام‌ها
        </RouterLink>
      </Button>
      <Button
        variant="ghost"
        size="sm"
        class="ms-auto"
        :disabled="receiptsQuery.isFetching.value"
        @click="receiptsQuery.refetch()"
      >
        <RefreshCwIcon class="size-3.5" :class="{ 'animate-spin': receiptsQuery.isFetching.value }" />
        به‌روزرسانی
      </Button>
    </header>

    <div class="sent-page-body">
      <section v-if="message" class="sent-page-message">
        <h1 class="sent-page-title">{{ message.title }}</h1>
        <p class="sent-page-meta">
          {{ message.audience_label }} · {{ formatRelativeTime(message.sent_at) }}
        </p>
        <div class="sent-page-text">{{ message.body || '—' }}</div>
      </section>
      <Skeleton v-else class="h-24 w-full" />

      <section class="sent-page-receipts" aria-label="وضعیت خواندن">
        <header class="receipts-head">
          <h2 class="receipts-title">
            <UsersIcon class="size-4" aria-hidden="true" />
            وضعیت خواندن
          </h2>
          <span v-if="receipts" class="receipts-count">
            {{ receipts.read }} از {{ receipts.delivered }} خوانده‌اند
          </span>
        </header>

        <div v-if="receipts" class="receipts-bar" role="presentation">
          <span class="receipts-bar-fill" :style="{ inlineSize: `${progress}%` }" />
        </div>

        <div class="receipts-filter">
          <Button
            size="sm"
            :variant="onlyUnread ? 'default' : 'outline'"
            @click="onlyUnread = true"
          >
            نخوانده‌ها
            <Badge v-if="receipts" variant="secondary" class="ms-1 font-normal">
              {{ receipts.unread }}
            </Badge>
          </Button>
          <Button
            size="sm"
            :variant="onlyUnread ? 'outline' : 'default'"
            @click="onlyUnread = false"
          >
            همه
            <Badge v-if="receipts" variant="secondary" class="ms-1 font-normal">
              {{ receipts.delivered }}
            </Badge>
          </Button>
        </div>

        <template v-if="receiptsQuery.isPending.value">
          <Skeleton v-for="n in 4" :key="n" class="h-9 w-full rounded-md" />
        </template>

        <p v-else-if="shown.length === 0" class="receipts-empty">
          {{ onlyUnread ? 'همه این پیام را خوانده‌اند.' : 'گیرنده‌ای ثبت نشده است.' }}
        </p>

        <ul v-else class="receipts-list">
          <li v-for="row in shown" :key="row.id" class="receipt" :class="{ 'is-read': row.is_read }">
            <span class="receipt-dot" aria-hidden="true">
              <CheckIcon v-if="row.is_read" class="size-3" />
            </span>
            <span class="receipt-name">{{ row.label }}</span>
            <span v-if="row.team_code" class="receipt-hint">{{ row.team_code }}</span>
            <span class="receipt-state">
              <template v-if="row.is_read">{{ formatRelativeTime(row.read_at) }}</template>
              <template v-else>خوانده‌نشده</template>
            </span>
          </li>
        </ul>
      </section>
    </div>
  </article>
</template>

<style scoped>
.sent-page {
  display: flex;
  block-size: 100%;
  min-block-size: 0;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem;
  overflow: hidden;
}

.sent-page-head {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.sent-page-body {
  display: flex;
  min-block-size: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 1rem;
  overflow-y: auto;
  max-inline-size: 48rem;
}

.sent-page-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 800;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.sent-page-meta {
  margin: 0.2rem 0 0.6rem;
  color: var(--muted-foreground);
  font-size: 0.72rem;
}
.sent-page-text {
  padding: 0.7rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  background: var(--card);
  font-size: 0.85rem;
  line-height: 1.95;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* ---- receipts ---- */
.sent-page-receipts {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.receipts-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.receipts-title {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin: 0;
  font-size: 0.9rem;
  font-weight: 700;
}
.receipts-count {
  margin-inline-start: auto;
  color: var(--muted-foreground);
  font-size: 0.75rem;
}

.receipts-bar {
  block-size: 0.4rem;
  border-radius: 9999px;
  background: var(--muted);
  overflow: hidden;
}
.receipts-bar-fill {
  display: block;
  block-size: 100%;
  border-radius: 9999px;
  background: #10b981;
  transition: inline-size 0.3s ease;
}

.receipts-filter {
  display: flex;
  gap: 0.35rem;
}

.receipts-empty {
  margin: 1.5rem 0;
  color: var(--muted-foreground);
  font-size: 0.8rem;
  text-align: center;
}

.receipts-list {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.receipt {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.45rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  background: var(--card);
  font-size: 0.8rem;
}
.receipt.is-read {
  background: transparent;
  opacity: 0.7;
}

.receipt-dot {
  display: grid;
  place-items: center;
  inline-size: 1.1rem;
  block-size: 1.1rem;
  flex-shrink: 0;
  border-radius: 9999px;
  background: var(--destructive);
  color: #fff;
}
.receipt.is-read .receipt-dot {
  background: #10b981;
}

.receipt-name {
  min-inline-size: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}
.receipt-hint {
  color: var(--muted-foreground);
  font-size: 0.68rem;
}
.receipt-state {
  margin-inline-start: auto;
  flex-shrink: 0;
  color: var(--muted-foreground);
  font-size: 0.7rem;
}

@media (prefers-reduced-motion: reduce) {
  .receipts-bar-fill {
    transition: none;
  }
}
</style>

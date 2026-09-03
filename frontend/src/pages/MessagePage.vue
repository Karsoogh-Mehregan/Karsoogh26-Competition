<script setup lang="ts">
/**
 * One received message, on its own page.
 *
 * The inbox used to expand a card in place, which fell apart on anything
 * longer than a couple of lines — and an unbroken string with no spaces blew
 * straight out of the card. A message of any length gets a page with room for
 * it, and reading is what marks it read.
 */
import { ArrowRightIcon, InboxIcon, MegaphoneIcon } from '@lucide/vue'
import { computed, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useMeQuery } from '@/queries/auth'
import { useMarkReadMutation, useNotificationQuery } from '@/queries/notifications'

const route = useRoute()
const { data: me } = useMeQuery()

const id = computed(() => Number(route.params.id))
const query = useNotificationQuery(() => id.value, () => me.value != null && !!id.value)
const { mutate: markRead } = useMarkReadMutation()

const item = computed(() => query.data.value ?? null)

// Opening it is what reads it. Kept out of the GET on purpose — a request that
// reports state should not change it — so the page asks once it has the item.
watch(
  item,
  (current) => {
    if (current && !current.is_read) markRead([current.id])
  },
  { immediate: true },
)

const sentAt = computed(() => {
  const when = item.value?.sent_at ?? item.value?.created_at
  if (!when) return ''
  return new Date(when).toLocaleString('fa-IR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
})
</script>

<template>
  <article class="message-page" dir="rtl">
    <header class="message-page-head">
      <Button as-child variant="ghost" size="sm">
        <RouterLink to="/inbox">
          <ArrowRightIcon class="size-4" />
          همهٔ پیام‌ها
        </RouterLink>
      </Button>
    </header>

    <div v-if="query.isPending.value && !item" class="message-page-body">
      <Skeleton class="h-7 w-2/3" />
      <Skeleton class="h-4 w-1/3" />
      <Skeleton class="h-40 w-full" />
    </div>

    <p v-else-if="!item" class="message-page-missing">این پیام پیدا نشد.</p>

    <div v-else class="message-page-body">
      <div class="message-page-meta">
        <span class="message-page-icon" aria-hidden="true">
          <component :is="item.kind === 'announcement' ? MegaphoneIcon : InboxIcon" class="size-4" />
        </span>
        <span class="message-page-sender">{{ item.sender }}</span>
        <Badge variant="outline" class="font-normal">
          {{ item.kind === 'announcement' ? 'پیام مدیر' : 'اعلان خودکار' }}
        </Badge>
        <time class="message-page-time">{{ sentAt }}</time>
      </div>

      <h1 class="message-page-title">{{ item.title }}</h1>

      <div class="message-page-text">{{ item.body || '—' }}</div>
    </div>
  </article>
</template>

<style scoped>
.message-page {
  display: flex;
  block-size: 100%;
  min-block-size: 0;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem;
  overflow: hidden;
}

.message-page-head {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.message-page-body {
  display: flex;
  min-block-size: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 0.6rem;
  overflow-y: auto;
  max-inline-size: 46rem;
}

.message-page-missing {
  margin: 3rem 0;
  color: var(--muted-foreground);
  text-align: center;
}

.message-page-meta {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-wrap: wrap;
  color: var(--muted-foreground);
  font-size: 0.75rem;
}
.message-page-icon {
  display: grid;
  place-items: center;
  inline-size: 1.75rem;
  block-size: 1.75rem;
  border-radius: 9999px;
  background: color-mix(in oklab, var(--primary) 16%, transparent);
  color: var(--primary);
}
.message-page-sender {
  color: var(--foreground);
  font-weight: 700;
}
.message-page-time {
  margin-inline-start: auto;
}

.message-page-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 800;
  line-height: 1.6;
  /* A pasted id or URL with no spaces must break rather than push the page
     sideways. `anywhere` also lets it shrink the container, which `break-word`
     does not. */
  overflow-wrap: anywhere;
}

.message-page-text {
  color: var(--foreground);
  font-size: 0.9rem;
  line-height: 2;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>

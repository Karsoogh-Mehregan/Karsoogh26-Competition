<script setup lang="ts">
/**
 * The inbox cards themselves, shared by the bell drawer and the full page.
 *
 * One copy on purpose: "read is grey, unread has a dot and an accent bar" is a
 * rule that has to hold in both places, and two copies of it drift. The only
 * difference between the two callers is how much room they have, which is a
 * `dense` prop and nothing more.
 */
import { ChevronDownIcon, InboxIcon, MegaphoneIcon } from '@lucide/vue'
import { onBeforeUnmount, ref } from 'vue'

import { Skeleton } from '@/components/ui/skeleton'
import { useNotifications } from '@/composables/useNotifications'
import { formatRelativeTime } from '@/lib/format'
import type { InboxItem } from '@/types/api'

const props = withDefaults(
  defineProps<{ items: InboxItem[]; loading?: boolean; dense?: boolean }>(),
  { loading: false, dense: false },
)

const { read } = useNotifications()

const expanded = ref<number | null>(null)

// A relative timestamp that never updates is a lie within the minute.
const now = ref(Date.now())
const ticker = setInterval(() => (now.value = Date.now()), 30_000)
onBeforeUnmount(() => clearInterval(ticker))

function toggle(item: InboxItem) {
  expanded.value = expanded.value === item.id ? null : item.id
  read(item)
}

function iconFor(item: InboxItem) {
  return item.kind === 'announcement' ? MegaphoneIcon : InboxIcon
}
</script>

<template>
  <div class="inbox-list" :class="{ 'is-dense': props.dense }">
    <template v-if="props.loading">
      <Skeleton v-for="n in 4" :key="n" class="h-20 w-full rounded-lg" />
    </template>

    <p v-else-if="props.items.length === 0" class="inbox-empty">
      <InboxIcon class="size-8 opacity-40" aria-hidden="true" />
      هنوز پیامی ندارید.
    </p>

    <article
      v-for="item in props.items"
      v-else
      :key="item.id"
      class="inbox-card"
      :class="{ 'is-read': item.is_read, 'is-open': expanded === item.id }"
    >
      <button
        type="button"
        class="inbox-card-head"
        :aria-expanded="expanded === item.id"
        @click="toggle(item)"
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
          <!-- Greyness alone is not a symbol, and colour alone is not
               accessible; unread gets both, plus the title attribute. -->
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
</template>

<style scoped>
.inbox-list {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  min-block-size: 0;
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 0.6rem;
}
.inbox-list.is-dense {
  padding: 0;
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

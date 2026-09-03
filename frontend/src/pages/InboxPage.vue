<script setup lang="ts">
/**
 * Every message this account has received, on a page of its own.
 *
 * The bell drawer is the glance — what just arrived, without leaving the map.
 * This is the place you actually go to read: wider cards, a filter, and room
 * for the browser-permission control that has nowhere sensible to live in a
 * cramped drawer. Both render the same `NotificationList`, so a card looks the
 * same in either.
 */
import { BellIcon, BellOffIcon, CheckCheckIcon, Loader2Icon, SendIcon } from '@lucide/vue'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

import NotificationList from '@/components/NotificationList.vue'
import { Button } from '@/components/ui/button'
import { useActing } from '@/composables/useActing'
import { useDesktopPermission, useNotifications } from '@/composables/useNotifications'

const { items, unread, hasUnread, loading, readAll, markingAll } = useNotifications()
const permission = useDesktopPermission()
const { isAnnouncer } = useActing()

const onlyUnread = ref(false)

const shown = computed(() =>
  onlyUnread.value ? items.value.filter((item) => !item.is_read) : items.value,
)
</script>

<template>
  <div class="inbox-page" dir="rtl">
    <header class="inbox-page-head">
      <div class="min-w-0">
        <h1 class="inbox-page-title">
          پیام‌ها
          <span v-if="hasUnread" class="inbox-page-count">{{ unread }}</span>
        </h1>
        <p class="inbox-page-hint">اعلان‌های خودکار بازی و پیام‌های مدیران.</p>
      </div>

      <div class="inbox-page-actions">
        <Button
          size="sm"
          :variant="onlyUnread ? 'default' : 'outline'"
          @click="onlyUnread = !onlyUnread"
        >
          فقط خوانده‌نشده‌ها
        </Button>
        <Button variant="outline" size="sm" :disabled="!hasUnread || markingAll" @click="readAll">
          <Loader2Icon v-if="markingAll" class="size-3.5 animate-spin" />
          <CheckCheckIcon v-else class="size-3.5" />
          خواندن همه
        </Button>
        <Button v-if="isAnnouncer" as-child size="sm">
          <RouterLink to="/messages">
            <SendIcon class="size-3.5" />
            نوشتن پیام
          </RouterLink>
        </Button>
      </div>
    </header>

    <!-- Asked for behind a button, never on load: an unprompted permission
         prompt is the fastest route to a permanent block. -->
    <button
      v-if="permission.canAsk.value"
      type="button"
      class="inbox-page-permission"
      @click="permission.request()"
    >
      <BellIcon class="size-4 shrink-0" aria-hidden="true" />
      <span>برای دریافت اعلان روی مرورگر — حتی وقتی این صفحه باز نیست — اجازه دهید.</span>
    </button>
    <p v-else-if="permission.isDenied.value" class="inbox-page-permission is-denied">
      <BellOffIcon class="size-4 shrink-0" aria-hidden="true" />
      <span>اعلان مرورگر رد شده است؛ از تنظیمات سایت در مرورگر می‌توانید دوباره اجازه دهید.</span>
    </p>

    <NotificationList :items="shown" :loading="loading" dense class="inbox-page-list" />
  </div>
</template>

<style scoped>
.inbox-page {
  display: flex;
  block-size: 100%;
  min-block-size: 0;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  overflow: hidden;
}

.inbox-page-head {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  flex-shrink: 0;
  flex-wrap: wrap;
  padding-block-end: 0.6rem;
  border-block-end: 1px solid var(--border);
}

.inbox-page-title {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
}

.inbox-page-count {
  display: inline-grid;
  place-items: center;
  min-inline-size: 1.3rem;
  padding-inline: 0.35rem;
  border-radius: 9999px;
  background: var(--destructive);
  color: #fff;
  font-size: 0.7rem;
  font-weight: 700;
}

.inbox-page-hint {
  margin: 0.15rem 0 0;
  color: var(--muted-foreground);
  font-size: 0.75rem;
}

.inbox-page-actions {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-inline-start: auto;
  flex-wrap: wrap;
}

.inbox-page-permission {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
  padding: 0.55rem 0.7rem;
  border: 1px dashed var(--border);
  border-radius: 0.55rem;
  background: color-mix(in oklab, var(--muted) 45%, transparent);
  color: var(--muted-foreground);
  font-size: 0.76rem;
  text-align: start;
  max-inline-size: 46rem;
}
button.inbox-page-permission:hover {
  color: var(--foreground);
  border-color: var(--ring);
}
.inbox-page-permission.is-denied {
  margin: 0;
  border-style: solid;
}

.inbox-page-list {
  max-inline-size: 52rem;
}
</style>

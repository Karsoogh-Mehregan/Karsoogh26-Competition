<script setup lang="ts">
/**
 * The bell's drawer: a glance at what just arrived, without leaving the map.
 *
 * The reading surface is `/inbox`; this only has to answer "what happened just
 * now". Cards come from `NotificationList` so the two never drift apart.
 */
import { BellIcon, CheckCheckIcon, Loader2Icon, MailOpenIcon, SendIcon } from '@lucide/vue'
import { useRouter } from 'vue-router'

import NotificationList from '@/components/NotificationList.vue'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { useActing } from '@/composables/useActing'
import { useNotifications } from '@/composables/useNotifications'

const { items, unread, hasUnread, loading, panelOpen, close, readAll, markingAll } =
  useNotifications()
const { isAnnouncer } = useActing()
const router = useRouter()

function onOpenChange(open: boolean) {
  if (!open) close()
}

function goTo(name: string) {
  close()
  router.push({ name })
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
          <Button variant="ghost" size="sm" @click="goTo('inbox')">
            <MailOpenIcon class="size-3.5" />
            همهٔ پیام‌ها
          </Button>
          <Button variant="ghost" size="sm" :disabled="!hasUnread || markingAll" @click="readAll">
            <Loader2Icon v-if="markingAll" class="size-3.5 animate-spin" />
            <CheckCheckIcon v-else class="size-3.5" />
            خواندن همه
          </Button>
          <Button v-if="isAnnouncer" variant="ghost" size="sm" @click="goTo('messages')">
            <SendIcon class="size-3.5" />
            نوشتن پیام
          </Button>
        </div>
      </SheetHeader>

      <!-- A card navigates to the message page, so the drawer gets out of the way. -->
      <NotificationList :items="items" :loading="loading" @open="close" />
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
  gap: 0.2rem;
  flex-wrap: wrap;
  margin-block-start: 0.15rem;
}
</style>

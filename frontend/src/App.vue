<script setup>
import 'vue-sonner/style.css'
import EntrySheetDialog from './components/EntrySheetDialog.vue'
import { onUnmounted, watch } from 'vue'
import { MenuIcon } from '@lucide/vue'
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import InfoPanel from './components/InfoPanel.vue'
import NotificationPanel from './components/NotificationPanel.vue'
import TopBar from './components/TopBar.vue'
import { useBoardStream } from '@/composables/useBoardStream'
import { useNotificationAnnouncer } from '@/composables/useNotifications'
import { useMeQuery } from '@/queries/auth'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { Toaster } from '@/components/ui/sonner'

const { data: me } = useMeQuery()
const board = useBoardStream()

// Mounted here, not in the panel: the toast has to fire whether or not the
// drawer happens to be open, and App outlives every route.
useNotificationAnnouncer()

watch(
  me,
  (value) => (value ? board.start() : board.stop()),
  { immediate: true },
)
onUnmounted(board.stop)

const mobilePanelOpen = ref(false)
const route = useRoute()

watch(() => route.fullPath, () => {
  mobilePanelOpen.value = false
})
</script>

<template>
  <div class="flex h-full w-full flex-col overflow-hidden">
    <TopBar />
    <div class="flex min-h-0 w-full flex-1 overflow-hidden">
      <div class="hidden h-full w-80 shrink-0 md:block">
      <InfoPanel />
      </div>
    <div class="flex min-w-0 flex-1 flex-col">
      <header class="flex h-12 shrink-0 items-center justify-between border-b bg-card px-3 md:hidden">
        <strong class="text-sm">کارسوق مهرگان</strong>
        <Button
          variant="outline"
          size="sm"
          aria-label="باز کردن منوی تیم و صفحات"
          @click="mobilePanelOpen = true"
        >
          <MenuIcon class="size-4" />
          منو
        </Button>
      </header>
      <main class="min-h-0 min-w-0 flex-1">
        <RouterView />
      </main>
    </div>
  </div>

  <Sheet v-model:open="mobilePanelOpen">
    <SheetContent
      side="right"
      class="w-[min(22rem,92vw)] gap-0 p-0 [&>button]:right-auto [&>button]:left-4"
      dir="rtl"
    >
      <SheetTitle class="sr-only">منوی تیم و صفحات</SheetTitle>
      <InfoPanel />
    </SheetContent>
  </Sheet>
  <EntrySheetDialog />
  <NotificationPanel />
  <Toaster class="pointer-events-auto" close-button dir="rtl" position="top-center" rich-colors />
</template>

<script setup>
import 'vue-sonner/style.css'
import { MenuIcon } from '@lucide/vue'
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import InfoPanel from './components/InfoPanel.vue'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { Toaster } from '@/components/ui/sonner'

const mobilePanelOpen = ref(false)
const route = useRoute()

watch(() => route.fullPath, () => {
  mobilePanelOpen.value = false
})
</script>

<template>
  <div class="flex h-full w-full overflow-hidden">
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
  <Toaster class="pointer-events-auto" close-button dir="rtl" position="top-center" rich-colors />
</template>

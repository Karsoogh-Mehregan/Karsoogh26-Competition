<script setup>
import 'vue-sonner/style.css'
import { onUnmounted, watch } from 'vue'
import InfoPanel from './components/InfoPanel.vue'
import TopBar from './components/TopBar.vue'
import { useBoardStream } from '@/composables/useBoardStream'
import { useMeQuery } from '@/queries/auth'
import { Toaster } from '@/components/ui/sonner'

const { data: me } = useMeQuery()
const board = useBoardStream()

watch(
  me,
  (value) => (value ? board.start() : board.stop()),
  { immediate: true },
)
onUnmounted(board.stop)
</script>

<template>
  <div class="flex h-full w-full flex-col overflow-hidden">
    <TopBar />
    <div class="flex min-h-0 w-full flex-1 overflow-hidden">
      <InfoPanel />
      <main class="h-full min-w-0 flex-1">
        <RouterView />
      </main>
    </div>
  </div>
  <Toaster class="pointer-events-auto" close-button dir="rtl" position="top-center" rich-colors />
</template>

<script setup>
import 'vue-sonner/style.css'
import InfoPanel from './components/InfoPanel.vue'
import { Toaster } from '@/components/ui/sonner'
</script>

<template>
  <div class="flex h-full w-full overflow-hidden">
    <InfoPanel />
    <main class="h-full min-w-0 flex-1">
      <RouterView />
    </main>
  </div>
  <Toaster class="pointer-events-auto" close-button dir="rtl" position="top-center" rich-colors />
</template>

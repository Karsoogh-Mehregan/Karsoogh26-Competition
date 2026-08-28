<script setup>
import GraphView from './components/GraphView.vue'
import InfoPanel from './components/InfoPanel.vue'
import { Toaster } from '@/components/ui/sonner'
</script>

<template>
  <div class="flex h-full w-full overflow-hidden">
    <InfoPanel />
    <main class="h-full min-w-0 flex-1">
      <GraphView />
    </main>
    <Toaster dir="rtl" rich-colors position="top-center" />
  </div>
</template>

<script setup lang="ts">
import GraphView from '@/components/GraphView.vue'
import HousePanel from '@/components/HousePanel.vue'
</script>

<template>
  <div class="flex h-full min-w-0">
    <div class="min-w-0 flex-1">
      <GraphView />
    </div>
    <HousePanel />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import GraphView from './components/GraphView.vue'
import InfoPanel from './components/InfoPanel.vue'
import { useGraph } from './composables/useGraph.js'

const { nodes, edges, path, selectableIds } = useGraph()

const currentNeighborCount = computed(() => selectableIds.value.size)
</script>

<template>
  <div class="app-shell">
    <main class="graph-area">
      <GraphView />
    </main>
    <InfoPanel
      :path="path"
      :total-nodes="nodes.length"
      :total-edges="edges.length"
      :current-neighbor-count="currentNeighborCount"
    />
  </div>
</template>

<style>
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
  width: 100%;
}
* {
  box-sizing: border-box;
}
body {
  font-family: var(--font-primary);
}
</style>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}
.graph-area {
  flex: 1;
  min-width: 0;
  height: 100%;
}
</style>

<script setup lang="ts">
/**
 * The only component that imports three.js.
 *
 * `HousePanel` pulls it in through `defineAsyncComponent`, so Vite splits it —
 * and the renderer with it — into its own chunk. A mentor who never opens a
 * house, or a team still on the entry sheet, never downloads any of it.
 */
import { RotateCcwIcon } from '@lucide/vue'
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

import { Button } from '@/components/ui/button'
import { useHouseStage, type StageStats } from '@/lib/house/stage'
import type { HouseSpec } from '@/lib/house/spec'

const props = defineProps<{ spec: HouseSpec | null }>()

const host = ref<HTMLDivElement | null>(null)
const stage = useHouseStage()
const stats = shallowRef<StageStats | null>(null)
const showStats = import.meta.env.DEV

let observer: ResizeObserver | null = null

function readStats() {
  if (!showStats) return
  // One frame behind on purpose: renderer.info is filled in during the draw.
  requestAnimationFrame(() => {
    stats.value = stage.stats()
  })
}

onMounted(() => {
  const element = host.value
  if (!element) return
  stage.mount(element)
  observer = new ResizeObserver(([entry]) => {
    const box = entry.contentRect
    stage.resize(box.width, box.height)
  })
  observer.observe(element)
  const rect = element.getBoundingClientRect()
  stage.resize(rect.width, rect.height)
  stage.setSpec(props.spec)
  readStats()
})

watch(
  () => props.spec,
  (spec) => {
    stage.setSpec(spec)
    readStats()
  },
)

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  // Unmount, never dispose: the context and the geometry pool are reused the
  // next time a house is opened.
  stage.unmount()
})

function resetView() {
  stage.resetView()
}
</script>

<template>
  <div class="house-stage">
    <div ref="host" class="house-stage-canvas" />

    <Button
      variant="ghost"
      size="icon"
      class="house-stage-reset"
      aria-label="بازگرداندن زاویهٔ دید"
      title="بازگرداندن زاویهٔ دید"
      @click="resetView"
    >
      <RotateCcwIcon class="size-4" />
    </Button>

    <p class="house-stage-hint" aria-hidden="true">برای چرخاندن، بکشید</p>

    <p v-if="showStats && stats" class="house-stage-stats" dir="ltr">
      {{ stats.drawCalls }} draws · {{ stats.triangles }} tris · {{ stats.geometries }} geo ·
      {{ stats.programs }} prog
    </p>
  </div>
</template>

<style scoped>
.house-stage {
  position: relative;
  inline-size: 100%;
  block-size: 100%;
  min-block-size: 0;
  border-radius: 0.75rem;
  overflow: hidden;
  background:
    radial-gradient(120% 90% at 50% 8%, color-mix(in oklab, var(--card) 92%, #f6c98a) 0%, var(--card) 68%),
    var(--card);
}

.house-stage-canvas {
  inline-size: 100%;
  block-size: 100%;
  cursor: grab;
}
.house-stage-canvas:active {
  cursor: grabbing;
}

.house-stage-reset {
  position: absolute;
  inset-block-start: 0.4rem;
  inset-inline-end: 0.4rem;
  opacity: 0.55;
}
.house-stage-reset:hover {
  opacity: 1;
}

.house-stage-hint {
  position: absolute;
  inset-block-end: 0.4rem;
  inset-inline-start: 0;
  inset-inline-end: 0;
  text-align: center;
  font-size: 0.68rem;
  color: var(--muted-foreground);
  opacity: 0.65;
  pointer-events: none;
}

.house-stage-stats {
  position: absolute;
  inset-block-start: 0.45rem;
  inset-inline-start: 0.55rem;
  font-size: 0.62rem;
  font-variant-numeric: tabular-nums;
  color: var(--muted-foreground);
  opacity: 0.6;
  pointer-events: none;
}
</style>

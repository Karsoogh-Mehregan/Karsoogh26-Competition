<script setup lang="ts">
import {
  CrosshairIcon,
  MaximizeIcon,
  MinusIcon,
  PlusIcon,
  SearchIcon,
  XIcon,
} from '@lucide/vue'
import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useActing } from '@/composables/useActing'
import { useMapViewport } from '@/composables/useMapViewport'

interface MapNode {
  id: string
  type: string
  x: number
  y: number
}

const props = defineProps<{ nodes: MapNode[] }>()
const emit = defineEmits<{ (e: 'highlight', id: string | null): void }>()

const { zoomPercent, canZoomIn, canZoomOut, zoomIn, zoomOut, reset, fitTo, focus } =
  useMapViewport()
const { actingTeam } = useActing()

const MAX_RESULTS = 7

const query = ref('')
const open = ref(false)

function normalize(value: string): string {
  return value
    .trim()
    .toUpperCase()
    .replace(/[۰-۹]/g, (digit) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)))
}

const matches = computed<MapNode[]>(() => {
  const needle = normalize(query.value)
  if (!needle) return []
  const exact: MapNode[] = []
  const partial: MapNode[] = []
  for (const node of props.nodes) {
    const id = node.id.toUpperCase()
    if (id === needle) exact.push(node)
    else if (id.includes(needle)) partial.push(node)
    if (exact.length + partial.length > 80) break
  }
  return [...exact, ...partial].slice(0, MAX_RESULTS)
})

function goTo(node: MapNode) {
  focus({ x: node.x, y: node.y }, 5)
  emit('highlight', node.id)
  open.value = false
  query.value = node.id
}

function onSubmit() {
  const first = matches.value[0]
  if (first) {
    goTo(first)
    return
  }
  if (query.value.trim()) {
    toast.error('خانه‌ای با این شناسه پیدا نشد.')
  }
}

function clearSearch() {
  query.value = ''
  open.value = false
  emit('highlight', null)
}

const holdingIds = computed(() => new Set(actingTeam.value?.holdings.map((h) => h.node_code) ?? []))

const canFindMine = computed(() => holdingIds.value.size > 0)

function goToMine() {
  const points = props.nodes
    .filter((node) => holdingIds.value.has(node.id))
    .map((node) => ({ x: node.x, y: node.y }))
  if (points.length === 0) {
    toast.info('هنوز خانه‌ای ندارید.')
    return
  }
  fitTo(points, points.length === 1 ? 260 : 180)
}

function onReset() {
  clearSearch()
  reset()
}
</script>

<template>
  <div class="map-hud" dir="rtl">
    <div class="glass-panel map-search">
      <Label for="map-search-input" class="sr-only">جستجوی خانه روی نقشه</Label>
      <SearchIcon class="map-search-icon" aria-hidden="true" />
      <Input
        id="map-search-input"
        v-model="query"
        class="map-search-input"
        type="search"
        autocomplete="off"
        placeholder="جستجوی خانه — مثلاً L1_36"
        @focus="open = true"
        @input="open = true"
        @keydown.enter.prevent="onSubmit"
        @keydown.esc.prevent="clearSearch"
      />
      <button
        v-if="query"
        type="button"
        class="map-search-clear"
        aria-label="پاک کردن جستجو"
        @click="clearSearch"
      >
        <XIcon class="size-3.5" />
      </button>

      <ul v-if="open && matches.length" class="glass-panel map-results" role="listbox">
        <li v-for="node in matches" :key="node.id">
          <button type="button" class="map-result" @click="goTo(node)">
            <span class="map-result-id">{{ node.id }}</span>
            <span class="map-result-type">{{ node.type }}</span>
          </button>
        </li>
      </ul>
    </div>

    <div class="glass-panel map-controls">
      <Button
        variant="ghost"
        size="icon"
        class="map-btn"
        aria-label="بزرگ‌نمایی"
        :disabled="!canZoomIn"
        @click="zoomIn"
      >
        <PlusIcon class="size-4" />
      </Button>
      <span class="map-zoom tabular-nums" aria-live="off">{{ zoomPercent }}%</span>
      <Button
        variant="ghost"
        size="icon"
        class="map-btn"
        aria-label="کوچک‌نمایی"
        :disabled="!canZoomOut"
        @click="zoomOut"
      >
        <MinusIcon class="size-4" />
      </Button>
      <span class="map-divider" aria-hidden="true" />
      <Button
        v-if="canFindMine"
        variant="ghost"
        size="icon"
        class="map-btn"
        aria-label="رفتن به خانه‌های من"
        title="خانه‌های من"
        @click="goToMine"
      >
        <CrosshairIcon class="size-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        class="map-btn"
        aria-label="نمای کامل نقشه"
        title="نمای کامل"
        @click="onReset"
      >
        <MaximizeIcon class="size-4" />
      </Button>
    </div>
  </div>
</template>

<style scoped>
.map-hud {
  position: absolute;
  inset-block-start: 1rem;
  inset-inline-end: 1rem;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.6rem;
  width: min(19rem, calc(100% - 2rem));
  pointer-events: none;
}
.map-hud > * {
  pointer-events: auto;
}

.map-search {
  position: relative;
  /* Lifted so the results list drops over the zoom controls, not behind them. */
  z-index: 2;
  display: flex;
  align-items: center;
  padding: 0.25rem;
}
.map-search-icon {
  position: absolute;
  inset-inline-start: 0.75rem;
  width: 1rem;
  height: 1rem;
  color: var(--muted-foreground);
  pointer-events: none;
}
.map-search-input {
  border: 0;
  background: transparent;
  box-shadow: none;
  padding-inline-start: 2rem;
  padding-inline-end: 1.75rem;
}
.map-search-input:focus-visible {
  border: 0;
  box-shadow: none;
  outline: none;
}
.map-search-input::-webkit-search-cancel-button {
  display: none;
}
.map-search-clear {
  position: absolute;
  inset-inline-end: 0.6rem;
  display: grid;
  place-items: center;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 9999px;
  color: var(--muted-foreground);
  cursor: pointer;
}
.map-search-clear:hover {
  background: color-mix(in oklab, var(--foreground) 10%, transparent);
  color: var(--foreground);
}

.map-results {
  /* A dropdown has to be readable: tint it well past the panel default so the
     controls sitting underneath do not read through the frost. */
  --glass-tint: color-mix(in oklab, var(--card) 92%, transparent);
  position: absolute;
  inset-block-start: calc(100% + 0.4rem);
  inset-inline: 0;
  margin: 0;
  padding: 0.25rem;
  list-style: none;
  max-height: 15rem;
  overflow-y: auto;
}
.map-result {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  width: 100%;
  padding: 0.4rem 0.6rem;
  border-radius: var(--radius-sm);
  font-size: 0.8125rem;
  cursor: pointer;
  text-align: start;
}
.map-result:hover,
.map-result:focus-visible {
  background: color-mix(in oklab, var(--primary) 14%, transparent);
  outline: none;
}
.map-result-id {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.map-result-type {
  color: var(--muted-foreground);
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.map-controls {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 0.15rem;
  padding: 0.25rem;
  align-self: flex-start;
}
.map-btn {
  width: 2rem;
  height: 2rem;
}
.map-zoom {
  min-width: 3.25rem;
  text-align: center;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted-foreground);
}
.map-divider {
  width: 1px;
  height: 1.25rem;
  margin-inline: 0.2rem;
  background: color-mix(in oklab, var(--foreground) 15%, transparent);
}

@media (max-width: 640px) {
  .map-hud {
    inset-inline: 1rem;
    width: auto;
  }
}
</style>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import MapHud from './MapHud.vue'
import QuestionDialog from './QuestionDialog.vue'
import { useActing } from '../composables/useActing'
import { useGraph } from '../composables/useGraph.js'
import { useMapViewport } from '../composables/useMapViewport'

const HOUSE_FILL = '#E8D5B0'

const { me, teams, actingTeam, isPlayer, claimStart, assignQuestion } = useActing()
const { nodes, edges, nodeById, adjacency, startEligibleIds } = useGraph()

const loggedIn = computed(() => !!me.value)
const hasTeam = computed(() => !!actingTeam.value)
// A mentor can pick a team to view its state on the map, but only the team
// itself can move — mentors would otherwise see clickable nodes that 403.
const canAct = computed(() => loggedIn.value && hasTeam.value && isPlayer.value)
const pendingNode = ref(null)
const dialogOpen = computed({
  get: () => pendingNode.value !== null,
  set: (open) => {
    if (!open) pendingNode.value = null
  },
})
const pendingOccupancyId = ref(null)

function isStartNode(n) {
  return !!n && (n.type === 'start' || n.shape === 'diamond')
}

const paintedHoldings = computed(() => {
  if (actingTeam.value) {
    const color = actingTeam.value.color
    return actingTeam.value.holdings.map((holding) => ({ ...holding, color }))
  }
  return teams.value.flatMap((team) =>
    team.holdings.map((holding) => ({ ...holding, color: team.color })),
  )
})

const holdingsByNode = computed(() => {
  const map = new Map()
  for (const holding of paintedHoldings.value) {
    const list = map.get(holding.node_code) ?? []
    list.push(holding)
    map.set(holding.node_code, list)
  }
  return map
})

const claimedStartIds = computed(() => {
  const ids = new Set()
  for (const team of teams.value) {
    for (const holding of team.holdings) {
      const node = nodeById.get(holding.node_code)
      if (isStartNode(node)) {
        ids.add(holding.node_code)
      }
    }
    if (!team.color) continue
    for (const node of nodes) {
      if (isStartNode(node) && node.color === team.color) {
        ids.add(node.id)
      }
    }
  }
  return ids
})

const actingHeldIds = computed(() => {
  if (!actingTeam.value) return new Set()
  return new Set(actingTeam.value.holdings.map((holding) => holding.node_code))
})

function holdingUnlocksNeighbors(holding) {
  return holding.is_spawn === true || holding.grade != null
}

const expandableHeldIds = computed(() => {
  if (!actingTeam.value) return new Set()
  return new Set(
    actingTeam.value.holdings
      .filter(holdingUnlocksNeighbors)
      .map((holding) => holding.node_code),
  )
})

function isHeld(id) {
  return holdingsByNode.value.has(id)
}

function isNodeSelectable(id) {
  if (!canAct.value) return false
  const held = actingHeldIds.value
  if (held.size === 0) {
    return startEligibleIds.has(id) && !claimedStartIds.value.has(id)
  }
  if (held.has(id)) return false
  const expandable = expandableHeldIds.value
  if (expandable.size === 0) return false
  for (const heldId of expandable) {
    if (adjacency.get(heldId)?.has(id)) return true
  }
  return false
}

function isNodeSelected(id) {
  return isHeld(id)
}

function answerableHolding(id) {
  if (!canAct.value) return null
  return (
    actingTeam.value.holdings.find(
      (h) => h.node_code === id && !h.is_spawn && h.grade == null,
    ) ?? null
  )
}

function isNodeAnswerable(id) {
  return answerableHolding(id) !== null
}

const hoveredId = ref(null)

// ---- camera ----
// The viewBox is the camera; useMapViewport owns it. `bounds` is only the
// whole-map framing it starts from and returns to.
const PAD = 90
const bounds = computed(() => {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const n of nodes) {
    minX = Math.min(minX, n.x)
    maxX = Math.max(maxX, n.x)
    minY = Math.min(minY, n.y)
    maxY = Math.max(maxY, n.y)
  }
  return {
    minX: minX - PAD,
    minY: minY - PAD,
    width: maxX - minX + PAD * 2,
    height: maxY - minY + PAD * 2,
  }
})

const svgRef = ref(null)
const viewport = useMapViewport()
const { viewBox, box, labelsVisible, unitsPerPx, isPanning, consumedByDrag } = viewport
const searchHit = ref(null)

onMounted(() => {
  viewport.attach(svgRef.value)
  viewport.setHome({
    x: bounds.value.minX,
    y: bounds.value.minY,
    w: bounds.value.width,
    h: bounds.value.height,
  })
})

onBeforeUnmount(() => viewport.detach())

function onSearchHighlight(id) {
  searchHit.value = id
}

// Only label what is actually on screen: 473 <text> nodes would cost more than
// they are worth, and off-screen ones are unreadable anyway.
const labelledNodes = computed(() => {
  if (!labelsVisible.value) return []
  const { x, y, w, h } = box.value
  const margin = Math.max(w, h) * 0.08
  return nodes.filter(
    (n) =>
      n.x >= x - margin &&
      n.x <= x + w + margin &&
      n.y >= y - margin &&
      n.y <= y + h + margin,
  )
})

// Text has no `vector-effect`, so labels are sized in map units converted from
// the pixel size we actually want on screen.
function px(value) {
  return value * unitsPerPx.value
}

// ---- edge helpers ----
function edgePath(e) {
  const a = nodeById.get(e.source)
  const b = nodeById.get(e.target)
  return { x1: a.x, y1: a.y, x2: b.x, y2: b.y }
}

// shrink a directed edge's endpoint back so the arrowhead doesn't overlap the node circle
function shrunkTarget(e) {
  const a = nodeById.get(e.source)
  const b = nodeById.get(e.target)
  const dx = b.x - a.x
  const dy = b.y - a.y
  const len = Math.hypot(dx, dy) || 1
  const r = visualRadius(b) + 6
  return { x: b.x - (dx / len) * r, y: b.y - (dy / len) * r }
}

function isEdgeActive(e) {
  if (!hasTeam.value || expandableHeldIds.value.size === 0) return false
  const srcExpandable = expandableHeldIds.value.has(e.source)
  const tgtExpandable = expandableHeldIds.value.has(e.target)
  return (
    (srcExpandable && isNodeSelectable(e.target)) ||
    (tgtExpandable && isNodeSelectable(e.source))
  )
}

function isEdgeTraversed(e) {
  return isNodeSelected(e.source) && isNodeSelected(e.target)
}

// ---- node helpers ----
function nodeState(n) {
  if (isNodeAnswerable(n.id)) return 'answerable'
  if (isNodeSelected(n.id)) return 'visited'
  if (isNodeSelectable(n.id)) return 'selectable'
  if (isStartNode(n) && !claimedStartIds.value.has(n.id)) return 'idle'
  return 'disabled'
}

function isNodeInteractive(n) {
  return isNodeAnswerable(n.id) || isNodeSelectable(n.id)
}

function nodeLabel(n) {
  const state = nodeState(n)
  if (state === 'answerable') return `${n.id} — پاسخ به سؤال`
  if (state === 'selectable') return `${n.id} — قابل انتخاب`
  return n.id
}

function onNodeClick(n) {
  // A click that ended a pan is a camera move, not a move on the board.
  if (consumedByDrag()) return
  const holding = answerableHolding(n.id)
  if (holding) {
    pendingOccupancyId.value = holding.id
    return
  }
  if (!isNodeSelectable(n.id)) return
  pendingNode.value = n
}

const pendingIsStart = computed(
  () => isStartNode(pendingNode.value) && actingHeldIds.value.size === 0,
)

async function confirmNodeAction() {
  const node = pendingNode.value
  const claimStartNode = pendingIsStart.value
  pendingNode.value = null
  if (!node || !hasTeam.value) return
  try {
    if (claimStartNode) {
      await claimStart(node.id)
      toast.success('خانهٔ شروع ثبت شد')
      return
    }
    const result = await assignQuestion(node.id)
    toast.success(`سؤال ${result.question_id ?? ''} رزرو شد`)
  } catch (err) {
    toast.error(err.message || 'عملیات ناموفق بود.')
  }
}

function ringFill(n, ringIndexFromOutside) {
  const holdings = holdingsByNode.value.get(n.id) ?? []
  const floor = ringIndexFromOutside + 1
  const onFloor = holdings.find((holding) => holding.floor === floor)
  if (onFloor?.color) return onFloor.color
  if (ringIndexFromOutside === 0) {
    const pending = holdings.find((holding) => holding.floor == null)
    if (pending?.color) return pending.color
  }
  return HOUSE_FILL
}

function nodeFill(n) {
  const holdings = holdingsByNode.value.get(n.id) ?? []
  const colored = holdings.find((holding) => holding.color)
  if (colored?.color && (slotCount(n) === 1 || isStartNode(n))) {
    return colored.color
  }
  if (isStartNode(n)) return n.color
  return HOUSE_FILL
}

function startDuel() {
  pendingNode.value = null
  toast.info('دوئل هنوز فعال نشده است.')
}

function slotCount(n) {
  if (n.type === 'l3' || n.type === 'l4') return 2
  if (n.type === 'l5' || n.type === 'l6' || n.type === 'center') return 3
  return 1
}

function visualRadius(n) {
  if (!n) return 6
  if (slotCount(n) > 1) return n.size * 3
  if (n.type === 'l1' || n.type === 'l2') return n.size * 1.5
  return n.size
}

function slotRadii(n) {
  const outer = visualRadius(n)
  const slots = slotCount(n)
  return Array.from({ length: slots }, (_, i) => outer * ((slots - i) / slots))
}

function shapePath(n) {
  const s = n.size
  if (n.shape === 'diamond') {
    return `M 0 ${-s} L ${s} 0 L 0 ${s} L ${-s} 0 Z`
  }
  if (n.shape === 'square') {
    const h = s * 0.82
    return `M ${-h} ${-h} L ${h} ${-h} L ${h} ${h} L ${-h} ${h} Z`
  }
  return null // circle handled separately
}
</script>

<template>
  <div class="graph-wrap">
    <!-- Something for the glass panels to blur. Purely decorative. -->
    <div class="map-aurora" aria-hidden="true">
      <span class="aurora-blob blob-a" />
      <span class="aurora-blob blob-b" />
      <span class="aurora-blob blob-c" />
    </div>

    <svg
      ref="svgRef"
      class="graph-svg"
      :class="{ panning: isPanning }"
      :viewBox="viewBox"
      preserveAspectRatio="xMidYMid meet"
      tabindex="0"
      role="application"
      aria-label="نقشهٔ بازی — با کشیدن جابه‌جا و با چرخ ماوس بزرگ‌نمایی کنید"
    >
    <defs>
      <!-- Fake glass: a lit top edge fading to nothing, laid over the node fill. -->
      <linearGradient id="glass-sheen" x1="0" y1="0" x2="0.35" y2="1">
        <stop offset="0%" stop-color="#ffffff" stop-opacity="0.6" />
        <stop offset="42%" stop-color="#ffffff" stop-opacity="0.06" />
        <stop offset="100%" stop-color="#3d6c93" stop-opacity="0.14" />
      </linearGradient>
      <marker
        id="arrow"
        viewBox="0 0 10 10"
        refX="9"
        refY="5"
        markerUnits="userSpaceOnUse"
        markerWidth="12"
        markerHeight="12"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#6fa8d0" />
      </marker>
      <marker
        id="arrow-active"
        viewBox="0 0 10 10"
        refX="9"
        refY="5"
        markerUnits="userSpaceOnUse"
        markerWidth="13"
        markerHeight="13"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#2b6ca8" />
      </marker>
      <marker
        id="arrow-out"
        viewBox="0 0 10 10"
        refX="9"
        refY="5"
        markerUnits="userSpaceOnUse"
        markerWidth="12"
        markerHeight="12"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#222" />
      </marker>
    </defs>

    <!-- outward direction markers: yellow diamond start nodes only -->
    <g class="out-arrows">
      <line
        v-for="n in nodes.filter((n) => n.shape === 'diamond')"
        :key="'out-' + n.id"
        :x1="n.x + n.outArrowDx * (n.size + 6)"
        :y1="n.y + n.outArrowDy * (n.size + 6)"
        :x2="n.x + n.outArrowDx * (n.size + 34)"
        :y2="n.y + n.outArrowDy * (n.size + 34)"
        stroke="#222"
        stroke-width="1.6"
        marker-end="url(#arrow-out)"
      />
    </g>

    <!-- edges -->
    <g class="edges">
      <line
        v-for="(e, i) in edges"
        :key="'e-' + i"
        :x1="edgePath(e).x1"
        :y1="edgePath(e).y1"
        :x2="e.directed ? shrunkTarget(e).x : edgePath(e).x2"
        :y2="e.directed ? shrunkTarget(e).y : edgePath(e).y2"
        :class="[
          'edge',
          { active: isEdgeActive(e), traversed: isEdgeTraversed(e) },
        ]"
        :marker-end="e.directed ? (isEdgeActive(e) || isEdgeTraversed(e) ? 'url(#arrow-active)' : 'url(#arrow)') : null"
      />
    </g>

    <!-- nodes -->
    <g class="nodes">
      <g
        v-for="n in nodes"
        :key="n.id"
        :transform="`translate(${n.x}, ${n.y})`"
        :class="[
          'node',
          'state-' + nodeState(n),
          'shape-' + n.shape,
          { 'search-hit': searchHit === n.id },
        ]"
        :role="isNodeInteractive(n) ? 'button' : undefined"
        :tabindex="isNodeInteractive(n) ? 0 : undefined"
        :aria-label="isNodeInteractive(n) ? nodeLabel(n) : undefined"
        @click="onNodeClick(n)"
        @keydown.enter.prevent="onNodeClick(n)"
        @keydown.space.prevent="onNodeClick(n)"
        @mouseenter="hoveredId = n.id"
        @mouseleave="hoveredId = null"
        @focus="hoveredId = n.id"
        @blur="hoveredId = null"
      >
        <template v-if="slotCount(n) > 1">
          <circle
            v-for="(r, i) in slotRadii(n)"
            :key="i"
            :r="r"
            :fill="ringFill(n, i)"
            class="node-shape"
          />
        </template>
        <circle
          v-else-if="n.shape === 'circle'"
          :r="visualRadius(n)"
          :fill="nodeFill(n)"
          class="node-shape"
        />
        <path v-else :d="shapePath(n)" :fill="nodeFill(n)" class="node-shape" />

        <!-- Only on nodes big enough to show it; 473 sheens would be noise. -->
        <circle
          v-if="slotCount(n) > 1"
          :r="visualRadius(n)"
          class="node-sheen"
          fill="url(#glass-sheen)"
        />
        <path
          v-else-if="n.shape !== 'circle'"
          :d="shapePath(n)"
          class="node-sheen"
          fill="url(#glass-sheen)"
        />

        <circle
          v-if="searchHit === n.id"
          :r="visualRadius(n) + 14"
          class="ring-search"
        />
        <circle
          v-if="isNodeSelected(n.id)"
          :r="visualRadius(n) + 5"
          class="ring-selected"
        />
        <circle
          v-else-if="isNodeSelectable(n.id)"
          :r="visualRadius(n) + 5"
          class="ring-selectable"
        />

        <text
          v-if="hoveredId === n.id && !labelsVisible"
          :y="-(visualRadius(n) + px(10))"
          :style="{ fontSize: `${px(14)}px`, strokeWidth: `${px(4)}px` }"
          class="node-label"
          text-anchor="middle"
        >
          {{ n.id }}
        </text>
      </g>

      <!-- Zoomed-in labels, drawn once over the nodes so they never sit under one. -->
      <text
        v-for="n in labelledNodes"
        :key="'label-' + n.id"
        :x="n.x"
        :y="n.y + visualRadius(n) + px(13)"
        :style="{ fontSize: `${px(11)}px`, strokeWidth: `${px(3)}px` }"
        class="node-label zoom-label"
        text-anchor="middle"
      >
        {{ n.id }}
      </text>
    </g>

    <!-- center label -->
    <text
      v-if="nodeById.get('CENTER') && !labelsVisible"
      :x="nodeById.get('CENTER').x"
      :y="nodeById.get('CENTER').y + visualRadius(nodeById.get('CENTER')) + px(18)"
      :style="{ fontSize: `${px(14)}px` }"
      text-anchor="middle"
      class="center-label"
    >
      CENTER
    </text>
  </svg>

    <Dialog v-model:open="dialogOpen">
      <DialogContent class="sm:max-w-xs" dir="rtl" :show-close-button="false">
        <DialogHeader class="text-center sm:text-center">
          <DialogTitle>این خانه</DialogTitle>
          <DialogDescription>
            {{ pendingNode ? pendingNode.id : '' }}
          </DialogDescription>
        </DialogHeader>
        <div class="flex flex-col gap-2">
          <Button class="w-full" @click="confirmNodeAction">
            {{ pendingIsStart ? 'ورود به این خانه' : 'رزرو این خانه' }}
          </Button>
          <Button class="w-full" variant="outline" @click="startDuel">دویل</Button>
        </div>
      </DialogContent>
    </Dialog>

    <QuestionDialog
      :occupancy-id="pendingOccupancyId"
      @close="pendingOccupancyId = null"
    />

    <MapHud :nodes="nodes" @highlight="onSearchHighlight" />

    <ul v-if="canAct" class="legend glass-panel" aria-label="راهنمای رنگ خانه‌ها">
      <li><span class="legend-dot legend-answerable" />پاسخ به سؤال</li>
      <li><span class="legend-dot legend-selectable" />قابل رزرو</li>
      <li><span class="legend-dot legend-visited" />در اختیار شما</li>
    </ul>
  </div>
</template>

<style scoped>
.graph-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  isolation: isolate;
  background: var(--background);
}

/* ---- aurora backdrop ----
   Slow-drifting colour behind the map. Its only job is to give the glass
   panels — and the translucent node fills — something to refract. */
.map-aurora {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
  background: radial-gradient(circle at 50% 40%, #ffffff 0%, #eef4fa 52%, #dde7f2 100%);
}
.aurora-blob {
  position: absolute;
  display: block;
  border-radius: 9999px;
  filter: blur(70px);
  opacity: 0.62;
  will-change: transform;
}
.blob-a {
  inset-block-start: -12%;
  inset-inline-start: 8%;
  width: 46%;
  aspect-ratio: 1;
  background: #7fb2d9;
  animation: drift-a 34s ease-in-out infinite alternate;
}
.blob-b {
  inset-block-end: -18%;
  inset-inline-end: 2%;
  width: 52%;
  aspect-ratio: 1;
  background: #e0b775;
  opacity: 0.5;
  animation: drift-b 42s ease-in-out infinite alternate;
}
.blob-c {
  inset-block-start: 32%;
  inset-inline-end: 34%;
  width: 34%;
  aspect-ratio: 1;
  background: #a99ad9;
  opacity: 0.42;
  animation: drift-c 50s ease-in-out infinite alternate;
}

@keyframes drift-a {
  to { transform: translate3d(14%, 18%, 0) scale(1.18); }
}
@keyframes drift-b {
  to { transform: translate3d(-16%, -12%, 0) scale(1.12); }
}
@keyframes drift-c {
  to { transform: translate3d(10%, -20%, 0) scale(0.88); }
}

.legend {
  position: absolute;
  z-index: 2;
  inset-block-end: 1rem;
  inset-inline-start: 1rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
  margin: 0;
  padding: 0.5rem 0.75rem;
  list-style: none;
  font-size: 0.75rem;
  color: var(--muted-foreground);
}
.legend li {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}
.legend-dot {
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 9999px;
  border: 1px solid #1a1a1a;
}
.legend-answerable {
  background: #e67e22;
}
.legend-selectable {
  background: #2b6ca8;
}
.legend-visited {
  background: v-bind('actingTeam?.color || HOUSE_FILL');
}

.graph-svg {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  display: block;
  background: transparent;
  cursor: grab;
  touch-action: none;
  outline: none;
}
.graph-svg.panning {
  cursor: grabbing;
}
.graph-svg.panning .node {
  cursor: grabbing;
}
.graph-svg:focus-visible {
  box-shadow: inset 0 0 0 2px var(--ring);
}

.edge {
  stroke: #9dc8e4;
  stroke-width: 0.7px;
  vector-effect: non-scaling-stroke;
  transition: stroke 0.2s ease, stroke-width 0.2s ease, opacity 0.2s ease;
}
.edge.traversed {
  stroke: #4a90c4;
  stroke-width: 2.2px;
}
.edge.active {
  stroke: #2b6ca8;
  stroke-width: 2.2px;
}

.node {
  cursor: default;
  transition: opacity 0.25s ease;
}
.node-shape {
  stroke: color-mix(in oklab, #10243a 55%, transparent);
  stroke-width: 0.9px;
  fill-opacity: 0.92;
  vector-effect: non-scaling-stroke;
  transition: filter 0.2s ease, stroke-width 0.15s ease, fill-opacity 0.2s ease;
}
.node:hover .node-shape {
  fill-opacity: 1;
}

/* The lit edge that reads as glass. Never a hit target. */
.node-sheen {
  pointer-events: none;
}

.zoom-label {
  pointer-events: none;
  fill: #10243a;
  opacity: 0.72;
}

.ring-search {
  fill: none;
  stroke: #e0761f;
  stroke-width: 3;
  vector-effect: non-scaling-stroke;
  animation: search-ping 1.4s ease-out infinite;
}

@keyframes search-ping {
  0% { opacity: 0.95; transform: scale(0.82); }
  70% { opacity: 0; transform: scale(1.35); }
  100% { opacity: 0; transform: scale(1.35); }
}

.node-label {
  font-size: 15px;
  font-weight: 600;
  fill: #1a1a1a;
  paint-order: stroke;
  stroke: #ffffff;
  stroke-width: 4px;
  pointer-events: none;
}

.center-label {
  font-size: 15px;
  fill: #333;
  font-weight: 600;
}

/* --- state styling --- */
.state-disabled {
  opacity: 0.32;
  cursor: not-allowed;
}

.state-idle {
  opacity: 1;
  cursor: default;
}

.state-selectable {
  cursor: pointer;
}
.state-selectable .node-shape {
  filter: drop-shadow(0 0 6px rgba(43, 108, 168, 0.65));
}
.state-selectable:hover .node-shape {
  stroke-width: 2.2;
  filter: drop-shadow(0 0 8px rgba(43, 108, 168, 0.85));
}

.state-visited {
  opacity: 1;
  cursor: default;
}
.state-visited .node-shape {
  filter: drop-shadow(0 0 6px rgba(43, 108, 168, 0.55));
}

.state-answerable {
  opacity: 1;
  cursor: pointer;
}
.state-answerable .node-shape {
  filter: drop-shadow(0 0 6px rgba(230, 126, 34, 0.75));
  animation: answerable-pulse 1.8s ease-in-out infinite;
}
.state-answerable:hover .node-shape,
.state-answerable:focus-visible .node-shape {
  stroke-width: 2.2;
  animation: none;
  filter: drop-shadow(0 0 8px rgba(230, 126, 34, 0.95));
}

@keyframes answerable-pulse {
  0%,
  100% {
    filter: drop-shadow(0 0 4px rgba(230, 126, 34, 0.55));
  }
  50% {
    filter: drop-shadow(0 0 10px rgba(230, 126, 34, 1));
  }
}

.node:focus {
  outline: none;
}
.node:focus-visible .node-shape {
  stroke: #1d4ed8;
  stroke-width: 3;
}

.state-current {
  cursor: default;
}
.state-current .node-shape {
  filter: drop-shadow(0 0 10px rgba(214, 39, 40, 0.85));
}

.ring-selected {
  fill: none;
  stroke: #2b6ca8;
  stroke-width: 2.2;
}

.ring-current {
  fill: none;
  stroke: #d62728;
  stroke-width: 2.6;
  stroke-dasharray: 4 3;
  transform-box: fill-box;
  transform-origin: center;
  animation: spin 6s linear infinite;
}

.ring-selectable {
  fill: none;
  stroke: #2b6ca8;
  stroke-width: 2;
  opacity: 0.85;
  animation: pulse 1.6s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.35; r: v-bind('"var(--r)"'); }
  50% { opacity: 0.9; }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .ring-current,
  .ring-selectable,
  .ring-search,
  .aurora-blob,
  .state-answerable .node-shape {
    animation: none;
  }
}
</style>

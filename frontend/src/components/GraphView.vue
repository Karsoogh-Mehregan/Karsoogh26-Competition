<script setup>
import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useActing } from '../composables/useActing'
import { useGraph } from '../composables/useGraph.js'

const HOUSE_FILL = '#E8D5B0'

const { me, teams, actingTeam, claimStart, assignQuestion } = useActing()
const { nodes, edges, nodeById, adjacency, startEligibleIds } = useGraph()

const loggedIn = computed(() => !!me.value)
const hasTeam = computed(() => !!actingTeam.value)
const pendingNode = ref(null)
const dialogOpen = computed({
  get: () => pendingNode.value !== null,
  set: (open) => {
    if (!open) pendingNode.value = null
  },
})

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
  if (!loggedIn.value || !hasTeam.value) return false
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

const hoveredId = ref(null)

// ---- viewBox / bounds ----
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
const viewBox = computed(
  () => `${bounds.value.minX} ${bounds.value.minY} ${bounds.value.width} ${bounds.value.height}`
)

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
  if (isNodeSelected(n.id)) return 'visited'
  if (isNodeSelectable(n.id)) return 'selectable'
  if (isStartNode(n) && !claimedStartIds.value.has(n.id)) return 'idle'
  return 'disabled'
}

function onNodeClick(n) {
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
    <svg class="graph-svg" :viewBox="viewBox" preserveAspectRatio="xMidYMid meet">
    <defs>
      <marker
        id="arrow"
        viewBox="0 0 10 10"
        refX="8"
        refY="5"
        markerWidth="6"
        markerHeight="6"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#6fa8d0" />
      </marker>
      <marker
        id="arrow-active"
        viewBox="0 0 10 10"
        refX="8"
        refY="5"
        markerWidth="7"
        markerHeight="7"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#2b6ca8" />
      </marker>
      <marker
        id="arrow-out"
        viewBox="0 0 10 10"
        refX="8"
        refY="5"
        markerWidth="6"
        markerHeight="6"
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
        :class="['node', 'state-' + nodeState(n), 'shape-' + n.shape]"
        @click="onNodeClick(n)"
        @mouseenter="hoveredId = n.id"
        @mouseleave="hoveredId = null"
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
          v-if="hoveredId === n.id"
          :y="-(visualRadius(n) + 12)"
          class="node-label"
          text-anchor="middle"
        >
          {{ n.id }}
        </text>
      </g>
    </g>

    <!-- center label -->
    <text
      v-if="nodeById.get('CENTER')"
      :x="nodeById.get('CENTER').x"
      :y="nodeById.get('CENTER').y + visualRadius(nodeById.get('CENTER')) + 22"
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
  </div>
</template>

<style scoped>
.graph-wrap {
  width: 100%;
  height: 100%;
}

.graph-svg {
  width: 100%;
  height: 100%;
  display: block;
  background: radial-gradient(circle at center, #ffffff 0%, #fafbfd 60%, #f4f6f9 100%);
}

.edge {
  stroke: #bcdcf0;
  stroke-width: 1.35;
  transition: stroke 0.2s ease, stroke-width 0.2s ease, opacity 0.2s ease;
}
.edge.traversed {
  stroke: #4a90c4;
  stroke-width: 3.2;
}
.edge.active {
  stroke: #2b6ca8;
  stroke-width: 3.2;
}

.node {
  cursor: default;
  transition: opacity 0.25s ease;
}
.node-shape {
  stroke: #1a1a1a;
  stroke-width: 1.4;
  transition: filter 0.2s ease, stroke-width 0.15s ease;
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
</style>

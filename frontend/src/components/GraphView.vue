<script setup>
import { computed, ref } from 'vue'
import { useGraph } from '../composables/useGraph.js'

const {
  nodes,
  edges,
  nodeById,
  path,
  currentNodeId,
  hasStarted,
  isSelectable,
  isSelected,
  isCurrent,
  selectNode,
} = useGraph()

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
  const r = (b.size ?? 6) + 6
  return { x: b.x - (dx / len) * r, y: b.y - (dy / len) * r }
}

function isEdgeActive(e) {
  // highlight edges that connect to the current node, once traversal started
  if (!hasStarted.value) return false
  return e.source === currentNodeId.value || e.target === currentNodeId.value
}

function isEdgeTraversed(e) {
  // edge is part of the path already walked
  const p = path.value
  for (let i = 0; i < p.length - 1; i++) {
    const a = p[i], b = p[i + 1]
    if ((e.source === a && e.target === b) || (e.source === b && e.target === a)) return true
  }
  return false
}

// ---- node helpers ----
function nodeState(n) {
  if (isCurrent(n.id)) return 'current'
  if (isSelected(n.id)) return 'visited'
  if (isSelectable(n.id)) return 'selectable'
  return 'disabled'
}

function onNodeClick(n) {
  selectNode(n.id)
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

    <!-- outward direction markers for pink/gray nodes -->
    <g class="out-arrows">
      <line
        v-for="n in nodes.filter((n) => n.hasOutArrow)"
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
        <circle
          v-if="n.shape === 'circle'"
          :r="n.size"
          :fill="n.color"
          class="node-shape"
        />
        <path v-else :d="shapePath(n)" :fill="n.color" class="node-shape" />

        <circle
          v-if="isCurrent(n.id)"
          :r="n.size + 7"
          class="ring-current"
        />
        <circle
          v-else-if="isSelectable(n.id)"
          :r="n.size + 5"
          class="ring-selectable"
        />

        <text
          v-if="hoveredId === n.id"
          :y="-(n.size + 12)"
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
      :y="nodeById.get('CENTER').y + nodeById.get('CENTER').size + 22"
      text-anchor="middle"
      class="center-label"
    >
      CENTER
    </text>
  </svg>
</template>

<style scoped>
.graph-svg {
  width: 100%;
  height: 100%;
  display: block;
  background: radial-gradient(circle at center, #ffffff 0%, #fafbfd 60%, #f4f6f9 100%);
}

.edge {
  stroke: #bcdcf0;
  stroke-width: 2;
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
  transition: opacity 0.25s ease, transform 0.15s ease;
}
.node-shape {
  stroke: #1a1a1a;
  stroke-width: 1.4;
  transition: filter 0.2s ease;
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

.state-selectable {
  cursor: pointer;
}
.state-selectable .node-shape {
  filter: drop-shadow(0 0 6px rgba(43, 108, 168, 0.65));
}
.state-selectable:hover {
  transform: scale(1.18);
}

.state-visited {
  opacity: 0.9;
  cursor: not-allowed;
}

.state-current {
  cursor: not-allowed;
}
.state-current .node-shape {
  filter: drop-shadow(0 0 10px rgba(214, 39, 40, 0.85));
}

.ring-current {
  fill: none;
  stroke: #d62728;
  stroke-width: 2.6;
  stroke-dasharray: 4 3;
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

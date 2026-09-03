<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import MapHud from './MapHud.vue'
import { useActing } from '../composables/useActing'
import { useEntry } from '../composables/useEntry'
import { useMapDesign } from '../composables/useMapDesign'
import { sectorGeometries } from '../lib/mapNeighborhoods'
import { useInspectorStore } from '../stores/inspector'
import { useGraph } from '../composables/useGraph.js'
import { useMapViewport } from '../composables/useMapViewport'

const HOUSE_FILL = '#E2CFA6'

const { me, teams, actingTeam, isPlayer } = useActing()
const { canClaimStart } = useEntry()
const inspector = useInspectorStore()
const { nodes, edges, nodeById, adjacency, startEligibleIds } = useGraph()
const design = useMapDesign()
const { neighborhoods, roadStyle, tintStrength, haloStrength } = design

// ---- neighbourhoods ----
// Eight wedges painted behind everything, and one ring per node in its sector's
// colour. Both are static geometry: nothing here re-renders on a board event.
const SECTOR_OUTER = 1075
const SECTOR_INNER = 120
// The borders follow the real gaps between groups on every ring, so they
// wander a little instead of cutting straight. Geometry only; computed once.
const sectorShapes = sectorGeometries(nodes, SECTOR_OUTER, SECTOR_INNER)
const sectors = computed(() =>
  sectorShapes.map((shape) => ({
    ...shape,
    color: neighborhoods.value[shape.index]?.color ?? '#999999',
    name: neighborhoods.value[shape.index]?.name ?? '',
  })),
)

function haloColor(n) {
  return design.neighborhoodOf(n).color
}

const loggedIn = computed(() => !!me.value)
const hasTeam = computed(() => !!actingTeam.value)
// A mentor can pick a team to view its state on the map, but only the team
// itself can move — mentors would otherwise see clickable nodes that 403.
const canAct = computed(() => loggedIn.value && hasTeam.value && isPlayer.value)
function isStartNode(n) {
  return !!n && (n.type === 'start' || n.shape === 'diamond')
}

const paintedHoldings = computed(() =>
  teams.value.flatMap((team) =>
    team.holdings.map((holding) => ({
      ...holding,
      color: team.color,
      team_code: team.code,
    })),
  ),
)

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

function isHeldByAnyone(id) {
  return holdingsByNode.value.has(id)
}

// A team that has not cleared the entry sheet cannot take a spawn yet, so the
// start nodes stay unselectable and route the click to the sheet instead.
function isFreeStart(id) {
  return startEligibleIds.has(id) && !claimedStartIds.value.has(id)
}

function isEntryGate(n) {
  return canAct.value && !canClaimStart.value && actingHeldIds.value.size === 0 && isFreeStart(n.id)
}

function isNodeSelectable(id) {
  if (!canAct.value) return false
  const held = actingHeldIds.value
  if (held.size === 0) {
    return canClaimStart.value && isFreeStart(id)
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
  return actingHeldIds.value.has(id)
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

// One dot every GRID_UNITS map units. Translating the pattern by the camera
// origin pins the dots to the map, so they slide under your finger as you pan
// and spread apart as you zoom in.
const GRID_UNITS = 120
const gridStyle = computed(() => {
  const perPx = unitsPerPx.value || 1
  const cell = GRID_UNITS / perPx
  return {
    backgroundSize: `${cell}px ${cell}px`,
    backgroundPosition: `${-box.value.x / perPx}px ${-box.value.y / perPx}px`,
  }
})

// ---- edge helpers ----
function edgePath(e) {
  const a = nodeById.get(e.source)
  const b = nodeById.get(e.target)
  return { x1: a.x, y1: a.y, x2: b.x, y2: b.y }
}

// One <path> per road, so the Designer's road style is a `d` string and a
// class rather than a different element. Curved roads bow away from the map's
// centre, which reads as streets wrapping around the rings.
function edgeD(e) {
  const { x1, y1 } = edgePath(e)
  const end = e.directed ? shrunkTarget(e) : { x: edgePath(e).x2, y: edgePath(e).y2 }
  if (roadStyle.value !== 'curved') {
    return `M ${x1} ${y1} L ${end.x} ${end.y}`
  }
  const mx = (x1 + end.x) / 2
  const my = (y1 + end.y) / 2
  const len = Math.hypot(end.x - x1, end.y - y1) || 1
  // Perpendicular, pointing away from the origin.
  let nx = -(end.y - y1) / len
  let ny = (end.x - x1) / len
  if (nx * mx + ny * my < 0) {
    nx = -nx
    ny = -ny
  }
  const bulge = Math.min(22, len * 0.16)
  return `M ${x1} ${y1} Q ${mx + nx * bulge} ${my + ny * bulge} ${end.x} ${end.y}`
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
  if (isEntryGate(n)) return 'gated'
  if (isStartNode(n) && !claimedStartIds.value.has(n.id)) return 'idle'
  if (isHeldByAnyone(n.id)) return 'occupied'
  return 'disabled'
}

function isNodeInteractive() {
  return loggedIn.value
}

function isNodeInspected(n) {
  return inspector.inspection?.nodeCode === n.id
}

function nodeLabel(n) {
  const state = nodeState(n)
  if (state === 'answerable') return `${n.id} — پاسخ به سؤال`
  if (state === 'selectable') return `${n.id} — قابل انتخاب`
  if (state === 'gated') return `${n.id} — ابتدا سؤال‌های ورودی را پاسخ دهید`
  return n.id
}

function isGatewayNode(n) {
  return design.levelOf(n.id, n.type) === 'toll'
}

function inspectIntent(n) {
  const holding = answerableHolding(n.id)
  if (holding) return { intent: 'solve', occupancyId: holding.id }
  if (isEntryGate(n)) return { intent: 'entry_gate', occupancyId: null }
  // A gateway is played, not answered: it never offers a question, and only
  // offers a board where the server actually has one configured.
  if (isGatewayNode(n)) {
    const playable = canAct.value && design.hasMinesweeper(n.id)
    return { intent: playable ? 'minesweeper' : 'view', occupancyId: null }
  }
  if (isNodeSelectable(n.id)) {
    const claimingStart = isStartNode(n) && actingHeldIds.value.size === 0
    return { intent: claimingStart ? 'claim_start' : 'reserve', occupancyId: null }
  }
  return { intent: 'view', occupancyId: null }
}

/**
 * Every node opens the detail panel, even one this team can do nothing with —
 * seeing who holds a building and how full it is is worth a click on its own.
 * What the panel *offers* is the intent, decided here where the adjacency and
 * entry-sheet rules already live.
 */
function onNodeClick(n) {
  // A click that ended a pan is a camera move, not a move on the board.
  if (consumedByDrag()) return
  const { intent, occupancyId } = inspectIntent(n)
  inspector.inspect(n.id, intent, occupancyId)
}

function reservedHoldingsOn(n) {
  return (holdingsByNode.value.get(n.id) ?? []).filter(
    (holding) => !holding.is_spawn && holding.grade == null,
  )
}

// Team colour is the node's message; only dim it when there is a team to
// contrast against, and never so far that the colour stops reading.
function holdingOpacity(holding) {
  if (!holding) return 1
  if (!actingTeam.value) return 1
  return holding.team_code === actingTeam.value.code ? 1 : 0.55
}

function ringFill(n, ringIndexFromOutside) {
  const holdings = holdingsByNode.value.get(n.id) ?? []
  const floor = ringIndexFromOutside + 1
  const onFloor = holdings.find((holding) => holding.floor === floor)
  if (onFloor?.color) return onFloor.color
  const reserved = reservedHoldingsOn(n)[ringIndexFromOutside]
  if (reserved?.color) return reserved.color
  return HOUSE_FILL
}

function ringOpacity(n, ringIndexFromOutside) {
  const holdings = holdingsByNode.value.get(n.id) ?? []
  const floor = ringIndexFromOutside + 1
  const onFloor = holdings.find((holding) => holding.floor === floor)
  const reserved = reservedHoldingsOn(n)[ringIndexFromOutside]
  return holdingOpacity(onFloor ?? reserved)
}

function ringIsHatched(n, ringIndexFromOutside) {
  return ringIndexFromOutside < reservedHoldingsOn(n).length
}

function isShapeHatched(n) {
  return slotCount(n) === 1 && reservedHoldingsOn(n).length > 0
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

function shapeOpacity(n) {
  const holdings = holdingsByNode.value.get(n.id) ?? []
  const colored = holdings.find((holding) => holding.color)
  return holdingOpacity(colored)
}

function slotCount(n) {
  return design.capacityOf(n.id, n.type)
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
    <!-- A near-neutral ground with a faint dot grid pinned to map coordinates:
         it gives the glass something to refract and makes panning read as
         motion, without colouring over the nodes. -->
    <div class="map-ground" aria-hidden="true" />
    <div class="map-grid" aria-hidden="true" :style="gridStyle" />

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
        <stop offset="0%" stop-color="#ffffff" stop-opacity="0.34" />
        <stop offset="38%" stop-color="#ffffff" stop-opacity="0.03" />
        <stop offset="100%" stop-color="#2c4661" stop-opacity="0.1" />
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
      <!-- عوارضی: a gantry with a barrier arm, instead of an anonymous dot. -->
      <symbol id="toll-gate" viewBox="-10 -10 20 20">
        <rect x="-8.5" y="-1" width="3" height="9.5" rx="0.6" />
        <rect x="5.5" y="-1" width="3" height="9.5" rx="0.6" />
        <rect x="-8.5" y="-5.5" width="17" height="3.2" rx="0.8" />
        <rect x="-6" y="2.2" width="12" height="2" rx="0.6" />
      </symbol>
      <pattern
        id="reserve-hatch"
        patternUnits="userSpaceOnUse"
        width="6"
        height="6"
        patternTransform="rotate(45)"
      >
        <line x1="0" y1="0" x2="0" y2="6" stroke="#1a1a1a" stroke-width="2.2" />
      </pattern>
    </defs>

    <!-- neighbourhood wedges: a wash of colour per sector, never a hit target -->
    <g v-if="tintStrength > 0" class="sectors" aria-hidden="true">
      <path
        v-for="sector in sectors"
        :key="'sector-' + sector.index"
        :d="sector.d"
        :fill="sector.color"
        :fill-opacity="tintStrength"
        :stroke="sector.color"
        :stroke-opacity="Math.min(1, tintStrength * 2.2)"
        class="sector"
      />
    </g>
    <g v-if="tintStrength > 0 && labelsVisible" class="sector-labels" aria-hidden="true">
      <text
        v-for="sector in sectors"
        :key="'sector-label-' + sector.index"
        :x="sector.label.x"
        :y="sector.label.y"
        :font-size="px(11)"
        :fill="sector.color"
        class="sector-label"
        text-anchor="middle"
        dominant-baseline="middle"
      >
        {{ sector.name }}
      </text>
    </g>

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
    <g class="edges" :class="'road-' + roadStyle">
      <path
        v-for="(e, i) in edges"
        :key="'e-' + i"
        :d="edgeD(e)"
        fill="none"
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
          { 'search-hit': searchHit === n.id, 'is-inspected': isNodeInspected(n) },
        ]"
        :role="isNodeInteractive() ? 'button' : undefined"
        :tabindex="isNodeInteractive() ? 0 : undefined"
        :aria-label="isNodeInteractive() ? nodeLabel(n) : undefined"
        @click="onNodeClick(n)"
        @keydown.enter.prevent="onNodeClick(n)"
        @keydown.space.prevent="onNodeClick(n)"
        @mouseenter="hoveredId = n.id"
        @mouseleave="hoveredId = null"
        @focus="hoveredId = n.id"
        @blur="hoveredId = null"
      >
        <!-- An opaque plate under the node: the team colour must read against
             neutral ground, not through the neighbourhood wash. -->
        <circle class="node-plate" :r="visualRadius(n) + 1.5" />
        <circle
          v-if="haloStrength > 0"
          class="node-halo"
          :r="visualRadius(n) + 6"
          :stroke="haloColor(n)"
          :stroke-opacity="haloStrength"
          fill="none"
        />
        <template v-if="slotCount(n) > 1">
          <template v-for="(r, i) in slotRadii(n)" :key="n.id + '-ring-' + i">
            <circle
              :r="r"
              :fill="ringFill(n, i)"
              :opacity="ringOpacity(n, i)"
              class="node-shape"
            />
            <circle
              v-if="ringIsHatched(n, i)"
              :r="r"
              fill="url(#reserve-hatch)"
              :opacity="ringOpacity(n, i)"
              class="node-hatch"
            />
          </template>
        </template>
        <template v-else-if="n.type === 'c34' || n.type === 'c45'">
          <!-- The gantry glyph has gaps; this disc is what actually takes the click. -->
          <circle :r="n.size * 1.4" fill="transparent" stroke="none" class="node-hit" />
          <use
            href="#toll-gate"
            :x="-n.size * 1.4"
            :y="-n.size * 1.4"
            :width="n.size * 2.8"
            :height="n.size * 2.8"
            :fill="nodeFill(n)"
            :opacity="shapeOpacity(n)"
            class="node-shape node-toll"
          />
        </template>
        <template v-else-if="n.shape === 'circle'">
          <circle
            :r="visualRadius(n)"
            :fill="nodeFill(n)"
            :opacity="shapeOpacity(n)"
            class="node-shape"
          />
          <circle
            v-if="isShapeHatched(n)"
            :r="visualRadius(n)"
            fill="url(#reserve-hatch)"
            :opacity="shapeOpacity(n)"
            class="node-hatch"
          />
        </template>
        <template v-else>
          <path
            :d="shapePath(n)"
            :fill="nodeFill(n)"
            :opacity="shapeOpacity(n)"
            class="node-shape"
          />
          <path
            v-if="isShapeHatched(n)"
            :d="shapePath(n)"
            fill="url(#reserve-hatch)"
            :opacity="shapeOpacity(n)"
            class="node-hatch"
          />
        </template>

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

    <MapHud :nodes="nodes" @highlight="onSearchHighlight" />

    <ul v-if="canAct" class="legend glass-panel" aria-label="راهنمای رنگ خانه‌ها">
      <li><span class="legend-dot legend-answerable" />پاسخ به سؤال</li>
      <li><span class="legend-dot legend-selectable" />قابل رزرو</li>
      <li v-if="!canClaimStart"><span class="legend-dot legend-gated" />نیازمند سؤال ورودی</li>
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

/* ---- backdrop ----
   Deliberately almost colourless. The map has 473 nodes to read; anything
   saturated back here competes with them and tires the eye at high zoom. */
.map-ground {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background:
    radial-gradient(120% 90% at 50% 0%, #ffffff 0%, #f7f9fc 55%, #eff3f8 100%);
}
.map-grid {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image: radial-gradient(
    circle,
    color-mix(in oklab, #2c4661 22%, transparent) 1px,
    transparent 1px
  );
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
.legend-gated {
  background: #b8860b;
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

.sector,
.sector-label {
  pointer-events: none;
}
.sector {
  stroke-width: 1.6px;
  vector-effect: non-scaling-stroke;
  stroke-linejoin: round;
}
.node-toll {
  stroke-width: 0.9px;
  pointer-events: none;
}
.node-hit {
  pointer-events: all;
}
.sector-label {
  font-weight: 700;
  letter-spacing: 0.02em;
  opacity: 0.55;
}

/* The neighbourhood's "hollow presence" around every house. */
.node-plate {
  fill: #f8f7f3;
  stroke: none;
  pointer-events: none;
}
.node-halo {
  stroke-width: 1.6px;
  vector-effect: non-scaling-stroke;
  pointer-events: none;
}

.road-dashed .edge {
  stroke-dasharray: 6 5;
}

.edge {
  stroke: #8fb9d6;
  stroke-width: 0.8px;
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
/* Which node the house panel is showing. Deliberately louder than hover: the
   detail beside the map is useless if you lose track of what it belongs to. */
.is-inspected .node-shape {
  stroke: #1d4ed8;
  stroke-width: 3px;
}
.is-inspected {
  filter: drop-shadow(0 0 9px rgba(29, 78, 216, 0.55));
}
.search-hit .node-shape {
  stroke: #b45309;
  stroke-width: 2.6px;
}
.node-shape {
  stroke: #33506b;
  stroke-width: 1.1px;
  vector-effect: non-scaling-stroke;
  transition: filter 0.2s ease, stroke-width 0.15s ease;
}
.node-hatch {
  stroke: none;
  pointer-events: none;
}

.state-occupied {
  opacity: 1;
  cursor: default;
}

.node:hover .node-shape {
  stroke: #10243a;
  stroke-width: 1.8px;
}

/* The lit edge that reads as glass. Never a hit target. */
.node-sheen {
  pointer-events: none;
}

.zoom-label {
  pointer-events: none;
  fill: #1d3145;
  opacity: 0.85;
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

.state-gated {
  cursor: pointer;
}
.state-gated .node-shape {
  filter: drop-shadow(0 0 6px rgba(184, 134, 11, 0.7));
}
.state-gated:hover .node-shape,
.state-gated:focus-visible .node-shape {
  stroke-width: 2.2;
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
  .state-answerable .node-shape {
    animation: none;
  }
}
</style>

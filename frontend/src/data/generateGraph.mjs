/**
 * Builds the 48-team contest map JSON from the same geometry as
 * contest_map_48_teams.py (LAYER_SIZES scaled from the 36-team pattern).
 *
 * Run: node src/data/generateGraph.mjs
 */
import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const TEAM_COUNT = 48
const LAYER_SIZES = [192, 144, 48, 32, 24, 8]
const RADII = [6.0, 5.0, 4.0, 3.0, 2.0, 1.15]
const OFFSETS_DEG = [0.0, 1.875, 5.625, 9.375, 13.125, 28.125]

// Match the previous SVG scale (~outer radius 1000).
const SCALE = 1000 / 6
// SVG y grows downward; flip so the map matches the Python/matplotlib image.
const FLIP_Y = -1

const COLORS = {
  start: '#f2c200',
  gateway: '#17becf',
  l1: '#1f77b4',
  l2: '#ff7f0e',
  l3: '#2ca02c',
  c34: '#e377c2',
  l4: '#d62728',
  c45: '#7f7f7f',
  l5: '#9467bd',
  l6: '#8c564b',
  center: '#1f4e79',
}

const SIZES = {
  start: 10,
  gateway: 8,
  l1: 5,
  l2: 6,
  l3: 7,
  c34: 8,
  l4: 8,
  c45: 10,
  l5: 9,
  l6: 12,
  center: 18,
}

function round(n, p = 2) {
  const m = 10 ** p
  return Math.round(n * m) / m
}

function polarPositions(n, radius, offsetDeg = 0) {
  const pts = []
  for (let i = 0; i < n; i++) {
    const deg = offsetDeg + i * (360 / n)
    const rad = (deg * Math.PI) / 180
    pts.push({
      x: radius * Math.cos(rad),
      y: radius * Math.sin(rad),
      theta: deg,
    })
  }
  return pts
}

function nodeId(layer, index) {
  if (layer === 'C') return 'CENTER'
  if (layer === 'C34') return `C34_${index}`
  if (layer === 'C45') return `C45_${index}`
  return `L${layer}_${index}`
}

function toSvg(pt, radius) {
  const ux = pt.x / radius
  const uy = pt.y / radius
  return {
    x: round(SCALE * pt.x),
    y: round(SCALE * FLIP_Y * pt.y),
    theta: round(pt.theta, 3),
    r: round(SCALE * radius),
    outArrowDx: round(ux, 4),
    outArrowDy: round(FLIP_Y * uy, 4),
  }
}

function makeNode(id, spec, pt, radius) {
  const pos = toSvg(pt, radius)
  const node = {
    id,
    type: spec.type,
    shape: spec.shape,
    color: spec.color,
    layer: spec.layer,
    size: spec.size,
    hasOutArrow: Boolean(spec.hasOutArrow),
    x: pos.x,
    y: pos.y,
    theta: pos.theta,
    r: pos.r,
  }
  if (spec.hasOutArrow) {
    node.outArrowDx = pos.outArrowDx
    node.outArrowDy = pos.outArrowDy
  }
  return node
}

function buildNodes() {
  const nodes = []
  const layers = {}

  for (let i = 0; i < LAYER_SIZES.length; i++) {
    const layerIdx = i + 1
    layers[layerIdx] = polarPositions(LAYER_SIZES[i], RADII[i], OFFSETS_DEG[i])
  }

  layers.C34 = polarPositions(16, 3.5, 14.0625)
  layers.C45 = polarPositions(8, 2.5, 27.1875)

  // L1: every 4th node is a start diamond; the next one is the inward gateway.
  for (let i = 0; i < LAYER_SIZES[0]; i++) {
    const role = i % 4
    let spec
    if (role === 0) {
      spec = {
        type: 'start',
        shape: 'diamond',
        color: COLORS.start,
        layer: 1,
        size: SIZES.start,
        hasOutArrow: true,
      }
    } else if (role === 1) {
      spec = {
        type: 'gateway',
        shape: 'square',
        color: COLORS.gateway,
        layer: 1,
        size: SIZES.gateway,
        hasOutArrow: false,
      }
    } else {
      spec = {
        type: 'l1',
        shape: 'circle',
        color: COLORS.l1,
        layer: 1,
        size: SIZES.l1,
        hasOutArrow: false,
      }
    }
    nodes.push(makeNode(nodeId(1, i), spec, layers[1][i], RADII[0]))
  }

  const regularLayers = [
    { idx: 2, type: 'l2', color: COLORS.l2, size: SIZES.l2, radius: RADII[1] },
    { idx: 3, type: 'l3', color: COLORS.l3, size: SIZES.l3, radius: RADII[2] },
    { idx: 4, type: 'l4', color: COLORS.l4, size: SIZES.l4, radius: RADII[3] },
    { idx: 5, type: 'l5', color: COLORS.l5, size: SIZES.l5, radius: RADII[4] },
    { idx: 6, type: 'l6', color: COLORS.l6, size: SIZES.l6, radius: RADII[5] },
  ]

  for (const layer of regularLayers) {
    for (let i = 0; i < layers[layer.idx].length; i++) {
      nodes.push(
        makeNode(
          nodeId(layer.idx, i),
          {
            type: layer.type,
            shape: 'circle',
            color: layer.color,
            layer: layer.idx,
            size: layer.size,
            hasOutArrow: false,
          },
          layers[layer.idx][i],
          layer.radius,
        ),
      )
    }
  }

  for (let i = 0; i < layers.C34.length; i++) {
    nodes.push(
      makeNode(
        nodeId('C34', i),
        {
          type: 'c34',
          shape: 'circle',
          color: COLORS.c34,
          layer: 'C34',
          size: SIZES.c34,
          hasOutArrow: false,
        },
        layers.C34[i],
        3.5,
      ),
    )
  }

  for (let i = 0; i < layers.C45.length; i++) {
    nodes.push(
      makeNode(
        nodeId('C45', i),
        {
          type: 'c45',
          shape: 'square',
          color: COLORS.c45,
          layer: 'C45',
          size: SIZES.c45,
          hasOutArrow: false,
        },
        layers.C45[i],
        2.5,
      ),
    )
  }

  nodes.push({
    id: 'CENTER',
    type: 'center',
    shape: 'circle',
    color: COLORS.center,
    layer: 0,
    size: SIZES.center,
    hasOutArrow: false,
    x: 0,
    y: 0,
    theta: 0,
    r: 0,
  })

  return nodes
}

function edge(source, target, directed = false) {
  return { source, target, directed }
}

function buildEdges() {
  const edges = []

  // Ring edges on L1–L5
  for (let layer = 1; layer <= 5; layer++) {
    const n = LAYER_SIZES[layer - 1]
    for (let i = 0; i < n; i++) {
      edges.push(edge(nodeId(layer, i), nodeId(layer, (i + 1) % n)))
    }
  }

  // L1 gateway -> L2 (one per team)
  for (let i = 0; i < TEAM_COUNT; i++) {
    edges.push(edge(nodeId(1, 4 * i + 1), nodeId(2, 3 * i)))
  }

  // L2 -> L3 (two inner L2 nodes of each team)
  for (let i = 0; i < TEAM_COUNT; i++) {
    edges.push(edge(nodeId(2, 3 * i + 1), nodeId(3, i)))
    edges.push(edge(nodeId(2, 3 * i + 2), nodeId(3, i)))
  }

  // L3 -> C34 -> L4 (16 planar groups, directed inward)
  for (let g = 0; g < 16; g++) {
    const c34 = nodeId('C34', g)
    for (let i = 0; i < 3; i++) {
      edges.push(edge(nodeId(3, 3 * g + i), c34, true))
    }
    for (let j = 0; j < 2; j++) {
      edges.push(edge(c34, nodeId(4, 2 * g + j), true))
    }
  }

  // L4 -> C45 -> L5 (8 planar groups, directed inward)
  for (let g = 0; g < 8; g++) {
    const c45 = nodeId('C45', g)
    for (let i = 0; i < 4; i++) {
      edges.push(edge(nodeId(4, 4 * g + i), c45, true))
    }
    for (let j = 0; j < 3; j++) {
      edges.push(edge(c45, nodeId(5, 3 * g + j), true))
    }
  }

  // L5 -> L6 (groups of 3)
  for (let k = 0; k < 8; k++) {
    for (let t = 0; t < 3; t++) {
      edges.push(edge(nodeId(5, 3 * k + t), nodeId(6, k)))
    }
  }

  // L6 complete graph K8, including opposite pairs:
  // L6_0–L6_4, L6_1–L6_5, L6_2–L6_6, L6_3–L6_7.
  for (let i = 0; i < 8; i++) {
    for (let j = i + 1; j < 8; j++) {
      edges.push(edge(nodeId(6, i), nodeId(6, j)))
    }
  }

  // L6 -> center
  for (let i = 0; i < 8; i++) {
    edges.push(edge(nodeId(6, i), 'CENTER'))
  }

  return edges
}

const nodes = buildNodes()
const edges = buildEdges()
const startCount = nodes.filter((n) => n.shape === 'diamond').length

const data = {
  nodes,
  edges,
  meta: {
    teamCount: TEAM_COUNT,
    totalNodes: nodes.length,
    totalEdges: edges.length,
    startNodeCount: startCount,
    centerNodeId: 'CENTER',
  },
}

if (nodes.length !== 473) {
  throw new Error(`Expected 473 nodes, got ${nodes.length}`)
}
if (startCount !== 48) {
  throw new Error(`Expected 48 start diamonds, got ${startCount}`)
}
if (edges.length !== 780) {
  throw new Error(`Expected 780 edges, got ${edges.length}`)
}

const outPath = join(dirname(fileURLToPath(import.meta.url)), 'graph_data.json')
writeFileSync(outPath, `${JSON.stringify(data, null, 1)}\n`)

console.log(
  `Wrote ${outPath}\n${nodes.length} nodes, ${edges.length} edges, ${startCount} start diamonds`,
)

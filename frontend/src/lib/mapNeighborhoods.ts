/**
 * Which pizza slice a node is in, and the SVG wedge that paints it.
 *
 * Membership is exact: `floor(theta / 45)`. Every connectivity group in
 * `generateGraph.mjs` (L3 → C34 → L4 → C45 → L5 → L6) lands inside one sector,
 * and no node sits on a boundary, so the sector is geometry the client
 * computes, not data the server stores.
 *
 * The *painted* border is not the straight 45° cut, though. On each ring the
 * last node of one sector and the first of the next sit at different angles —
 * a 1.9° gap on L1, 45° on L6 — so the true no-man's-land between two
 * neighbourhoods wanders as it runs inward. `sectorGeometries()` follows that:
 * at every ring it takes the midpoint of the gap, lets the line swing a little
 * within the gap for a hand-drawn feel, and threads a smooth curve through the
 * points. The result hugs the groups exactly and never crosses a node.
 */

export const SECTOR_COUNT = 8
export const SECTOR_DEGREES = 360 / SECTOR_COUNT

export interface PolarNode {
  theta: number
  r?: number
}

interface Point {
  x: number
  y: number
}

export function sectorOf(node: PolarNode): number {
  const theta = ((node.theta % 360) + 360) % 360
  return Math.min(SECTOR_COUNT - 1, Math.floor(theta / SECTOR_DEGREES))
}

/** The map flips y so it matches the design image: y grows *up* in map terms. */
function polar(radius: number, degrees: number): Point {
  const radians = (degrees * Math.PI) / 180
  return { x: radius * Math.cos(radians), y: -radius * Math.sin(radians) }
}

function fmt(point: Point): string {
  return `${point.x.toFixed(1)} ${point.y.toFixed(1)}`
}

/** Catmull-Rom through the points, emitted as cubic Béziers. First point is a `L`/`M` target. */
function spline(points: Point[]): string {
  if (points.length < 2) return ''
  const out: string[] = []
  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[Math.max(0, i - 1)]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[Math.min(points.length - 1, i + 2)]
    const c1 = { x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6 }
    const c2 = { x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6 }
    out.push(`C ${fmt(c1)} ${fmt(c2)} ${fmt(p2)}`)
  }
  return out.join(' ')
}

/**
 * For each of the eight borders, the angle it passes through at every ring,
 * inner to outer. Border `b` separates sector `b` from sector `b + 1`.
 */
function borderAngles(nodes: PolarNode[]): Map<number, number[]>[] {
  // ring radius -> thetas, skipping the centre.
  const rings = new Map<number, number[]>()
  for (const node of nodes) {
    const r = Math.round(node.r ?? 0)
    if (r <= 0) continue
    let list = rings.get(r)
    if (!list) {
      list = []
      rings.set(r, list)
    }
    list.push(((node.theta % 360) + 360) % 360)
  }

  const radii = [...rings.keys()].sort((a, b) => a - b)
  const borders: Map<number, number[]>[] = []

  for (let b = 0; b < SECTOR_COUNT; b += 1) {
    const nominal = (b + 1) * SECTOR_DEGREES
    const perRing = new Map<number, number[]>()
    radii.forEach((r, ringIndex) => {
      const thetas = rings.get(r) ?? []
      let before = -Infinity
      let after = Infinity
      for (let theta of thetas) {
        // The seam between sector 7 and sector 0 lives at 360, not 0.
        if (b === SECTOR_COUNT - 1 && theta < SECTOR_DEGREES) theta += 360
        if (theta < nominal) before = Math.max(before, theta)
        else after = Math.min(after, theta)
      }
      if (!Number.isFinite(before) || !Number.isFinite(after)) {
        perRing.set(r, [nominal])
        return
      }
      const gap = after - before
      const mid = (before + after) / 2
      // A gentle meander: a tenth of the gap, and never more than 2.5° even on
      // the inner rings where the gaps are wide. Enough to read as hand-drawn,
      // not enough to look like the border is wandering off.
      const swing = Math.min(2.5, 0.1 * gap) * Math.sin(ringIndex * 1.9 + b * 0.7)
      perRing.set(r, [mid + swing])
    })
    borders.push(perRing)
  }
  return borders
}

export interface SectorGeometry {
  index: number
  d: string
  label: Point
}

/**
 * Eight closed paths, one per sector, bounded by the wandering borders on both
 * sides, an arc along the rim and an arc around the unpainted centre.
 */
export function sectorGeometries(
  nodes: PolarNode[],
  outerRadius: number,
  innerRadius: number,
): SectorGeometry[] {
  const borders = borderAngles(nodes)
  const radii = [...(borders[0]?.keys() ?? [])].sort((a, b) => a - b)

  const borderPoints = (b: number): Point[] => {
    const ring = borders[b]
    const angles = radii.map((r) => ring.get(r)?.[0] ?? (b + 1) * SECTOR_DEGREES)
    const innermost = angles[0] ?? (b + 1) * SECTOR_DEGREES
    const outermost = angles[angles.length - 1] ?? innermost
    const points: Point[] = [polar(innerRadius, innermost)]
    radii.forEach((r, i) => points.push(polar(r, angles[i])))
    points.push(polar(outerRadius, outermost))
    return points
  }

  const out: SectorGeometry[] = []
  for (let index = 0; index < SECTOR_COUNT; index += 1) {
    const left = borderPoints((index + SECTOR_COUNT - 1) % SECTOR_COUNT) // start side
    const right = [...borderPoints(index)].reverse() // end side, walked inward

    const d = [
      `M ${fmt(left[0])}`,
      spline(left),
      // Rim: from the start border's outer point to the end border's outer point.
      `A ${outerRadius} ${outerRadius} 0 0 0 ${fmt(right[0])}`,
      spline(right),
      // Back around the hole to where we began.
      `A ${innerRadius} ${innerRadius} 0 0 1 ${fmt(left[0])}`,
      'Z',
    ].join(' ')

    out.push({
      index,
      d,
      label: polar(outerRadius - 34, index * SECTOR_DEGREES + SECTOR_DEGREES / 2),
    })
  }
  return out
}

/** Where a sector's label sits: on the bisector, just inside the rim. */
export function sectorLabelPoint(index: number, radius: number): Point {
  return polar(radius, index * SECTOR_DEGREES + SECTOR_DEGREES / 2)
}

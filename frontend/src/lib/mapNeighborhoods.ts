/**
 * Which pizza slice a node is in, and the SVG wedge that paints it.
 *
 * The map is eight 45° sectors, and every connectivity group in
 * `generateGraph.mjs` (L3 → C34 → L4 → C45 → L5 → L6) lands inside one:
 * with the layer offsets baked into the JSON, `floor(theta / 45)` puts a
 * team's whole tree in the same slice, and no node sits on a boundary. So the
 * sector is geometry the client computes, not data the server stores — the
 * server only says what each sector is called and how it is painted.
 */

export const SECTOR_COUNT = 8
export const SECTOR_DEGREES = 360 / SECTOR_COUNT

export interface PolarNode {
  theta: number
}

export function sectorOf(node: PolarNode): number {
  const theta = ((node.theta % 360) + 360) % 360
  return Math.min(SECTOR_COUNT - 1, Math.floor(theta / SECTOR_DEGREES))
}

/** The map flips y so it matches the design image: y grows *up* in map terms. */
function polar(radius: number, degrees: number): { x: number; y: number } {
  const radians = (degrees * Math.PI) / 180
  return { x: radius * Math.cos(radians), y: -radius * Math.sin(radians) }
}

/**
 * An SVG path for one sector: centre, out along the start angle, an arc along
 * the rim, back to centre. `innerRadius` leaves the very middle unpainted so
 * the CENTER node and the L6 ring are not shouted over by eight colours meeting.
 */
export function wedgePath(index: number, outerRadius: number, innerRadius = 0): string {
  const start = index * SECTOR_DEGREES
  const end = start + SECTOR_DEGREES
  const outerStart = polar(outerRadius, start)
  const outerEnd = polar(outerRadius, end)
  // SVG's sweep flag: our angles run counter-clockwise on screen because y is
  // flipped, which in SVG's clockwise-positive frame is sweep = 0.
  if (innerRadius <= 0) {
    return [
      'M 0 0',
      `L ${outerStart.x.toFixed(2)} ${outerStart.y.toFixed(2)}`,
      `A ${outerRadius} ${outerRadius} 0 0 0 ${outerEnd.x.toFixed(2)} ${outerEnd.y.toFixed(2)}`,
      'Z',
    ].join(' ')
  }
  const innerStart = polar(innerRadius, start)
  const innerEnd = polar(innerRadius, end)
  return [
    `M ${innerStart.x.toFixed(2)} ${innerStart.y.toFixed(2)}`,
    `L ${outerStart.x.toFixed(2)} ${outerStart.y.toFixed(2)}`,
    `A ${outerRadius} ${outerRadius} 0 0 0 ${outerEnd.x.toFixed(2)} ${outerEnd.y.toFixed(2)}`,
    `L ${innerEnd.x.toFixed(2)} ${innerEnd.y.toFixed(2)}`,
    `A ${innerRadius} ${innerRadius} 0 0 1 ${innerStart.x.toFixed(2)} ${innerStart.y.toFixed(2)}`,
    'Z',
  ].join(' ')
}

/** Where a sector's label sits: on the bisector, just inside the rim. */
export function sectorLabelPoint(index: number, radius: number): { x: number; y: number } {
  return polar(radius, index * SECTOR_DEGREES + SECTOR_DEGREES / 2)
}

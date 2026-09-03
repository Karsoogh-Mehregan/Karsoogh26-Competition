/**
 * Turn a `HouseSpec` into a `THREE.Group`, and repaint one without rebuilding.
 *
 * Two entry points, and the split between them is the whole performance story:
 *
 *   `buildHouse(spec)`   allocates meshes. Called when the player opens a
 *                        different node, or when scaffolding appears.
 *   `handle.paint(spec)` swaps material references. Called on every board
 *                        event — a grade, a release, a buyout — and allocates
 *                        nothing at all.
 *
 * A contest fires board events continuously; if paint rebuilt geometry the
 * panel would churn all afternoon for no visible reason.
 *
 * Composition, bottom to top: the archetype's foundation, the storey stack
 * (one box + trim per seat), instanced windows, the door and sign with the
 * theme's emblem, the archetype's roof, its props (asking the roof where its
 * surface is), and the theme's motif around the plot.
 */
import { Group, InstancedMesh, Mesh, Object3D, type Material } from 'three'

import { geometry, type GeometryKey } from './geometry'
import { SCAFFOLD, contactShadow, glass as glassMaterial, shade, solid, teamColor } from './materials'
import {
  FLOOR_H,
  HALF,
  WIDTH,
  buildEmblem,
  buildFoundation,
  buildMotif,
  buildProp,
  buildRoof,
  mesh,
  type Paint,
} from './props'
import type { HouseSpec } from './spec'
import type { Theme } from './themes'

const BODY_H = 0.86
const TRIM_H = 0.14

export interface HouseHandle {
  group: Group
  /** Height of the finished model, so the camera can frame it. */
  height: number
  paint(spec: HouseSpec): void
}

function paintFor(theme: Theme): Paint {
  const p = theme.palette
  return {
    wall: solid(p.wall),
    roof: solid(p.roof),
    trim: solid(p.trim),
    accent: solid(p.accent),
    dark: solid(shade(p.trim, 0.7)),
    base: solid(p.base),
    ground: solid(p.ground),
    glass: glassMaterial(p.glass),
    scaffold: solid(SCAFFOLD),
  }
}

function bodyY(floor: number): number {
  return (floor - 1) * FLOOR_H + BODY_H / 2
}

function trimY(floor: number): number {
  return (floor - 1) * FLOOR_H + BODY_H + TRIM_H / 2
}

// ---- instanced parts -------------------------------------------------------

interface Placement {
  x: number
  y: number
  z: number
  rotY: number
}

/** Two panes on each of the four faces, minus the ground-floor doorway. */
function windowPlacements(capacity: number): Placement[] {
  const out: Placement[] = []
  const offset = HALF + 0.02
  for (let floor = 1; floor <= capacity; floor += 1) {
    const y = bodyY(floor) + 0.06
    for (const side of [-1, 1]) {
      for (const along of [-0.46, 0.46]) {
        // The doorway takes the whole front of the ground floor.
        if (floor === 1 && side === 1) continue
        out.push({ x: along, y, z: side * offset, rotY: 0 })
      }
      for (const along of [-0.46, 0.46]) {
        out.push({ x: side * offset, y, z: along, rotY: Math.PI / 2 })
      }
    }
  }
  return out
}

function instanced(
  key: GeometryKey,
  material: Material,
  placements: Placement[],
  scale: { x: number; y: number; z: number },
): InstancedMesh | null {
  if (placements.length === 0) return null
  const item = new InstancedMesh(geometry(key), material, placements.length)
  const dummy = new Object3D()
  placements.forEach((placement, index) => {
    dummy.position.set(placement.x, placement.y, placement.z)
    dummy.rotation.set(0, placement.rotY, 0)
    dummy.scale.set(scale.x, scale.y, scale.z)
    dummy.updateMatrix()
    item.setMatrixAt(index, dummy.matrix)
  })
  item.instanceMatrix.needsUpdate = true
  return item
}

/** A reserved seat is a building site: poles at the corners, two planks across. */
function scaffoldPlacements(spec: HouseSpec): { poles: Placement[]; planks: Placement[] } {
  const poles: Placement[] = []
  const planks: Placement[] = []
  const reach = HALF + 0.12
  for (const slot of spec.floors) {
    if (slot.status !== 'reserved') continue
    const base = (slot.floor - 1) * FLOOR_H
    for (const x of [-reach, reach]) {
      for (const z of [-reach, reach]) {
        poles.push({ x, y: base + FLOOR_H / 2, z, rotY: 0 })
      }
    }
    planks.push({ x: 0, y: base + 0.3, z: reach, rotY: 0 })
    planks.push({ x: 0, y: base + 0.78, z: reach, rotY: 0 })
  }
  return { poles, planks }
}

// ---- the house -------------------------------------------------------------

export function buildHouse(spec: HouseSpec): HouseHandle {
  const group = new Group()
  const paint = paintFor(spec.theme)
  const { archetype, theme, capacity } = spec

  const foundation = buildFoundation(archetype.foundation, paint)
  for (const part of foundation.parts) group.add(part)

  // Ground shadow, drawn first and never depth-writing so nothing z-fights it.
  const shadow = mesh(
    'plane',
    contactShadow(),
    { y: foundation.groundY - 0.012 },
    { x: 5.2, y: 5.2 },
    { x: -Math.PI / 2 },
  )
  shadow.renderOrder = -1
  group.add(shadow)

  // One storey per seat: a body that carries the occupant's colour, capped by a
  // darker trim band so stacked floors stay legible from any angle.
  const bodies: Mesh[] = []
  const trims: Mesh[] = []
  for (const slot of spec.floors) {
    const body = mesh('box', paint.wall, { y: bodyY(slot.floor) }, { x: WIDTH, y: BODY_H, z: WIDTH })
    const trim = mesh(
      'box',
      paint.trim,
      { y: trimY(slot.floor) },
      { x: WIDTH + 0.16, y: TRIM_H, z: WIDTH + 0.16 },
    )
    bodies.push(body)
    trims.push(trim)
    group.add(body, trim)
  }

  const windows = instanced('box', paint.glass, windowPlacements(capacity), {
    x: 0.36,
    y: 0.44,
    z: 0.08,
  })
  if (windows) group.add(windows)

  // Doorway on the ground floor's front face, the shop sign beside it, and the
  // neighbourhood's symbol on the sign.
  group.add(mesh('box', paint.dark, { y: 0.34, z: HALF + 0.03 }, { x: 0.6, y: 0.68, z: 0.1 }))
  group.add(mesh('box', paint.glass, { y: 0.32, z: HALF + 0.07 }, { x: 0.42, y: 0.54, z: 0.06 }))
  if (archetype.awning) {
    group.add(mesh('box', paint.roof, { y: 0.86, z: HALF + 0.2 }, { x: 1.06, y: 0.07, z: 0.5 }, { x: -0.32 }))
  }
  group.add(mesh('box', paint.accent, { x: 0.72, y: 0.74, z: HALF + 0.06 }, { x: 0.5, y: 0.34, z: 0.06 }))
  for (const part of buildEmblem(theme.emblem, paint)) group.add(part)

  const roof = buildRoof(archetype.roof, capacity * FLOOR_H, paint)
  for (const part of roof.parts) group.add(part)

  let top = roof.top
  for (const kind of archetype.props) {
    const parts = buildProp(kind, roof, paint)
    for (const part of parts) {
      group.add(part)
      // Tall yard props (a watchtower, a crane) decide the framing too.
      top = Math.max(top, part.position.y + part.scale.y / 2)
    }
  }

  for (const part of buildMotif(theme.motif, capacity, foundation.groundY, paint)) {
    group.add(part)
    top = Math.max(top, part.position.y + part.scale.y / 2)
  }

  const scaffold = scaffoldPlacements(spec)
  const poles = instanced('cylinder', paint.scaffold, scaffold.poles, { x: 0.07, y: FLOOR_H, z: 0.07 })
  if (poles) group.add(poles)
  const planks = instanced('box', paint.scaffold, scaffold.planks, { x: WIDTH + 0.3, y: 0.06, z: 0.08 })
  if (planks) group.add(planks)

  const wallColor = theme.palette.wall
  const trimColor = theme.palette.trim

  const handle: HouseHandle = {
    group,
    height: top - foundation.groundY + 0.6,
    paint(next: HouseSpec) {
      next.floors.forEach((slot, index) => {
        const body = bodies[index]
        const trim = trims[index]
        if (!body || !trim) return
        if (slot.status === 'empty') {
          body.material = solid(wallColor)
          trim.material = solid(trimColor)
          return
        }
        const color = teamColor(slot.color)
        body.material = solid(color)
        trim.material = solid(shade(color))
      })
    },
  }

  handle.paint(spec)
  return handle
}

/**
 * Drop a house's meshes. Geometries and materials are pooled and deliberately
 * survive: only the per-house wrappers are thrown away, which is the cheap half
 * and the only half that is actually per-house.
 */
export function disposeHouse(handle: HouseHandle): void {
  handle.group.traverse((object) => {
    if (object instanceof InstancedMesh) {
      object.dispose()
    }
  })
  handle.group.clear()
}

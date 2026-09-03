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
 * Composition: the type's own builder in `buildings.ts` lays out the plot and
 * registers its paintable storeys; this file adds the instanced windows, the
 * contact shadow, the theme's motif around the plot, and scaffolding on any
 * storey a team has reserved but not yet earned.
 */
import { Group, InstancedMesh, Object3D, type Material } from 'three'

import { buildArchetype, type Placement } from './buildings'
import { geometry, type GeometryKey } from './geometry'
import { SCAFFOLD, contactShadow, glass as glassMaterial, shade, solid, teamColor } from './materials'
import { buildMotif, mesh, type Paint } from './props'
import type { HouseSpec } from './spec'
import type { Theme } from './themes'

export interface HouseHandle {
  group: Group
  /** Height of the finished model, so the camera can frame it. */
  height: number
  paint(spec: HouseSpec): void
}

const GRASS = 0x5f9e4a
const CROP = 0x86b04c
const WOOD = 0x8a5a3a
const METAL = 0x6e747c

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
    grass: solid(GRASS),
    crop: solid(CROP),
    wood: solid(WOOD),
    metal: solid(METAL),
  }
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

export function buildHouse(spec: HouseSpec): HouseHandle {
  const group = new Group()
  const paint = paintFor(spec.theme)
  const built = buildArchetype(spec.archetype, spec.capacity, paint, spec.theme)

  // Ground shadow, drawn first and never depth-writing so nothing z-fights it.
  const span = Math.max(built.plot.w, built.plot.d) + 3.2
  const shadow = mesh(
    'plane',
    contactShadow(),
    { x: built.plot.x, y: built.groundY - 0.012, z: built.plot.z },
    { x: span, y: span },
    { x: -Math.PI / 2 },
  )
  shadow.renderOrder = -1
  group.add(shadow)

  for (const part of built.parts) group.add(part)

  const windows = instanced('box', paint.glass, built.windows, { x: 0.34, y: 0.42, z: 0.08 })
  if (windows) group.add(windows)

  let top = built.top
  for (const part of buildMotif(spec.theme.motif, built.plot, built.groundY, paint, spec.capacity)) {
    group.add(part)
    top = Math.max(top, part.position.y + part.scale.y / 2)
  }

  // A reserved seat is a building site: poles at the corners of that storey's
  // bounds, two planks across its front.
  const poles: Placement[] = []
  const planks: Placement[] = []
  spec.floors.forEach((slot, index) => {
    if (slot.status !== 'reserved') return
    const b = built.floors[index]?.bounds
    if (!b) return
    const rx = b.w / 2 + 0.14
    const rz = b.d / 2 + 0.14
    const h = b.y1 - b.y0
    for (const sx of [-1, 1]) {
      for (const sz of [-1, 1]) {
        poles.push({ x: b.x + sx * rx, y: b.y0 + h / 2, z: b.z + sz * rz, rotY: 0 })
      }
    }
    planks.push({ x: b.x, y: b.y0 + h * 0.3, z: b.z + rz, rotY: 0 })
    planks.push({ x: b.x, y: b.y0 + h * 0.75, z: b.z + rz, rotY: 0 })
  })
  const scaffoldPoles = instanced('cylinder', paint.scaffold, poles, { x: 0.07, y: 1, z: 0.07 })
  if (scaffoldPoles) {
    // Poles are unit-height instances; stretch each to its storey.
    const dummy = new Object3D()
    poles.forEach((p, i) => {
      const b = built.floors.find((f) => Math.abs(f.bounds.y0 + (f.bounds.y1 - f.bounds.y0) / 2 - p.y) < 1e-6)?.bounds
      const h = b ? b.y1 - b.y0 : 1
      dummy.position.set(p.x, p.y, p.z)
      dummy.rotation.set(0, 0, 0)
      dummy.scale.set(0.07, h, 0.07)
      dummy.updateMatrix()
      scaffoldPoles.setMatrixAt(i, dummy.matrix)
    })
    scaffoldPoles.instanceMatrix.needsUpdate = true
    group.add(scaffoldPoles)
  }
  const scaffoldPlanks = instanced('box', paint.scaffold, planks, { x: 1, y: 0.06, z: 0.08 })
  if (scaffoldPlanks) {
    const dummy = new Object3D()
    planks.forEach((p, i) => {
      const b = built.floors.find((f) => Math.abs(f.bounds.z + f.bounds.d / 2 + 0.14 - p.z) < 1e-6)?.bounds
      dummy.position.set(p.x, p.y, p.z)
      dummy.rotation.set(0, 0, 0)
      dummy.scale.set((b?.w ?? 2) + 0.4, 0.06, 0.08)
      dummy.updateMatrix()
      scaffoldPlanks.setMatrixAt(i, dummy.matrix)
    })
    scaffoldPlanks.instanceMatrix.needsUpdate = true
    group.add(scaffoldPlanks)
  }

  const wallColor = spec.theme.palette.wall
  const trimColor = spec.theme.palette.trim

  const handle: HouseHandle = {
    group,
    height: top - built.groundY + 0.6,
    paint(next: HouseSpec) {
      next.floors.forEach((slot, index) => {
        const record = built.floors[index]
        if (!record) return
        if (slot.status === 'empty') {
          for (const body of record.bodies) body.material = solid(wallColor)
          for (const trim of record.trims) trim.material = solid(trimColor)
          return
        }
        const color = teamColor(slot.color)
        for (const body of record.bodies) body.material = solid(color)
        for (const trim of record.trims) trim.material = solid(shade(color))
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

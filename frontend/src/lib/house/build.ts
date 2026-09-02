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
 */
import { Group, InstancedMesh, Mesh, Object3D, type Material } from 'three'

import { geometry, type GeometryKey } from './geometry'
import {
  GROUND,
  NEUTRAL,
  NEUTRAL_DARK,
  SCAFFOLD,
  STONE,
  contactShadow,
  glass,
  shade,
  solid,
  teamColor,
} from './materials'
import type { HouseSpec } from './spec'

const FLOOR_H = 1
const BODY_H = 0.86
const TRIM_H = 0.14
const WIDTH = 2
const HALF = WIDTH / 2

export interface HouseHandle {
  group: Group
  /** Height of the finished model, so the camera can frame it. */
  height: number
  paint(spec: HouseSpec): void
}

interface Vec3 {
  x?: number
  y?: number
  z?: number
}

function mesh(
  key: GeometryKey,
  material: Material,
  position: Vec3,
  scale: Vec3,
  rotation?: Vec3,
): Mesh {
  const item = new Mesh(geometry(key), material)
  item.position.set(position.x ?? 0, position.y ?? 0, position.z ?? 0)
  item.scale.set(scale.x ?? 1, scale.y ?? 1, scale.z ?? 1)
  if (rotation) {
    item.rotation.set(rotation.x ?? 0, rotation.y ?? 0, rotation.z ?? 0)
  }
  return item
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

// ---- roofs and props -------------------------------------------------------

function buildRoof(spec: HouseSpec, top: number): { parts: Object3D[]; top: number } {
  const accent = solid(spec.archetype.accent)
  const stone = solid(STONE)
  const parts: Object3D[] = []

  switch (spec.archetype.roof) {
    case 'gable': {
      parts.push(
        mesh('prism', accent, { y: top + 0.38 }, { x: WIDTH + 0.3, y: 0.76, z: WIDTH + 0.3 }),
      )
      return { parts, top: top + 0.76 }
    }
    case 'hip': {
      parts.push(
        mesh(
          'pyramid',
          accent,
          { y: top + 0.42 },
          { x: WIDTH + 0.42, y: 0.84, z: WIDTH + 0.42 },
          { y: Math.PI / 4 },
        ),
      )
      return { parts, top: top + 0.84 }
    }
    case 'dome': {
      parts.push(
        mesh('box', stone, { y: top + 0.09 }, { x: WIDTH + 0.22, y: 0.18, z: WIDTH + 0.22 }),
      )
      parts.push(mesh('cylinder', stone, { y: top + 0.32 }, { x: 1.5, y: 0.3, z: 1.5 }))
      parts.push(mesh('dome', accent, { y: top + 0.46 }, { x: 1.7, y: 1.2, z: 1.7 }))
      return { parts, top: top + 1.06 }
    }
    case 'tiered': {
      parts.push(
        mesh('box', stone, { y: top + 0.08 }, { x: WIDTH + 0.24, y: 0.16, z: WIDTH + 0.24 }),
      )
      parts.push(mesh('box', accent, { y: top + 0.4 }, { x: 1.5, y: 0.48, z: 1.5 }))
      parts.push(mesh('box', stone, { y: top + 0.72 }, { x: 0.9, y: 0.18, z: 0.9 }))
      return { parts, top: top + 0.81 }
    }
    case 'flat':
    default: {
      const rail = WIDTH + 0.24
      parts.push(mesh('box', stone, { y: top + 0.08 }, { x: rail, y: 0.16, z: rail }))
      for (const side of [-1, 1]) {
        parts.push(
          mesh('box', accent, { y: top + 0.26, z: (side * rail) / 2 }, { x: rail, y: 0.2, z: 0.1 }),
        )
        parts.push(
          mesh('box', accent, { y: top + 0.26, x: (side * rail) / 2 }, { x: 0.1, y: 0.2, z: rail }),
        )
      }
      return { parts, top: top + 0.36 }
    }
  }
}

function buildProp(spec: HouseSpec, top: number): Object3D[] {
  const accent = solid(spec.archetype.accent)
  const stone = solid(STONE)
  const dark = solid(shade(spec.archetype.accent, 0.6))
  const parts: Object3D[] = []

  switch (spec.archetype.prop) {
    case 'telescope':
      parts.push(mesh('cylinder', stone, { y: top + 0.08 }, { x: 0.5, y: 0.16, z: 0.5 }))
      parts.push(
        mesh('cylinder', dark, { y: top + 0.38, z: 0.1 }, { x: 0.22, y: 0.9, z: 0.22 }, { x: -0.7 }),
      )
      break
    case 'vault':
      parts.push(
        mesh('cylinder', dark, { y: top + 0.24 }, { x: 0.66, y: 0.14, z: 0.66 }, { x: Math.PI / 2 }),
      )
      parts.push(mesh('sphere', accent, { y: top + 0.24 }, { x: 0.2, y: 0.2, z: 0.2 }))
      break
    case 'scales':
      parts.push(mesh('cylinder', dark, { y: top + 0.34 }, { x: 0.09, y: 0.68, z: 0.09 }))
      parts.push(mesh('box', dark, { y: top + 0.66 }, { x: 1, y: 0.07, z: 0.07 }))
      for (const side of [-1, 1]) {
        parts.push(
          mesh('box', accent, { x: side * 0.44, y: top + 0.52 }, { x: 0.26, y: 0.1, z: 0.26 }),
        )
      }
      break
    case 'cross':
      parts.push(mesh('box', accent, { y: top + 0.3 }, { x: 0.7, y: 0.2, z: 0.14 }))
      parts.push(mesh('box', accent, { y: top + 0.3 }, { x: 0.2, y: 0.7, z: 0.14 }))
      break
    case 'cone':
      parts.push(mesh('cone', stone, { y: top + 0.26 }, { x: 0.44, y: 0.52, z: 0.44 }, { x: Math.PI }))
      parts.push(mesh('sphere', accent, { y: top + 0.58 }, { x: 0.4, y: 0.4, z: 0.4 }))
      break
    case 'books':
      parts.push(mesh('box', accent, { y: top + 0.09 }, { x: 0.8, y: 0.18, z: 0.5 }))
      parts.push(mesh('box', dark, { y: top + 0.27, x: 0.06 }, { x: 0.72, y: 0.18, z: 0.46 }, { y: 0.3 }))
      parts.push(mesh('box', stone, { y: top + 0.43 }, { x: 0.62, y: 0.14, z: 0.42 }, { y: -0.2 }))
      break
    case 'clock':
      parts.push(mesh('box', stone, { y: top + 0.3 }, { x: 0.5, y: 0.6, z: 0.5 }))
      parts.push(
        mesh(
          'cylinder',
          accent,
          { y: top + 0.42, z: 0.27 },
          { x: 0.38, y: 0.08, z: 0.38 },
          { x: Math.PI / 2 },
        ),
      )
      break
    case 'chimney':
      parts.push(mesh('box', dark, { x: 0.6, y: top + 0.28, z: -0.4 }, { x: 0.34, y: 0.7, z: 0.34 }))
      parts.push(mesh('box', stone, { x: 0.6, y: top + 0.66, z: -0.4 }, { x: 0.46, y: 0.1, z: 0.46 }))
      break
    case 'antenna':
      parts.push(mesh('cylinder', dark, { y: top + 0.45 }, { x: 0.07, y: 0.9, z: 0.07 }))
      parts.push(mesh('sphere', accent, { y: top + 0.92 }, { x: 0.2, y: 0.2, z: 0.2 }))
      break
    case 'flag':
      parts.push(mesh('cylinder', stone, { x: -0.6, y: top + 0.5 }, { x: 0.07, y: 1, z: 0.07 }))
      parts.push(mesh('box', accent, { x: -0.28, y: top + 0.82 }, { x: 0.62, y: 0.34, z: 0.03 }))
      break
    case 'banner':
      for (const side of [-1, 1]) {
        parts.push(
          mesh('cylinder', stone, { x: side * 0.62, y: top + 0.28 }, { x: 0.07, y: 0.56, z: 0.07 }),
        )
      }
      parts.push(mesh('box', accent, { y: top + 0.42 }, { x: 1.4, y: 0.42, z: 0.05 }))
      break
    case 'crate':
      parts.push(mesh('box', dark, { x: -0.5, y: top + 0.18, z: 0.3 }, { x: 0.36, y: 0.36, z: 0.36 }))
      parts.push(
        mesh('box', accent, { x: -0.2, y: top + 0.14, z: -0.2 }, { x: 0.28, y: 0.28, z: 0.28 }, { y: 0.5 }),
      )
      break
    case 'none':
    default:
      break
  }
  return parts
}

// ---- the house -------------------------------------------------------------

export function buildHouse(spec: HouseSpec): HouseHandle {
  const group = new Group()
  const stone = solid(STONE)
  const accent = solid(spec.archetype.accent)

  // Ground shadow, drawn first and never depth-writing so nothing z-fights it.
  const shadow = mesh('plane', contactShadow(), { y: -0.455 }, { x: 4.6, y: 4.6 }, { x: -Math.PI / 2 })
  shadow.renderOrder = -1
  group.add(shadow)

  group.add(mesh('box', solid(GROUND), { y: -0.3 }, { x: 2.66, y: 0.28, z: 2.66 }))
  group.add(mesh('box', stone, { y: -0.08 }, { x: 2.28, y: 0.16, z: 2.28 }))

  // One storey per seat: a body that carries the occupant's colour, capped by a
  // darker trim band so stacked floors stay legible from any angle.
  const bodies: Mesh[] = []
  const trims: Mesh[] = []
  for (const slot of spec.floors) {
    const body = mesh('box', solid(NEUTRAL), { y: bodyY(slot.floor) }, { x: WIDTH, y: BODY_H, z: WIDTH })
    const trim = mesh(
      'box',
      solid(NEUTRAL_DARK),
      { y: trimY(slot.floor) },
      { x: WIDTH + 0.16, y: TRIM_H, z: WIDTH + 0.16 },
    )
    bodies.push(body)
    trims.push(trim)
    group.add(body, trim)
  }

  const windows = instanced('box', glass(), windowPlacements(spec.capacity), {
    x: 0.36,
    y: 0.44,
    z: 0.08,
  })
  if (windows) group.add(windows)

  // Doorway, on the ground floor's front face.
  group.add(
    mesh(
      'box',
      solid(shade(spec.archetype.accent, 0.62)),
      { y: 0.34, z: HALF + 0.03 },
      { x: 0.6, y: 0.68, z: 0.1 },
    ),
  )
  group.add(mesh('box', glass(), { y: 0.32, z: HALF + 0.07 }, { x: 0.42, y: 0.54, z: 0.06 }))
  if (spec.archetype.awning) {
    group.add(mesh('box', accent, { y: 0.86, z: HALF + 0.2 }, { x: 1.06, y: 0.07, z: 0.5 }, { x: -0.32 }))
  }
  // Shop sign beside the door, tinted to the archetype so even an empty plot
  // says which building it is.
  group.add(mesh('box', accent, { x: 0.72, y: 0.74, z: HALF + 0.06 }, { x: 0.5, y: 0.2, z: 0.06 }))

  const roof = buildRoof(spec, spec.capacity * FLOOR_H)
  for (const part of roof.parts) group.add(part)
  for (const part of buildProp(spec, roof.top)) group.add(part)

  const scaffold = scaffoldPlacements(spec)
  const scaffoldMaterial = solid(SCAFFOLD)
  const poles = instanced('cylinder', scaffoldMaterial, scaffold.poles, {
    x: 0.07,
    y: FLOOR_H,
    z: 0.07,
  })
  if (poles) group.add(poles)
  const planks = instanced('box', scaffoldMaterial, scaffold.planks, {
    x: WIDTH + 0.3,
    y: 0.06,
    z: 0.08,
  })
  if (planks) group.add(planks)

  const handle: HouseHandle = {
    group,
    height: roof.top + 1,
    paint(next: HouseSpec) {
      next.floors.forEach((slot, index) => {
        const body = bodies[index]
        const trim = trims[index]
        if (!body || !trim) return
        const color = slot.status === 'empty' ? NEUTRAL : teamColor(slot.color)
        body.material = solid(color)
        trim.material = solid(slot.status === 'empty' ? NEUTRAL_DARK : shade(color))
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

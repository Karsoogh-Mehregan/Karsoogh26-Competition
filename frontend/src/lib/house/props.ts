/**
 * Everything that is not the storey stack: what a house stands on, what it
 * wears, what sits on and around it.
 *
 * All of it is built from the eight pooled geometries in `geometry.ts` by
 * scaling — see that file for why. The one rule this file adds is that a
 * roof-mounted prop asks the roof where its surface is (`RoofInfo.surfaceY`)
 * instead of guessing a height, which is what keeps a chimney sitting *on* a
 * slope rather than floating above the ridge.
 */
import { Mesh, Object3D, type Material } from 'three'

import type { FoundationKind, PropKind, RoofKind } from './archetypes'
import { geometry, type GeometryKey } from './geometry'
import type { EmblemKind, MotifKind } from './themes'

export const WIDTH = 2
export const HALF = WIDTH / 2
export const FLOOR_H = 1

interface Vec3 {
  x?: number
  y?: number
  z?: number
}

export function mesh(
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

/** The materials a theme resolves to, so builders never look colours up. */
export interface Paint {
  wall: Material
  roof: Material
  trim: Material
  accent: Material
  dark: Material
  base: Material
  ground: Material
  glass: Material
  scaffold: Material
}

// ---- foundations ------------------------------------------------------------

export interface FoundationInfo {
  parts: Object3D[]
  /** Lowest point of the model, where the contact shadow goes. */
  groundY: number
}

export function buildFoundation(kind: FoundationKind, paint: Paint): FoundationInfo {
  const parts: Object3D[] = []
  const plinth = () => mesh('box', paint.base, { y: -0.08 }, { x: WIDTH + 0.28, y: 0.16, z: WIDTH + 0.28 })

  switch (kind) {
    case 'stepped': {
      parts.push(mesh('box', paint.ground, { y: -0.42 }, { x: 3.3, y: 0.16, z: 3.3 }))
      parts.push(mesh('box', paint.base, { y: -0.26 }, { x: 2.9, y: 0.16, z: 2.9 }))
      parts.push(mesh('box', paint.base, { y: -0.08 }, { x: WIDTH + 0.4, y: 0.2, z: WIDTH + 0.4 }))
      return { parts, groundY: -0.5 }
    }
    case 'round': {
      parts.push(mesh('cylinder', paint.ground, { y: -0.3 }, { x: 3.2, y: 0.28, z: 3.2 }))
      parts.push(mesh('cylinder', paint.base, { y: -0.08 }, { x: 2.6, y: 0.16, z: 2.6 }))
      return { parts, groundY: -0.44 }
    }
    case 'piers': {
      parts.push(mesh('box', paint.base, { y: -0.16 }, { x: WIDTH + 0.5, y: 0.16, z: WIDTH + 0.5 }))
      for (const x of [-1, 1]) {
        for (const z of [-1, 1]) {
          parts.push(mesh('cylinder', paint.dark, { x: x * 0.95, y: -0.44, z: z * 0.95 }, { x: 0.22, y: 0.4, z: 0.22 }))
        }
      }
      parts.push(mesh('box', paint.ground, { y: -0.7 }, { x: 3.0, y: 0.12, z: 3.0 }))
      return { parts, groundY: -0.76 }
    }
    case 'walled': {
      parts.push(mesh('box', paint.ground, { y: -0.3 }, { x: 3.4, y: 0.28, z: 3.4 }))
      parts.push(plinth())
      const reach = 1.62
      // Three full walls and a front wall with a gap for the path to the door.
      parts.push(mesh('box', paint.base, { y: 0.02, z: -reach }, { x: 3.4, y: 0.34, z: 0.12 }))
      parts.push(mesh('box', paint.base, { x: -reach, y: 0.02 }, { x: 0.12, y: 0.34, z: 3.4 }))
      parts.push(mesh('box', paint.base, { x: reach, y: 0.02 }, { x: 0.12, y: 0.34, z: 3.4 }))
      parts.push(mesh('box', paint.base, { x: -1.15, y: 0.02, z: reach }, { x: 1.1, y: 0.34, z: 0.12 }))
      parts.push(mesh('box', paint.base, { x: 1.15, y: 0.02, z: reach }, { x: 1.1, y: 0.34, z: 0.12 }))
      return { parts, groundY: -0.44 }
    }
    case 'mound': {
      parts.push(mesh('dome', paint.ground, { y: -0.46 }, { x: 4.0, y: 0.7, z: 4.0 }))
      parts.push(mesh('cylinder', paint.base, { y: -0.08 }, { x: 2.5, y: 0.22, z: 2.5 }))
      return { parts, groundY: -0.46 }
    }
    case 'slab':
    default: {
      parts.push(mesh('box', paint.ground, { y: -0.3 }, { x: 3.0, y: 0.28, z: 3.0 }))
      parts.push(plinth())
      return { parts, groundY: -0.44 }
    }
  }
}

// ---- roofs --------------------------------------------------------------------

export interface RoofInfo {
  parts: Object3D[]
  /** Highest point, for camera framing. */
  top: number
  /** Height of the roof surface at a point, so props can sit on it. */
  surfaceY: (x: number, z: number) => number
}

export function buildRoof(kind: RoofKind, base: number, paint: Paint): RoofInfo {
  const parts: Object3D[] = []
  const overhang = WIDTH + 0.3
  const halfOver = overhang / 2

  switch (kind) {
    case 'gable': {
      const height = 0.76
      parts.push(mesh('prism', paint.roof, { y: base + height / 2 }, { x: overhang, y: height, z: overhang }))
      return {
        parts,
        top: base + height,
        surfaceY: (x) => base + height * (1 - Math.min(1, Math.abs(x) / halfOver)),
      }
    }
    case 'hip': {
      const height = 0.84
      // A 4-segment cone is a diamond on the axes; rotating 45° squares it up,
      // at which point its half-side is radius / √2 — hence the √2 in the scale.
      const side = (WIDTH + 0.36) * Math.SQRT2
      parts.push(
        mesh('pyramid', paint.roof, { y: base + height / 2 }, { x: side, y: height, z: side }, { y: Math.PI / 4 }),
      )
      const halfSide = (WIDTH + 0.36) / 2
      return {
        parts,
        top: base + height,
        surfaceY: (x, z) =>
          base + height * (1 - Math.min(1, Math.max(Math.abs(x), Math.abs(z)) / halfSide)),
      }
    }
    case 'dome': {
      parts.push(mesh('box', paint.base, { y: base + 0.09 }, { x: WIDTH + 0.22, y: 0.18, z: WIDTH + 0.22 }))
      parts.push(mesh('cylinder', paint.base, { y: base + 0.32 }, { x: 1.5, y: 0.3, z: 1.5 }))
      const radius = 0.85
      const rise = 0.6
      const centre = base + 0.46
      parts.push(mesh('dome', paint.roof, { y: centre }, { x: radius * 2, y: rise * 2, z: radius * 2 }))
      return {
        parts,
        top: centre + rise,
        surfaceY: (x, z) => {
          const r = Math.hypot(x, z)
          if (r > radius) return base + 0.18
          return centre + rise * Math.sqrt(Math.max(0, 1 - (r / radius) ** 2))
        },
      }
    }
    case 'tiered': {
      parts.push(mesh('box', paint.base, { y: base + 0.08 }, { x: WIDTH + 0.24, y: 0.16, z: WIDTH + 0.24 }))
      parts.push(mesh('box', paint.roof, { y: base + 0.4 }, { x: 1.5, y: 0.48, z: 1.5 }))
      parts.push(mesh('box', paint.base, { y: base + 0.73 }, { x: 0.9, y: 0.18, z: 0.9 }))
      return {
        parts,
        top: base + 0.82,
        surfaceY: (x, z) => {
          const reach = Math.max(Math.abs(x), Math.abs(z))
          if (reach < 0.45) return base + 0.82
          if (reach < 0.75) return base + 0.64
          return base + 0.16
        },
      }
    }
    case 'tower': {
      parts.push(mesh('box', paint.base, { y: base + 0.08 }, { x: WIDTH + 0.24, y: 0.16, z: WIDTH + 0.24 }))
      parts.push(mesh('box', paint.wall, { y: base + 0.86 }, { x: 0.8, y: 1.4, z: 0.8 }))
      parts.push(mesh('box', paint.trim, { y: base + 1.6 }, { x: 0.92, y: 0.08, z: 0.92 }))
      const capSide = 0.9 * Math.SQRT2
      parts.push(mesh('pyramid', paint.roof, { y: base + 1.9 }, { x: capSide, y: 0.52, z: capSide }, { y: Math.PI / 4 }))
      return {
        parts,
        top: base + 2.16,
        surfaceY: (x, z) => (Math.max(Math.abs(x), Math.abs(z)) < 0.4 ? base + 2.16 : base + 0.16),
      }
    }
    case 'open': {
      // No roof: a rail around the top so the last storey reads as a deck.
      const rail = WIDTH + 0.16
      for (const side of [-1, 1]) {
        parts.push(mesh('box', paint.trim, { y: base + 0.1, z: (side * rail) / 2 }, { x: rail, y: 0.2, z: 0.08 }))
        parts.push(mesh('box', paint.trim, { y: base + 0.1, x: (side * rail) / 2 }, { x: 0.08, y: 0.2, z: rail }))
      }
      return { parts, top: base + 0.2, surfaceY: () => base }
    }
    case 'flat':
    default: {
      const rail = WIDTH + 0.24
      parts.push(mesh('box', paint.base, { y: base + 0.08 }, { x: rail, y: 0.16, z: rail }))
      for (const side of [-1, 1]) {
        parts.push(mesh('box', paint.roof, { y: base + 0.26, z: (side * rail) / 2 }, { x: rail, y: 0.2, z: 0.1 }))
        parts.push(mesh('box', paint.roof, { y: base + 0.26, x: (side * rail) / 2 }, { x: 0.1, y: 0.2, z: rail }))
      }
      return { parts, top: base + 0.36, surfaceY: () => base + 0.16 }
    }
  }
}

// ---- props ----------------------------------------------------------------------

/** Ground props stand on the plinth just outside the walls. */
const YARD = HALF + 0.42

export function buildProp(kind: PropKind, roof: RoofInfo, paint: Paint): Object3D[] {
  const parts: Object3D[] = []
  const on = (x: number, z: number) => roof.surfaceY(x, z)

  switch (kind) {
    case 'coin': {
      // A big minted disc over the door, not on the roof.
      parts.push(mesh('cylinder', paint.accent, { y: 1.35, z: HALF + 0.09 }, { x: 0.7, y: 0.08, z: 0.7 }, { x: Math.PI / 2 }))
      parts.push(mesh('cylinder', paint.dark, { y: 1.35, z: HALF + 0.14 }, { x: 0.42, y: 0.04, z: 0.42 }, { x: Math.PI / 2 }))
      break
    }
    case 'cupola': {
      const y = on(0, 0)
      parts.push(mesh('cylinder', paint.base, { y: y + 0.16 }, { x: 0.6, y: 0.32, z: 0.6 }))
      parts.push(mesh('dome', paint.accent, { y: y + 0.32 }, { x: 0.7, y: 0.5, z: 0.7 }))
      break
    }
    case 'chimney': {
      const x = 0.62
      const z = -0.42
      const foot = on(x, z)
      parts.push(mesh('box', paint.dark, { x, y: foot + 0.3, z }, { x: 0.32, y: 0.7, z: 0.32 }))
      parts.push(mesh('box', paint.base, { x, y: foot + 0.68, z }, { x: 0.42, y: 0.1, z: 0.42 }))
      break
    }
    case 'bell': {
      const y = on(0, 0)
      for (const side of [-1, 1]) {
        parts.push(mesh('box', paint.base, { x: side * 0.22, y: y + 0.28 }, { x: 0.08, y: 0.56, z: 0.08 }))
      }
      parts.push(mesh('box', paint.base, { y: y + 0.58 }, { x: 0.56, y: 0.06, z: 0.06 }))
      parts.push(mesh('dome', paint.accent, { y: y + 0.32 }, { x: 0.26, y: 0.3, z: 0.26 }, { x: Math.PI }))
      break
    }
    case 'cone': {
      const y = on(0, 0)
      parts.push(mesh('cone', paint.base, { y: y + 0.26 }, { x: 0.44, y: 0.52, z: 0.44 }, { x: Math.PI }))
      parts.push(mesh('sphere', paint.accent, { y: y + 0.6 }, { x: 0.42, y: 0.42, z: 0.42 }))
      break
    }
    case 'press': {
      const y = on(0, 0)
      parts.push(mesh('box', paint.dark, { y: y + 0.16 }, { x: 0.9, y: 0.32, z: 0.5 }))
      parts.push(mesh('cylinder', paint.accent, { y: y + 0.4 }, { x: 0.3, y: 0.9, z: 0.3 }, { z: Math.PI / 2 }))
      break
    }
    case 'flag': {
      const x = -0.55
      const z = -0.2
      const foot = on(x, z)
      parts.push(mesh('cylinder', paint.base, { x, y: foot + 0.5, z }, { x: 0.07, y: 1.0, z: 0.07 }))
      parts.push(mesh('box', paint.accent, { x: x + 0.3, y: foot + 0.82, z }, { x: 0.6, y: 0.34, z: 0.03 }))
      break
    }
    case 'gate': {
      // Two posts and a lintel at the front of the yard, framing the door.
      const z = YARD + 0.35
      for (const side of [-1, 1]) {
        parts.push(mesh('box', paint.base, { x: side * 0.7, y: 0.45, z }, { x: 0.22, y: 0.9, z: 0.22 }))
      }
      parts.push(mesh('box', paint.roof, { y: 0.98, z }, { x: 1.7, y: 0.16, z: 0.3 }))
      break
    }
    case 'goalposts': {
      const y = on(0, 0)
      for (const z of [-0.8, 0.8]) {
        for (const x of [-0.45, 0.45]) {
          parts.push(mesh('cylinder', paint.base, { x, y: y + 0.32, z }, { x: 0.06, y: 0.64, z: 0.06 }))
        }
        parts.push(mesh('box', paint.base, { y: y + 0.64, z }, { x: 0.96, y: 0.06, z: 0.06 }))
      }
      // Pitch stripes.
      for (const z of [-0.4, 0, 0.4]) {
        parts.push(mesh('box', paint.accent, { y: y + 0.01, z }, { x: 1.8, y: 0.02, z: 0.06 }))
      }
      break
    }
    case 'plots': {
      const y = on(0, 0)
      let i = 0
      for (const x of [-0.6, 0, 0.6]) {
        for (const z of [-0.6, 0, 0.6]) {
          const material = i % 2 === 0 ? paint.accent : paint.ground
          parts.push(mesh('box', material, { x, y: y + 0.04, z }, { x: 0.5, y: 0.08, z: 0.5 }))
          i += 1
        }
      }
      break
    }
    case 'watchtower': {
      const x = -YARD + 0.05
      const z = -YARD + 0.05
      parts.push(mesh('box', paint.base, { x, y: 1.1, z }, { x: 0.5, y: 2.2, z: 0.5 }))
      parts.push(mesh('box', paint.trim, { x, y: 2.25, z }, { x: 0.7, y: 0.1, z: 0.7 }))
      const capSide = 0.7 * Math.SQRT2
      parts.push(mesh('pyramid', paint.roof, { x, y: 2.5, z }, { x: capSide, y: 0.4, z: capSide }, { y: Math.PI / 4 }))
      break
    }
    case 'telescope': {
      const y = on(0, 0)
      parts.push(mesh('cylinder', paint.base, { y: y + 0.08 }, { x: 0.5, y: 0.16, z: 0.5 }))
      parts.push(mesh('cylinder', paint.dark, { y: y + 0.4, z: 0.12 }, { x: 0.22, y: 0.9, z: 0.22 }, { x: -0.7 }))
      parts.push(mesh('cylinder', paint.glass, { y: y + 0.76, z: 0.42 }, { x: 0.26, y: 0.06, z: 0.26 }, { x: -0.7 }))
      break
    }
    case 'crates': {
      const x = YARD
      parts.push(mesh('box', paint.dark, { x, y: 0.18, z: 0.35 }, { x: 0.36, y: 0.36, z: 0.36 }))
      parts.push(mesh('box', paint.accent, { x: x - 0.1, y: 0.14, z: -0.2 }, { x: 0.28, y: 0.28, z: 0.28 }, { y: 0.5 }))
      parts.push(mesh('box', paint.base, { x, y: 0.5, z: 0.35 }, { x: 0.28, y: 0.28, z: 0.28 }, { y: 0.3 }))
      break
    }
    case 'silo': {
      const x = YARD + 0.1
      const z = -0.5
      parts.push(mesh('cylinder', paint.base, { x, y: 0.75, z }, { x: 0.55, y: 1.5, z: 0.55 }))
      parts.push(mesh('dome', paint.roof, { x, y: 1.5, z }, { x: 0.6, y: 0.5, z: 0.6 }))
      break
    }
    case 'trough': {
      const z = YARD + 0.15
      parts.push(mesh('box', paint.dark, { x: -0.9, y: 0.16, z }, { x: 0.9, y: 0.22, z: 0.34 }))
      parts.push(mesh('box', paint.glass, { x: -0.9, y: 0.25, z }, { x: 0.8, y: 0.06, z: 0.26 }))
      for (const x of [-1.3, -0.5]) {
        parts.push(mesh('cylinder', paint.base, { x, y: 0.3, z: z + 0.3 }, { x: 0.06, y: 0.6, z: 0.06 }))
      }
      parts.push(mesh('box', paint.base, { x: -0.9, y: 0.5, z: z + 0.3 }, { x: 0.9, y: 0.05, z: 0.05 }))
      break
    }
    case 'cross': {
      const y = on(0, 0)
      parts.push(mesh('box', paint.accent, { y: y + 0.36 }, { x: 0.7, y: 0.2, z: 0.16 }))
      parts.push(mesh('box', paint.accent, { y: y + 0.36 }, { x: 0.2, y: 0.7, z: 0.16 }))
      break
    }
    case 'scales': {
      const y = on(0, 0)
      parts.push(mesh('cylinder', paint.dark, { y: y + 0.34 }, { x: 0.09, y: 0.68, z: 0.09 }))
      parts.push(mesh('box', paint.dark, { y: y + 0.66 }, { x: 1, y: 0.07, z: 0.07 }))
      for (const side of [-1, 1]) {
        parts.push(mesh('cylinder', paint.dark, { x: side * 0.44, y: y + 0.6 }, { x: 0.02, y: 0.14, z: 0.02 }))
        parts.push(mesh('box', paint.accent, { x: side * 0.44, y: y + 0.52 }, { x: 0.26, y: 0.06, z: 0.26 }))
      }
      break
    }
    case 'columns': {
      // A colonnade across the front, standing on the plinth.
      for (const x of [-0.85, -0.3, 0.3, 0.85]) {
        parts.push(mesh('cylinder', paint.base, { x, y: 0.45, z: HALF + 0.28 }, { x: 0.16, y: 0.9, z: 0.16 }))
      }
      parts.push(mesh('box', paint.trim, { y: 0.94, z: HALF + 0.28 }, { x: 2.0, y: 0.1, z: 0.3 }))
      break
    }
    case 'orepile': {
      const x = YARD + 0.05
      parts.push(mesh('cone', paint.dark, { x, y: 0.22, z: 0.45 }, { x: 0.6, y: 0.44, z: 0.6 }))
      parts.push(mesh('cone', paint.accent, { x: x - 0.15, y: 0.16, z: -0.25 }, { x: 0.44, y: 0.32, z: 0.44 }))
      parts.push(mesh('sphere', paint.accent, { x: x + 0.2, y: 0.08, z: -0.55 }, { x: 0.16, y: 0.16, z: 0.16 }))
      break
    }
    case 'smokestack': {
      const x = 0.62
      const z = -0.5
      const foot = on(x, z)
      parts.push(mesh('cylinder', paint.dark, { x, y: foot + 0.7, z }, { x: 0.3, y: 1.4, z: 0.3 }))
      parts.push(mesh('cylinder', paint.trim, { x, y: foot + 1.38, z }, { x: 0.38, y: 0.08, z: 0.38 }))
      parts.push(mesh('sphere', paint.ground, { x: x + 0.05, y: foot + 1.65, z }, { x: 0.36, y: 0.3, z: 0.36 }))
      break
    }
    case 'logs': {
      const x = YARD + 0.05
      for (const [dz, dy] of [
        [0.3, 0.12],
        [-0.02, 0.12],
        [0.14, 0.38],
      ]) {
        parts.push(mesh('cylinder', paint.dark, { x, y: dy, z: dz }, { x: 0.28, y: 1.1, z: 0.28 }, { z: Math.PI / 2 }))
      }
      break
    }
    case 'spool': {
      const y = on(0, 0)
      parts.push(mesh('cylinder', paint.accent, { y: y + 0.3 }, { x: 0.5, y: 0.5, z: 0.5 }))
      parts.push(mesh('cylinder', paint.dark, { y: y + 0.06 }, { x: 0.64, y: 0.08, z: 0.64 }))
      parts.push(mesh('cylinder', paint.dark, { y: y + 0.56 }, { x: 0.64, y: 0.08, z: 0.64 }))
      break
    }
    case 'anvil': {
      const x = YARD
      parts.push(mesh('box', paint.dark, { x, y: 0.14, z: 0.2 }, { x: 0.3, y: 0.28, z: 0.3 }))
      parts.push(mesh('box', paint.trim, { x, y: 0.36, z: 0.2 }, { x: 0.7, y: 0.16, z: 0.28 }))
      parts.push(mesh('cone', paint.trim, { x: x + 0.45, y: 0.36, z: 0.2 }, { x: 0.22, y: 0.3, z: 0.22 }, { z: -Math.PI / 2 }))
      break
    }
    case 'books': {
      const y = on(0, 0)
      parts.push(mesh('box', paint.accent, { y: y + 0.09 }, { x: 0.8, y: 0.18, z: 0.5 }))
      parts.push(mesh('box', paint.dark, { y: y + 0.27, x: 0.06 }, { x: 0.72, y: 0.18, z: 0.46 }, { y: 0.3 }))
      parts.push(mesh('box', paint.base, { y: y + 0.43 }, { x: 0.62, y: 0.14, z: 0.42 }, { y: -0.2 }))
      break
    }
    case 'banner': {
      const y = on(0, 0)
      for (const side of [-1, 1]) {
        parts.push(mesh('cylinder', paint.base, { x: side * 0.62, y: y + 0.3 }, { x: 0.07, y: 0.6, z: 0.07 }))
      }
      parts.push(mesh('box', paint.accent, { y: y + 0.44 }, { x: 1.4, y: 0.4, z: 0.05 }))
      break
    }
    case 'antenna': {
      const y = on(0, 0)
      parts.push(mesh('cylinder', paint.dark, { y: y + 0.45 }, { x: 0.07, y: 0.9, z: 0.07 }))
      parts.push(mesh('sphere', paint.accent, { y: y + 0.92 }, { x: 0.2, y: 0.2, z: 0.2 }))
      break
    }
  }
  return parts
}

// ---- theme dressing ---------------------------------------------------------------

/** The neighbourhood's symbol, mounted on the shop sign beside the door. */
export function buildEmblem(kind: EmblemKind, paint: Paint): Object3D[] {
  const parts: Object3D[] = []
  const x = 0.72
  const y = 0.74
  const z = HALF + 0.13

  switch (kind) {
    case 'drop':
      parts.push(mesh('sphere', paint.glass, { x, y: y - 0.02, z }, { x: 0.16, y: 0.16, z: 0.12 }))
      parts.push(mesh('cone', paint.glass, { x, y: y + 0.1, z }, { x: 0.14, y: 0.16, z: 0.1 }))
      break
    case 'flame':
      parts.push(mesh('cone', paint.accent, { x, y: y + 0.02, z }, { x: 0.18, y: 0.28, z: 0.12 }))
      parts.push(mesh('cone', paint.glass, { x, y: y - 0.02, z: z + 0.02 }, { x: 0.09, y: 0.16, z: 0.08 }))
      break
    case 'bolt':
      parts.push(mesh('box', paint.accent, { x: x + 0.04, y: y + 0.08, z }, { x: 0.07, y: 0.14, z: 0.04 }, { z: 0.5 }))
      parts.push(mesh('box', paint.accent, { x: x - 0.02, y: y - 0.02, z }, { x: 0.07, y: 0.14, z: 0.04 }, { z: -0.6 }))
      parts.push(mesh('box', paint.accent, { x: x + 0.02, y: y - 0.12, z }, { x: 0.07, y: 0.12, z: 0.04 }, { z: 0.5 }))
      break
    case 'lens':
      parts.push(mesh('cylinder', paint.dark, { x, y: y + 0.02, z }, { x: 0.22, y: 0.04, z: 0.22 }, { x: Math.PI / 2 }))
      parts.push(mesh('cylinder', paint.glass, { x, y: y + 0.02, z: z + 0.02 }, { x: 0.15, y: 0.04, z: 0.15 }, { x: Math.PI / 2 }))
      parts.push(mesh('box', paint.dark, { x: x + 0.12, y: y - 0.12, z }, { x: 0.05, y: 0.16, z: 0.04 }, { z: 0.8 }))
      break
    case 'dumbbell':
      parts.push(mesh('cylinder', paint.dark, { x, y, z }, { x: 0.04, y: 0.26, z: 0.04 }, { z: Math.PI / 2 }))
      for (const side of [-1, 1]) {
        parts.push(mesh('sphere', paint.accent, { x: x + side * 0.13, y, z }, { x: 0.1, y: 0.1, z: 0.1 }))
      }
      break
    case 'book':
      parts.push(mesh('box', paint.glass, { x: x - 0.07, y, z }, { x: 0.14, y: 0.18, z: 0.03 }, { y: 0.5 }))
      parts.push(mesh('box', paint.glass, { x: x + 0.07, y, z }, { x: 0.14, y: 0.18, z: 0.03 }, { y: -0.5 }))
      break
    case 'tablet':
      parts.push(mesh('box', paint.dark, { x, y, z }, { x: 0.18, y: 0.22, z: 0.04 }))
      parts.push(mesh('box', paint.glass, { x, y: y + 0.05, z: z + 0.02 }, { x: 0.12, y: 0.02, z: 0.02 }))
      parts.push(mesh('box', paint.glass, { x, y: y - 0.02, z: z + 0.02 }, { x: 0.12, y: 0.02, z: 0.02 }))
      break
    case 'seed':
      parts.push(mesh('sphere', paint.dark, { x, y: y - 0.04, z }, { x: 0.14, y: 0.12, z: 0.1 }))
      parts.push(mesh('cone', paint.accent, { x: x + 0.02, y: y + 0.1, z }, { x: 0.08, y: 0.16, z: 0.06 }, { z: -0.4 }))
      break
    case 'none':
    default:
      break
  }
  return parts
}

/** One signature piece per neighbourhood, dressing the plot around the house. */
export function buildMotif(kind: MotifKind, capacity: number, groundY: number, paint: Paint): Object3D[] {
  const parts: Object3D[] = []

  switch (kind) {
    case 'moat': {
      parts.push(mesh('cylinder', paint.glass, { y: groundY + 0.03 }, { x: 4.1, y: 0.06, z: 4.1 }))
      break
    }
    case 'embers': {
      for (const x of [-1, 1]) {
        for (const z of [-1, 1]) {
          const px = x * 1.35
          const pz = z * 1.35
          parts.push(mesh('cone', paint.accent, { x: px, y: 0.18, z: pz }, { x: 0.24, y: 0.36, z: 0.24 }))
          parts.push(mesh('cone', paint.glass, { x: px, y: 0.14, z: pz }, { x: 0.12, y: 0.22, z: 0.12 }))
        }
      }
      break
    }
    case 'sparks': {
      const x = -YARD - 0.05
      const z = YARD - 0.1
      parts.push(mesh('box', paint.accent, { x: x + 0.08, y: 0.9, z }, { x: 0.12, y: 0.5, z: 0.08 }, { z: 0.45 }))
      parts.push(mesh('box', paint.accent, { x: x - 0.04, y: 0.55, z }, { x: 0.12, y: 0.5, z: 0.08 }, { z: -0.55 }))
      parts.push(mesh('box', paint.accent, { x: x + 0.06, y: 0.2, z }, { x: 0.12, y: 0.4, z: 0.08 }, { z: 0.45 }))
      parts.push(mesh('sphere', paint.glass, { x: x + 0.35, y: 1.05, z: z + 0.1 }, { x: 0.1, y: 0.1, z: 0.1 }))
      parts.push(mesh('sphere', paint.glass, { x: x - 0.3, y: 0.35, z: z - 0.1 }, { x: 0.08, y: 0.08, z: 0.08 }))
      break
    }
    case 'ruins': {
      const x = -YARD - 0.05
      parts.push(mesh('cylinder', paint.base, { x, y: 0.4, z: 0.5 }, { x: 0.22, y: 0.8, z: 0.22 }))
      parts.push(mesh('cylinder', paint.base, { x, y: 0.22, z: -0.3 }, { x: 0.22, y: 0.44, z: 0.22 }))
      parts.push(mesh('cylinder', paint.base, { x: x + 0.1, y: 0.11, z: -0.95 }, { x: 0.2, y: 0.7, z: 0.2 }, { z: Math.PI / 2, y: 0.6 }))
      break
    }
    case 'pillars': {
      for (const side of [-1, 1]) {
        const x = side * 0.62
        const z = HALF + 0.3
        parts.push(mesh('cylinder', paint.base, { x, y: 0.5, z }, { x: 0.14, y: 0.8, z: 0.14 }))
        parts.push(mesh('sphere', paint.accent, { x, y: 0.12, z }, { x: 0.26, y: 0.26, z: 0.26 }))
        parts.push(mesh('sphere', paint.accent, { x, y: 0.9, z }, { x: 0.26, y: 0.26, z: 0.26 }))
      }
      break
    }
    case 'pages': {
      for (const [x, z, spin] of [
        [-1.25, 1.2, 0.4],
        [1.3, -1.1, -0.9],
      ]) {
        parts.push(mesh('box', paint.glass, { x: x - 0.14, y: 0.06, z }, { x: 0.32, y: 0.04, z: 0.42 }, { y: spin, z: 0.25 }))
        parts.push(mesh('box', paint.glass, { x: x + 0.14, y: 0.06, z }, { x: 0.32, y: 0.04, z: 0.42 }, { y: spin, z: -0.25 }))
      }
      break
    }
    case 'construction': {
      // Poles up every corner and a crane in the yard: the whole plot is a site.
      const reach = HALF + 0.14
      const height = capacity * FLOOR_H + 0.4
      for (const x of [-reach, reach]) {
        for (const z of [-reach, reach]) {
          parts.push(mesh('cylinder', paint.scaffold, { x, y: height / 2, z }, { x: 0.07, y: height, z: 0.07 }))
        }
      }
      parts.push(mesh('box', paint.scaffold, { y: height, z: reach }, { x: reach * 2 + 0.1, y: 0.06, z: 0.08 }))
      const cx = YARD + 0.15
      const cz = -YARD
      parts.push(mesh('cylinder', paint.accent, { x: cx, y: height / 2 + 0.4, z: cz }, { x: 0.12, y: height + 0.8, z: 0.12 }))
      parts.push(mesh('box', paint.accent, { x: cx - 0.7, y: height + 0.75, z: cz }, { x: 1.8, y: 0.1, z: 0.1 }))
      parts.push(mesh('cylinder', paint.dark, { x: cx - 1.3, y: height + 0.3, z: cz }, { x: 0.02, y: 0.9, z: 0.02 }))
      parts.push(mesh('box', paint.dark, { x: cx - 1.3, y: height - 0.2, z: cz }, { x: 0.24, y: 0.2, z: 0.24 }))
      break
    }
    case 'torches': {
      for (const side of [-1, 1]) {
        const x = side * 0.62
        const z = HALF + 0.3
        parts.push(mesh('cylinder', paint.dark, { x, y: 0.45, z }, { x: 0.08, y: 0.9, z: 0.08 }))
        parts.push(mesh('cone', paint.accent, { x, y: 1.02, z }, { x: 0.2, y: 0.28, z: 0.2 }))
      }
      const tx = -YARD - 0.05
      const tz = -0.6
      parts.push(mesh('box', paint.dark, { x: tx, y: 0.35, z: tz }, { x: 0.36, y: 0.7, z: 0.36 }))
      parts.push(mesh('box', paint.accent, { x: tx, y: 0.85, z: tz }, { x: 0.3, y: 0.3, z: 0.3 }, { y: 0.4 }))
      parts.push(mesh('box', paint.dark, { x: tx, y: 1.15, z: tz }, { x: 0.36, y: 0.3, z: 0.36 }))
      break
    }
    case 'roots': {
      for (const angle of [0.4, 1.9, 3.4, 4.9]) {
        const x = Math.cos(angle) * 1.55
        const z = Math.sin(angle) * 1.55
        parts.push(
          mesh('cylinder', paint.dark, { x, y: groundY + 0.12, z }, { x: 0.16, y: 0.9, z: 0.16 }, {
            z: Math.PI / 2,
            y: -angle,
          }),
        )
      }
      parts.push(mesh('cone', paint.accent, { x: YARD, y: 0.22, z: YARD - 0.2 }, { x: 0.22, y: 0.44, z: 0.22 }))
      parts.push(mesh('cone', paint.accent, { x: YARD + 0.14, y: 0.14, z: YARD + 0.05 }, { x: 0.14, y: 0.28, z: 0.14 }, { z: -0.4 }))
      break
    }
    case 'none':
    default:
      break
  }
  return parts
}

/**
 * One builder per building type. This is where a farm becomes a field with a
 * farmhouse at the back, a stadium becomes stands around a pitch, and a
 * caravanserai becomes a walled courtyard — not a shared box stack wearing a
 * different hat.
 *
 * Two rules keep the game readable through all that variety:
 *
 * 1. **Every type still has `capacity` paintable storeys.** A storey is
 *    whatever the type says it is — a tier of bleachers, a ring of arcade rooms,
 *    a drum of the observatory tower — but it is registered through
 *    `Ctx.storey()`, so `paint()` can colour it for the team that holds the seat
 *    and the scaffolding knows where to stand. Floor N is still the top.
 *
 * 2. **Everything is the eight pooled geometries, scaled.** Cows, cranes, and
 *    windmills included. Nothing here allocates a `BufferGeometry`.
 */
import { Mesh, Object3D, type InstancedMesh, type Material } from 'three'

import type { Archetype } from './archetypes'
import type { FoundationKind, RoofKind } from './archetypes'
import type { GeometryKey } from './geometry'
import { glass as glassMaterial, solid } from './materials'
import {
  buildEmblem,
  buildFoundation,
  instancedMesh,
  mesh,
  roofOn,
  type Footprint,
  type Paint,
  type Placement,
  type RoofInfo,
} from './props'
import type { Theme } from './themes'

export type Face = 'n' | 's' | 'e' | 'w'
export type { Placement } from './props'

export interface FloorBounds {
  x: number
  z: number
  w: number
  d: number
  y0: number
  y1: number
}

export interface FloorRecord {
  bodies: Mesh[]
  trims: Mesh[]
  bounds: FloorBounds
}

export interface Built {
  parts: Object3D[]
  floors: FloorRecord[]
  windows: Placement[]
  /** Meshes that wear a neighbourhood's colour, by sector index 0..7. */
  sectorParts: Mesh[][]
  /** What an unclaimed storey wears when the type does not use the theme's wall. */
  emptyWall: Material | null
  /** Whether the neighbourhood motif dresses the plot. */
  dressing: boolean
  top: number
  groundY: number
  plot: Footprint
}

export const SECTOR_COUNT = 8

const STOREY_H = 0.88
const TRIM_H = 0.12

/** Direction a face points, and the yaw that turns a +z-facing piece onto it. */
function faceOf(face: Face): { dx: number; dz: number; rotY: number } {
  switch (face) {
    case 's':
      return { dx: 0, dz: 1, rotY: 0 }
    case 'n':
      return { dx: 0, dz: -1, rotY: Math.PI }
    case 'e':
      return { dx: 1, dz: 0, rotY: Math.PI / 2 }
    case 'w':
    default:
      return { dx: -1, dz: 0, rotY: -Math.PI / 2 }
  }
}

interface Vec3 {
  x?: number
  y?: number
  z?: number
}

class Ctx {
  readonly parts: Object3D[] = []
  readonly floors: FloorRecord[] = []
  readonly windows: Placement[] = []
  readonly sectorParts: Mesh[][] = Array.from({ length: SECTOR_COUNT }, () => [])
  emptyWall: Material | null = null
  dressing = true
  top = 0
  groundY = -0.44
  plot: Footprint = { x: 0, z: 0, w: 2, d: 2 }

  readonly capacity: number
  readonly paint: Paint
  readonly theme: Theme

  constructor(capacity: number, paint: Paint, theme: Theme) {
    this.capacity = capacity
    this.paint = paint
    this.theme = theme
    for (let i = 0; i < capacity; i += 1) {
      this.floors.push({ bodies: [], trims: [], bounds: { x: 0, z: 0, w: 2, d: 2, y0: 0, y1: 1 } })
    }
  }

  // ---- primitives ------------------------------------------------------------

  m(key: GeometryKey, material: Material, pos: Vec3, scale: Vec3, rot?: Vec3): Mesh {
    const item = mesh(key, material, pos, scale, rot)
    this.parts.push(item)
    this.top = Math.max(this.top, (pos.y ?? 0) + (scale.y ?? 1) / 2)
    return item
  }

  box(material: Material, pos: Vec3, scale: Vec3, rot?: Vec3): Mesh {
    return this.m('box', material, pos, scale, rot)
  }

  cyl(material: Material, pos: Vec3, scale: Vec3, rot?: Vec3): Mesh {
    return this.m('cylinder', material, pos, scale, rot)
  }

  /** One draw call for every copy; the placement's `rotY` turns each onto its face. */
  instances(
    key: GeometryKey,
    material: Material,
    scale: { x: number; y: number; z: number },
    placements: Placement[],
  ): InstancedMesh | null {
    const item = instancedMesh(key, material, placements, scale)
    if (item === null) return null
    this.parts.push(item)
    for (const p of placements) this.top = Math.max(this.top, p.y + scale.y / 2)
    return item
  }

  /** Hand a mesh to a neighbourhood: `paint()` keeps it in that sector's colour. */
  sectorMesh(sector: number, item: Mesh) {
    this.sectorParts[sector]?.push(item)
  }

  // ---- the plot ------------------------------------------------------------------

  foundation(kind: FoundationKind, plot?: Partial<Footprint>) {
    this.plot = { ...this.plot, ...plot }
    const info = buildFoundation(kind, this.paint, this.plot)
    this.parts.push(...info.parts)
    this.groundY = info.groundY
  }

  // ---- storeys ------------------------------------------------------------------------

  /**
   * Register a paintable storey. `floor` is 1-based; several masses may belong
   * to one floor (a ring of rooms, two sides of a grandstand) and all of them
   * take the team colour together.
   */
  storey(o: {
    floor: number
    x?: number
    z?: number
    w: number
    d: number
    y0: number
    h?: number
    round?: boolean
    trim?: boolean
    material?: Material
  }): number {
    const record = this.floors[o.floor - 1]
    if (!record) return o.y0
    const h = o.h ?? STOREY_H
    const x = o.x ?? 0
    const z = o.z ?? 0
    const key: GeometryKey = o.round ? 'cylinder' : 'box'
    const body = this.m(key, o.material ?? this.paint.wall, { x, y: o.y0 + h / 2, z }, { x: o.w, y: h, z: o.d })
    record.bodies.push(body)
    let y1 = o.y0 + h
    if (o.trim !== false) {
      const trim = this.m(key, this.paint.trim, { x, y: y1 + TRIM_H / 2, z }, { x: o.w + 0.12, y: TRIM_H, z: o.d + 0.12 })
      record.trims.push(trim)
      y1 += TRIM_H
    }
    // Bounds grow to cover every mass registered for the floor.
    const b = record.bounds
    if (record.bodies.length === 1) {
      record.bounds = { x, z, w: o.w, d: o.d, y0: o.y0, y1 }
    } else {
      const minX = Math.min(b.x - b.w / 2, x - o.w / 2)
      const maxX = Math.max(b.x + b.w / 2, x + o.w / 2)
      const minZ = Math.min(b.z - b.d / 2, z - o.d / 2)
      const maxZ = Math.max(b.z + b.d / 2, z + o.d / 2)
      record.bounds = {
        x: (minX + maxX) / 2,
        z: (minZ + maxZ) / 2,
        w: maxX - minX,
        d: maxZ - minZ,
        y0: Math.min(b.y0, o.y0),
        y1: Math.max(b.y1, y1),
      }
    }
    return y1
  }

  /** The everyday case: floors 1..capacity stacked straight up on one footprint. */
  stack(o: {
    x?: number
    z?: number
    w: number
    d: number
    h?: number
    from?: number
    to?: number
    round?: boolean
    windows?: Face[]
    doorFace?: Face
  }): number {
    const from = o.from ?? 1
    const to = o.to ?? this.capacity
    const h = o.h ?? STOREY_H
    let y = 0
    for (let floor = from; floor <= to; floor += 1) {
      const y0 = (floor - 1) * (h + TRIM_H)
      y = this.storey({ floor, x: o.x, z: o.z, w: o.w, d: o.d, y0, h, round: o.round })
      if (o.windows) {
        const faces = floor === 1 && o.doorFace ? o.windows.filter((f) => f !== o.doorFace) : o.windows
        this.windowsOn({ x: o.x ?? 0, z: o.z ?? 0, w: o.w, d: o.d, y: y0 + h * 0.55 }, faces)
      }
    }
    return y
  }

  // ---- openings -------------------------------------------------------------------------

  windowsOn(m: { x: number; z: number; w: number; d: number; y: number }, faces: Face[], per = 2) {
    for (const face of faces) {
      const f = faceOf(face)
      const along = face === 'n' || face === 's' ? m.w : m.d
      const spread = per === 1 ? [0] : [-along * 0.23, along * 0.23]
      for (const s of spread) {
        this.windows.push({
          x: m.x + (f.dx * (m.w / 2 + 0.02)) + (f.dz !== 0 ? s : 0),
          y: m.y,
          z: m.z + (f.dz * (m.d / 2 + 0.02)) + (f.dx !== 0 ? s : 0),
          rotY: f.dx !== 0 ? Math.PI / 2 : 0,
        })
      }
    }
  }

  /** Six windows around a drum. */
  windowsAround(x: number, z: number, radius: number, y: number, count = 6) {
    for (let i = 0; i < count; i += 1) {
      const a = (i / count) * Math.PI * 2 + Math.PI / count
      this.windows.push({ x: x + Math.sin(a) * radius, y, z: z + Math.cos(a) * radius, rotY: a })
    }
  }

  door(m: { x: number; z: number; w: number; d: number }, face: Face = 's', width = 0.6) {
    const f = faceOf(face)
    const ox = m.x + f.dx * (m.w / 2 + 0.03)
    const oz = m.z + f.dz * (m.d / 2 + 0.03)
    const rot = { y: f.rotY }
    this.box(this.paint.dark, { x: ox, y: 0.34, z: oz }, { x: width, y: 0.68, z: 0.1 }, rot)
    this.box(this.paint.glass, { x: ox + f.dx * 0.04, y: 0.32, z: oz + f.dz * 0.04 }, { x: width - 0.18, y: 0.54, z: 0.06 }, rot)
  }

  /** The shop sign with the neighbourhood's emblem, beside the door on `face`. */
  sign(m: { x: number; z: number; w: number; d: number }, face: Face = 's', y = 0.74) {
    const f = faceOf(face)
    const side = 0.62
    const sx = m.x + f.dx * (m.w / 2 + 0.06) + (f.dz !== 0 ? side : 0)
    const sz = m.z + f.dz * (m.d / 2 + 0.06) + (f.dx !== 0 ? -side : 0)
    this.box(this.paint.accent, { x: sx, y, z: sz }, { x: 0.5, y: 0.34, z: 0.06 }, { y: f.rotY })
    const ex = sx + f.dx * 0.07
    const ez = sz + f.dz * 0.07
    this.parts.push(...buildEmblem(this.theme.emblem, this.paint, { x: ex, y, z: ez }, f.rotY))
  }

  awning(m: { x: number; z: number; w: number; d: number }, face: Face = 's', y = 0.86, width?: number) {
    const f = faceOf(face)
    this.box(
      this.paint.roof,
      { x: m.x + f.dx * (m.d / 2 + 0.2), y, z: m.z + f.dz * (m.d / 2 + 0.2) },
      { x: width ?? m.w * 0.55, y: 0.07, z: 0.5 },
      { x: -0.32 * f.dz, y: f.rotY, z: 0.32 * f.dx },
    )
  }

  roof(kind: RoofKind, plot: Footprint, base: number): RoofInfo {
    const info = roofOn(kind, plot, base, this.paint)
    this.parts.push(...info.parts)
    this.top = Math.max(this.top, info.top)
    return info
  }

  // ---- reusable props ---------------------------------------------------------------------

  fence(x0: number, z0: number, x1: number, z1: number, gapAt?: number) {
    const len = Math.hypot(x1 - x0, z1 - z0)
    const posts = Math.max(2, Math.round(len / 0.55) + 1)
    const angle = Math.atan2(x1 - x0, z1 - z0)
    for (let i = 0; i < posts; i += 1) {
      const t = i / (posts - 1)
      this.box(this.paint.wood, { x: x0 + (x1 - x0) * t, y: 0.2, z: z0 + (z1 - z0) * t }, { x: 0.07, y: 0.4, z: 0.07 })
    }
    const mid = { x: (x0 + x1) / 2, z: (z0 + z1) / 2 }
    if (gapAt == null) {
      this.box(this.paint.wood, { x: mid.x, y: 0.3, z: mid.z }, { x: 0.05, y: 0.05, z: len }, { y: angle })
      this.box(this.paint.wood, { x: mid.x, y: 0.15, z: mid.z }, { x: 0.05, y: 0.05, z: len }, { y: angle })
    } else {
      const half = len / 2 - 0.35
      for (const s of [-1, 1]) {
        const cx = mid.x + Math.sin(angle) * s * (half / 2 + 0.35)
        const cz = mid.z + Math.cos(angle) * s * (half / 2 + 0.35)
        this.box(this.paint.wood, { x: cx, y: 0.3, z: cz }, { x: 0.05, y: 0.05, z: half }, { y: angle })
        this.box(this.paint.wood, { x: cx, y: 0.15, z: cz }, { x: 0.05, y: 0.05, z: half }, { y: angle })
      }
    }
  }

  flagpole(x: number, z: number, h = 1.4, material: Material = this.paint.accent) {
    this.cyl(this.paint.metal, { x, y: h / 2, z }, { x: 0.06, y: h, z: 0.06 })
    return this.box(material, { x: x + 0.22, y: h - 0.15, z }, { x: 0.44, y: 0.26, z: 0.03 })
  }

  lantern(x: number, z: number, h = 0.9) {
    this.cyl(this.paint.metal, { x, y: h / 2, z }, { x: 0.05, y: h, z: 0.05 })
    this.box(this.paint.glass, { x, y: h + 0.08, z }, { x: 0.16, y: 0.18, z: 0.16 })
  }

  crate(x: number, z: number, size = 0.34, y = size / 2, spin = 0) {
    this.box(this.paint.wood, { x, y, z }, { x: size, y: size, z: size }, { y: spin })
  }

  barrel(x: number, z: number, r = 0.3, h = 0.4) {
    this.cyl(this.paint.wood, { x, y: h / 2, z }, { x: r, y: h, z: r })
    this.cyl(this.paint.metal, { x, y: h * 0.3, z }, { x: r + 0.02, y: 0.03, z: r + 0.02 })
    this.cyl(this.paint.metal, { x, y: h * 0.7, z }, { x: r + 0.02, y: 0.03, z: r + 0.02 })
  }

  steps(x: number, z: number, w: number, count = 3, depth = 0.22) {
    for (let i = 0; i < count; i += 1) {
      this.box(this.paint.base, { x, y: -0.02 - i * 0.07, z: z + i * depth }, { x: w - i * 0.1, y: 0.08, z: depth })
    }
  }

  columns(xs: number[], z: number, h: number, r = 0.16) {
    for (const x of xs) {
      this.cyl(this.paint.base, { x, y: h / 2, z }, { x: r, y: h, z: r })
      this.box(this.paint.base, { x, y: h - 0.04, z }, { x: r + 0.1, y: 0.08, z: r + 0.1 })
    }
  }

  animal(x: number, z: number, length: number, height: number, material: Material, rotY = 0) {
    const s = Math.sin(rotY)
    const c = Math.cos(rotY)
    this.box(material, { x, y: height, z }, { x: length, y: height * 0.55, z: length * 0.42 }, { y: rotY })
    for (const lx of [-length * 0.32, length * 0.32]) {
      for (const lz of [-length * 0.14, length * 0.14]) {
        this.cyl(this.paint.dark, { x: x + lx * c + lz * s, y: height * 0.38, z: z - lx * s + lz * c }, { x: 0.06, y: height * 0.75, z: 0.06 })
      }
    }
    const hx = length * 0.58
    this.box(material, { x: x + hx * c, y: height * 1.25, z: z - hx * s }, { x: length * 0.3, y: height * 0.4, z: length * 0.3 }, { y: rotY })
  }

  finish(): Built {
    return {
      parts: this.parts,
      floors: this.floors,
      windows: this.windows,
      sectorParts: this.sectorParts,
      emptyWall: this.emptyWall,
      dressing: this.dressing,
      top: this.top,
      groundY: this.groundY,
      plot: this.plot,
    }
  }
}

type Builder = (c: Ctx) => void

// ---- the buildings -----------------------------------------------------------------

const BUILDERS: Record<string, Builder> = {
  /** Heavy stepped stone blocks, a giant coin over the door, a press on the roof. */
  mint(c) {
    c.foundation('stepped', { w: 2.6, d: 2.0 })
    let y = 0
    for (let f = 1; f <= c.capacity; f += 1) {
      const w = 2.6 - (f - 1) * 0.3
      const d = 2.0 - (f - 1) * 0.22
      y = c.storey({ floor: f, w, d, y0: y, h: 0.8 })
      c.windowsOn({ x: 0, z: 0, w, d, y: y - 0.5 }, ['e', 'w'], 1)
    }
    const topW = 2.6 - (c.capacity - 1) * 0.3
    const topD = 2.0 - (c.capacity - 1) * 0.22
    c.roof('flat', { x: 0, z: 0, w: topW, d: topD }, y)
    c.door({ x: 0, z: 0, w: 2.6, d: 2.0 }, 's', 0.7)
    c.sign({ x: 0, z: 0, w: 2.6, d: 2.0 }, 's')
    c.cyl(c.paint.accent, { y: 1.35, z: 1.06 }, { x: 0.8, y: 0.08, z: 0.8 }, { x: Math.PI / 2 })
    c.cyl(c.paint.dark, { y: 1.35, z: 1.11 }, { x: 0.5, y: 0.04, z: 0.5 }, { x: Math.PI / 2 })
    // The press: a frame and a piston.
    c.box(c.paint.metal, { y: y + 0.36 }, { x: 0.9, y: 0.4, z: 0.6 })
    c.cyl(c.paint.dark, { y: y + 0.82 }, { x: 0.26, y: 0.5, z: 0.26 })
    c.box(c.paint.metal, { y: y + 1.1 }, { x: 0.6, y: 0.1, z: 0.5 })
    for (const [x, z, n] of [
      [1.55, 0.6, 4],
      [1.6, 1.0, 2],
      [-1.55, 0.8, 3],
    ]) {
      for (let i = 0; i < n; i += 1) c.cyl(c.paint.accent, { x, y: 0.03 + i * 0.06, z }, { x: 0.3, y: 0.05, z: 0.3 })
    }
  },

  /** A civic front: centre block with a clock tower, two lower wings, wide steps. */
  cityhall(c) {
    c.foundation('stepped', { w: 3.0, d: 1.8 })
    const y = c.stack({ w: 1.4, d: 1.8, windows: ['n', 'e', 'w'] })
    const wingTop = Math.max(1, c.capacity - 1)
    for (const x of [-1.1, 1.1]) {
      const yw = c.stack({ x, w: 0.8, d: 1.5, to: wingTop, windows: ['n', 's'] })
      c.roof('hip', { x, z: 0, w: 0.8, d: 1.5 }, yw)
      c.flagpole(x, -0.9, yw + 0.9)
    }
    c.roof('flat', { x: 0, z: 0, w: 1.4, d: 1.8 }, y)
    c.box(c.paint.wall, { y: y + 0.76 }, { x: 0.66, y: 1.2, z: 0.66 })
    c.cyl(c.paint.accent, { y: y + 1.0, z: 0.34 }, { x: 0.42, y: 0.06, z: 0.42 }, { x: Math.PI / 2 })
    c.box(c.paint.dark, { y: y + 1.0, z: 0.38 }, { x: 0.04, y: 0.16, z: 0.02 })
    c.box(c.paint.trim, { y: y + 1.4 }, { x: 0.78, y: 0.08, z: 0.78 })
    c.m('pyramid', c.paint.roof, { y: y + 1.7 }, { x: 0.8 * Math.SQRT2, y: 0.52, z: 0.8 * Math.SQRT2 }, { y: Math.PI / 4 })
    c.door({ x: 0, z: 0, w: 1.4, d: 1.8 }, 's', 0.7)
    c.sign({ x: 0, z: 0, w: 1.4, d: 1.8 }, 's')
    c.steps(0, 0.95, 1.6)
  },

  /** A low cottage with a domed oven out back and bread on a table under the awning. */
  bakery(c) {
    c.foundation('slab', { w: 2.4, d: 1.8 })
    const y = c.stack({ w: 2.4, d: 1.6, h: 0.78, windows: ['n', 'e', 'w', 's'], doorFace: 's' })
    c.roof('gable', { x: 0, z: 0, w: 2.4, d: 1.6 }, y)
    c.door({ x: 0, z: 0, w: 2.4, d: 1.6 }, 's')
    c.sign({ x: 0, z: 0, w: 2.4, d: 1.6 }, 's')
    c.awning({ x: 0, z: 0, w: 2.4, d: 1.6 }, 's', 0.8, 1.6)
    // The oven: a stone dome on a block, its own tall chimney behind the house.
    c.box(c.paint.base, { x: 0.75, y: 0.25, z: -1.25 }, { x: 0.9, y: 0.5, z: 0.7 })
    c.m('dome', c.paint.base, { x: 0.75, y: 0.5, z: -1.25 }, { x: 0.8, y: 0.6, z: 0.8 })
    c.box(c.paint.glass, { x: 0.75, y: 0.36, z: -0.88 }, { x: 0.3, y: 0.22, z: 0.06 })
    c.box(c.paint.dark, { x: 0.75, y: 1.1, z: -1.4 }, { x: 0.3, y: 1.4, z: 0.3 })
    c.box(c.paint.base, { x: 0.75, y: 1.84, z: -1.4 }, { x: 0.42, y: 0.1, z: 0.42 })
    // Bread on a table.
    c.box(c.paint.wood, { x: -0.7, y: 0.36, z: 1.15 }, { x: 0.8, y: 0.06, z: 0.4 })
    for (const dx of [-0.25, 0, 0.25]) c.m('sphere', c.paint.accent, { x: -0.7 + dx, y: 0.46, z: 1.15 }, { x: 0.2, y: 0.14, z: 0.14 })
    c.m('sphere', c.paint.ground, { x: 1.0, y: 0.2, z: 1.1 }, { x: 0.36, y: 0.42, z: 0.36 })
  },

  /** A house with a terrace of tables and umbrellas out front. */
  restaurant(c) {
    c.foundation('walled', { w: 2.0, d: 1.6 })
    const y = c.stack({ z: -0.35, w: 2.0, d: 1.6, windows: ['n', 'e', 'w', 's'], doorFace: 's' })
    c.roof('hip', { x: 0, z: -0.35, w: 2.0, d: 1.6 }, y)
    c.door({ x: 0, z: -0.35, w: 2.0, d: 1.6 }, 's')
    c.sign({ x: 0, z: -0.35, w: 2.0, d: 1.6 }, 's')
    c.awning({ x: 0, z: -0.35, w: 2.0, d: 1.6 }, 's', 0.86, 1.4)
    c.box(c.paint.base, { y: 0.03, z: 1.05 }, { x: 2.6, y: 0.06, z: 1.2 })
    for (const x of [-0.85, 0, 0.85]) {
      c.cyl(c.paint.metal, { x, y: 0.2, z: 1.05 }, { x: 0.06, y: 0.4, z: 0.06 })
      c.cyl(c.paint.wood, { x, y: 0.42, z: 1.05 }, { x: 0.46, y: 0.04, z: 0.46 })
      c.cyl(c.paint.metal, { x, y: 0.85, z: 1.05 }, { x: 0.04, y: 0.9, z: 0.04 })
      c.m('cone', c.paint.accent, { x, y: 1.32, z: 1.05 }, { x: 0.7, y: 0.2, z: 0.7 })
    }
    c.lantern(-1.35, 1.6)
    c.lantern(1.35, 1.6)
  },

  /** A long low block with a bell tower at one end and a yard with a flagpole. */
  school(c) {
    c.foundation('slab', { w: 3.0, d: 1.4 })
    const y = c.stack({ x: 0.2, z: -0.3, w: 2.6, d: 1.4, h: 0.8, windows: ['n', 's', 'e'], doorFace: 's' })
    c.roof('gable', { x: 0.2, z: -0.3, w: 2.6, d: 1.4 }, y)
    const th = y + 0.9
    c.box(c.paint.wall, { x: -1.35, y: th / 2, z: -0.3 }, { x: 0.62, y: th, z: 0.62 })
    c.box(c.paint.trim, { x: -1.35, y: th + 0.04, z: -0.3 }, { x: 0.74, y: 0.08, z: 0.74 })
    for (const s of [-1, 1]) c.box(c.paint.trim, { x: -1.35 + s * 0.28, y: th + 0.34, z: -0.3 }, { x: 0.06, y: 0.5, z: 0.06 })
    c.m('dome', c.paint.accent, { x: -1.35, y: th + 0.5, z: -0.3 }, { x: 0.28, y: 0.3, z: 0.28 }, { x: Math.PI })
    c.m('pyramid', c.paint.roof, { x: -1.35, y: th + 0.86, z: -0.3 }, { x: 0.78 * Math.SQRT2, y: 0.5, z: 0.78 * Math.SQRT2 }, { y: Math.PI / 4 })
    c.door({ x: 0.2, z: -0.3, w: 2.6, d: 1.4 }, 's', 0.7)
    c.sign({ x: 0.2, z: -0.3, w: 2.6, d: 1.4 }, 's')
    c.flagpole(1.35, 1.1, 1.6)
    c.box(c.paint.wood, { x: -0.4, y: 0.2, z: 1.1 }, { x: 1.0, y: 0.06, z: 0.3 })
    for (const dx of [-0.4, 0.4]) c.box(c.paint.wood, { x: -0.4 + dx, y: 0.1, z: 1.1 }, { x: 0.06, y: 0.2, z: 0.26 })
  },

  /** A round kiosk with a cone roof and a scoop on top. */
  icecream(c) {
    c.foundation('round', { w: 1.9, d: 1.9 })
    const y = c.stack({ w: 1.9, d: 1.9, round: true, h: 0.84 })
    for (let f = 1; f <= c.capacity; f += 1) c.windowsAround(0, 0, 0.97, (f - 1) * 0.96 + 0.5, 5)
    c.m('cone', c.paint.accent, { y: 0.96 }, { x: 2.5, y: 0.22, z: 2.5 })
    c.m('cone', c.paint.roof, { y: y + 0.45 }, { x: 2.2, y: 0.9, z: 2.2 }, { x: Math.PI })
    c.m('cone', c.paint.base, { y: y + 1.1 }, { x: 0.6, y: 0.5, z: 0.6 }, { x: Math.PI })
    c.m('sphere', c.paint.glass, { y: y + 1.5 }, { x: 0.62, y: 0.6, z: 0.62 })
    c.m('sphere', c.paint.accent, { y: y + 1.86 }, { x: 0.18, y: 0.18, z: 0.18 })
    c.box(c.paint.dark, { y: 0.5, z: 0.98 }, { x: 0.9, y: 0.5, z: 0.06 })
    c.box(c.paint.wood, { y: 0.27, z: 1.06 }, { x: 1.0, y: 0.06, z: 0.24 })
    c.sign({ x: 0, z: 0, w: 1.9, d: 1.9 }, 'e', 0.7)
  },

  /** A press hall with a sawtooth roof, a billboard on stilts, paper rolls in the yard. */
  newspaper(c) {
    c.foundation('slab', { w: 2.6, d: 2.0 })
    const y = c.stack({ w: 2.6, d: 2.0, h: 0.8, windows: ['e', 'w', 'n', 's'], doorFace: 's' })
    for (const x of [-0.65, 0.65]) c.roof('gable', { x, z: 0, w: 1.1, d: 2.0 }, y)
    c.door({ x: 0, z: 0, w: 2.6, d: 2.0 }, 's', 0.8)
    c.sign({ x: 0, z: 0, w: 2.6, d: 2.0 }, 's')
    c.awning({ x: 0, z: 0, w: 2.6, d: 2.0 }, 's', 0.82, 1.2)
    for (const x of [-0.7, 0.7]) c.cyl(c.paint.metal, { x, y: y + 0.9, z: -0.3 }, { x: 0.07, y: 1.2, z: 0.07 })
    c.box(c.paint.accent, { y: y + 1.3, z: -0.3 }, { x: 2.0, y: 0.7, z: 0.06 })
    c.box(c.paint.glass, { y: y + 1.3, z: -0.26 }, { x: 1.7, y: 0.42, z: 0.02 })
    for (const [x, z] of [
      [1.7, 0.6],
      [1.7, 0.1],
      [1.7, 0.35],
    ]) c.cyl(c.paint.ground, { x, y: 0.2, z }, { x: 0.4, y: 0.5, z: 0.4 }, { z: Math.PI / 2 })
    for (let i = 0; i < 5; i += 1) c.box(c.paint.ground, { x: -1.55, y: 0.03 + i * 0.05, z: 0.9 }, { x: 0.5, y: 0.04, z: 0.36 }, { y: i * 0.1 })
  },

  /** A tall narrow tower with a balcony on every floor and a canopy over the door. */
  hotel(c) {
    c.foundation('stepped', { w: 1.6, d: 1.6 })
    const y = c.stack({ w: 1.6, d: 1.6, h: 0.9, windows: ['n', 'e', 'w', 's'], doorFace: 's' })
    for (let f = 2; f <= c.capacity; f += 1) {
      const by = (f - 1) * 1.02 + 0.02
      c.box(c.paint.base, { y: by, z: 0.98 }, { x: 1.8, y: 0.06, z: 0.34 })
      c.box(c.paint.metal, { y: by + 0.18, z: 1.14 }, { x: 1.8, y: 0.3, z: 0.03 })
    }
    c.roof('tiered', { x: 0, z: 0, w: 1.6, d: 1.6 }, y)
    c.door({ x: 0, z: 0, w: 1.6, d: 1.6 }, 's')
    c.sign({ x: 0, z: 0, w: 1.6, d: 1.6 }, 'e')
    for (const x of [-0.6, 0.6]) c.cyl(c.paint.metal, { x, y: 0.5, z: 1.4 }, { x: 0.05, y: 1.0, z: 0.05 })
    c.box(c.paint.accent, { y: 1.02, z: 1.2 }, { x: 1.5, y: 0.06, z: 0.7 })
    c.flagpole(0, 0, y + 0.8 + 0.2)
    c.box(c.paint.accent, { y: y + 0.55, z: 0.6 }, { x: 1.2, y: 0.3, z: 0.05 })
  },

  /** A walled courtyard: rooms around the edge, an arched gate, a fountain in the middle. */
  caravanserai(c) {
    c.foundation('slab', { w: 3.2, d: 3.2 })
    const H = 0.72
    let y = 0
    for (let f = 1; f <= c.capacity; f += 1) {
      const y0 = (f - 1) * (H + TRIM_H)
      y = c.storey({ floor: f, z: -1.25, w: 3.2, d: 0.7, y0, h: H })
      c.storey({ floor: f, x: -1.25, w: 0.7, d: 1.8, y0, h: H })
      c.storey({ floor: f, x: 1.25, w: 0.7, d: 1.8, y0, h: H })
      c.storey({ floor: f, x: -1.05, z: 1.25, w: 1.1, d: 0.7, y0, h: H })
      c.storey({ floor: f, x: 1.05, z: 1.25, w: 1.1, d: 0.7, y0, h: H })
      c.windowsOn({ x: 0, z: -1.25, w: 3.2, d: 0.7, y: y0 + 0.42 }, ['n'])
      c.windowsOn({ x: -1.25, z: 0, w: 0.7, d: 1.8, y: y0 + 0.42 }, ['w'])
      c.windowsOn({ x: 1.25, z: 0, w: 0.7, d: 1.8, y: y0 + 0.42 }, ['e'])
    }
    for (const [x, z] of [
      [-1.25, -1.25],
      [1.25, -1.25],
      [-1.25, 1.25],
      [1.25, 1.25],
    ]) c.m('dome', c.paint.roof, { x, y, z }, { x: 0.7, y: 0.5, z: 0.7 })
    const gh = y + 0.5
    for (const x of [-0.5, 0.5]) c.box(c.paint.base, { x, y: gh / 2, z: 1.3 }, { x: 0.3, y: gh, z: 0.6 })
    c.box(c.paint.roof, { y: gh + 0.1, z: 1.3 }, { x: 1.3, y: 0.24, z: 0.7 })
    c.cyl(c.paint.dark, { y: gh - 0.35, z: 1.3 }, { x: 0.7, y: 0.5, z: 0.7 }, { x: Math.PI / 2 })
    c.cyl(c.paint.base, { y: 0.12 }, { x: 0.8, y: 0.24, z: 0.8 })
    c.cyl(c.paint.glass, { y: 0.22 }, { x: 0.64, y: 0.06, z: 0.64 })
    c.cyl(c.paint.base, { y: 0.45 }, { x: 0.14, y: 0.5, z: 0.14 })
    c.m('sphere', c.paint.glass, { y: 0.72 }, { x: 0.2, y: 0.2, z: 0.2 })
    c.sign({ x: 0.5, z: 1.3, w: 0.3, d: 0.6 }, 's', 0.7)
  },

  /** A pitch with goals, stands rising in tiers on both long sides, floodlights. */
  stadium(c) {
    c.foundation('slab', { w: 3.2, d: 2.6 })
    c.box(c.paint.grass, { y: 0.03 }, { x: 2.6, y: 0.06, z: 1.6 })
    c.box(c.paint.glass, { y: 0.065 }, { x: 0.05, y: 0.01, z: 1.5 })
    c.cyl(c.paint.glass, { y: 0.065 }, { x: 0.5, y: 0.01, z: 0.5 })
    for (const s of [-1, 1]) {
      const gx = s * 1.2
      for (const dz of [-0.35, 0.35]) c.cyl(c.paint.base, { x: gx, y: 0.28, z: dz }, { x: 0.05, y: 0.5, z: 0.05 })
      c.box(c.paint.base, { x: gx, y: 0.53, z: 0 }, { x: 0.05, y: 0.05, z: 0.75 })
    }
    for (let f = 1; f <= c.capacity; f += 1) {
      const y0 = (f - 1) * 0.42
      const z = 1.05 + (f - 1) * 0.4
      c.storey({ floor: f, z: -z, w: 3.0, d: 0.42, y0, h: 0.4, trim: false })
      c.storey({ floor: f, z, w: 3.0, d: 0.42, y0, h: 0.4, trim: false })
      c.box(c.paint.trim, { y: y0 + 0.42, z: -z - 0.16 }, { x: 3.0, y: 0.04, z: 0.06 })
      c.box(c.paint.trim, { y: y0 + 0.42, z: z + 0.16 }, { x: 3.0, y: 0.04, z: 0.06 })
    }
    for (const x of [-1.65, 1.65]) {
      for (const z of [-1.4, 1.4]) {
        c.cyl(c.paint.metal, { x, y: 1.2, z }, { x: 0.07, y: 2.4, z: 0.07 })
        c.box(c.paint.glass, { x: x * 0.92, y: 2.45, z: z * 0.92 }, { x: 0.36, y: 0.24, z: 0.1 }, { y: Math.atan2(-x, -z) })
      }
    }
    c.box(c.paint.base, { x: -1.55, y: 0.35, z: 0 }, { x: 0.3, y: 0.7, z: 0.9 })
    c.box(c.paint.dark, { x: -1.7, y: 0.3, z: 0 }, { x: 0.02, y: 0.5, z: 0.5 })
    c.sign({ x: -1.55, z: 0, w: 0.3, d: 0.9 }, 'w', 0.5)
  },

  /** A field first: plots and furrows in front, a farmhouse at the back, a windmill, a fence. */
  farm(c) {
    c.foundation('slab', { w: 3.2, d: 3.0 })
    const house = { x: -0.8, z: -0.9, w: 1.3, d: 1.1 }
    const y = c.stack({ ...house, h: 0.72, windows: ['n', 'w', 's'], doorFace: 's' })
    c.roof('gable', house, y)
    c.door(house, 's', 0.5)
    c.sign(house, 's', 0.6)
    // The land: twelve plots, furrowed, fenced.
    let i = 0
    for (const px of [-1.05, -0.35, 0.35, 1.05]) {
      for (const pz of [0.15, 0.65, 1.15]) {
        const material = i % 3 === 0 ? c.paint.crop : i % 3 === 1 ? c.paint.ground : c.paint.dark
        c.box(material, { x: px, y: 0.04, z: pz }, { x: 0.62, y: 0.08, z: 0.44 })
        if (i % 3 === 0) {
          for (const dx of [-0.18, 0, 0.18]) c.m('cone', c.paint.crop, { x: px + dx, y: 0.16, z: pz }, { x: 0.1, y: 0.18, z: 0.1 })
        }
        i += 1
      }
    }
    c.fence(-1.45, -0.1, 1.45, -0.1)
    c.fence(-1.45, 1.45, 1.45, 1.45, 0)
    c.fence(-1.45, -0.1, -1.45, 1.45)
    c.fence(1.45, -0.1, 1.45, 1.45)
    // Windmill.
    const mx = 1.0
    const mz = -0.95
    c.cyl(c.paint.base, { x: mx, y: 0.8, z: mz }, { x: 0.6, y: 1.6, z: 0.6 })
    c.m('cone', c.paint.roof, { x: mx, y: 1.78, z: mz }, { x: 0.7, y: 0.36, z: 0.7 })
    c.cyl(c.paint.dark, { x: mx, y: 1.3, z: mz + 0.34 }, { x: 0.12, y: 0.1, z: 0.12 }, { x: Math.PI / 2 })
    for (let k = 0; k < 4; k += 1) {
      c.box(c.paint.wood, { x: mx, y: 1.3, z: mz + 0.4 }, { x: 0.12, y: 1.3, z: 0.03 }, { z: (k * Math.PI) / 2 + 0.4 })
    }
    // Scarecrow in the field.
    c.cyl(c.paint.wood, { x: 0.35, y: 0.45, z: 0.65 }, { x: 0.05, y: 0.9, z: 0.05 })
    c.box(c.paint.wood, { x: 0.35, y: 0.7, z: 0.65 }, { x: 0.5, y: 0.05, z: 0.05 })
    c.m('sphere', c.paint.accent, { x: 0.35, y: 0.98, z: 0.65 }, { x: 0.18, y: 0.18, z: 0.18 })
  },

  /** A stretch of wall with battlements, a gate, and a watchtower rising through it. */
  guardpost(c) {
    c.foundation('slab', { w: 3.2, d: 1.0 })
    c.box(c.paint.base, { x: 0.35, y: 0.45 }, { x: 2.5, y: 0.9, z: 0.5 })
    for (let i = 0; i < 6; i += 1) c.box(c.paint.base, { x: -0.6 + i * 0.44, y: 1.0 }, { x: 0.2, y: 0.2, z: 0.5 })
    c.box(c.paint.dark, { x: 0.5, y: 0.34, z: 0.27 }, { x: 0.5, y: 0.68, z: 0.04 })
    c.box(c.paint.dark, { x: 0.5, y: 0.34, z: -0.27 }, { x: 0.5, y: 0.68, z: 0.04 })
    const tower = { x: -1.15, z: 0, w: 0.95, d: 0.95 }
    const y = c.stack({ ...tower, h: 0.8, windows: ['n', 'w'] })
    for (const [dx, dz] of [
      [-0.38, -0.38],
      [0.38, -0.38],
      [-0.38, 0.38],
      [0.38, 0.38],
      [0, -0.4],
      [0, 0.4],
    ]) c.box(c.paint.base, { x: tower.x + dx, y: y + 0.12, z: dz }, { x: 0.2, y: 0.24, z: 0.2 })
    c.flagpole(tower.x, 0, y + 0.8)
    c.door(tower, 's', 0.5)
    c.sign(tower, 's', 0.62)
    for (const x of [-0.2, 1.4]) c.lantern(x, 0.45, 0.6)
  },

  /** A round tower of drums, a slit dome with a telescope, a small annex. */
  observatory(c) {
    c.foundation('round', { w: 1.9, d: 1.9 })
    const y = c.stack({ w: 1.9, d: 1.9, round: true })
    for (let f = 1; f <= c.capacity; f += 1) c.windowsAround(0, 0, 0.97, (f - 1) * 1.0 + 0.5, 6)
    const roof = c.roof('dome', { x: 0, z: 0, w: 1.9, d: 1.9 }, y)
    c.box(c.paint.dark, { y: roof.top - 0.2, z: 0.3 }, { x: 0.2, y: 0.5, z: 0.7 }, { x: -0.5 })
    c.cyl(c.paint.metal, { y: roof.top - 0.05, z: 0.45 }, { x: 0.2, y: 0.9, z: 0.2 }, { x: -0.7 })
    c.cyl(c.paint.glass, { y: roof.top + 0.3, z: 0.78 }, { x: 0.24, y: 0.06, z: 0.24 }, { x: -0.7 })
    const annex = { x: 1.15, z: 0.4, w: 0.9, d: 0.8 }
    c.box(c.paint.wall, { x: annex.x, y: 0.38, z: annex.z }, { x: annex.w, y: 0.76, z: annex.d })
    c.roof('flat', annex, 0.76)
    c.door(annex, 's', 0.42)
    c.sign(annex, 's', 0.6)
    for (let i = 0; i < 5; i += 1) {
      const a = 2.2 + i * 0.45
      c.box(c.paint.base, { x: Math.sin(a) * 1.05, y: 0.12 + i * 0.16, z: Math.cos(a) * 1.05 }, { x: 0.36, y: 0.06, z: 0.22 }, { y: a })
    }
  },

  /** A corner shop: produce stand under a striped awning, crates stacked at the side. */
  grocery(c) {
    c.foundation('slab', { w: 2.0, d: 1.6 })
    const shop = { x: 0, z: -0.2, w: 2.0, d: 1.6 }
    const y = c.stack({ ...shop, h: 0.82, windows: ['n', 'e', 'w'] })
    c.roof('flat', shop, y)
    c.door(shop, 's', 0.6)
    c.sign(shop, 's')
    for (let i = 0; i < 4; i += 1) {
      c.box(i % 2 ? c.paint.accent : c.paint.glass, { x: -0.6 + i * 0.4, y: 0.88, z: 0.95 }, { x: 0.4, y: 0.06, z: 0.55 }, { x: -0.3 })
    }
    c.box(c.paint.wood, { x: -0.55, y: 0.3, z: 0.95 }, { x: 0.9, y: 0.06, z: 0.5 })
    for (const dx of [-0.3, 0, 0.3]) {
      c.m('sphere', c.paint.crop, { x: -0.55 + dx, y: 0.4, z: 0.85 }, { x: 0.16, y: 0.16, z: 0.16 })
      c.m('sphere', c.paint.accent, { x: -0.55 + dx, y: 0.4, z: 1.06 }, { x: 0.16, y: 0.16, z: 0.16 })
    }
    c.crate(1.3, 0.3)
    c.crate(1.3, 0.3, 0.34, 0.51, 0.3)
    c.crate(1.3, 0.75, 0.3, 0.15, 0.6)
  },

  /** A barn, a silo, a paddock with cows. */
  dairy(c) {
    c.foundation('slab', { w: 3.0, d: 2.6 })
    const barn = { x: -0.5, z: -0.5, w: 2.0, d: 1.6 }
    const y = c.stack({ ...barn, h: 0.8, windows: ['n', 'w', 'e'] })
    c.roof('gable', barn, y)
    c.door(barn, 's', 0.9)
    c.sign(barn, 's')
    const sh = c.capacity * 0.9 + 0.9
    c.cyl(c.paint.base, { x: 1.15, y: sh / 2, z: -0.5 }, { x: 0.7, y: sh, z: 0.7 })
    c.m('dome', c.paint.roof, { x: 1.15, y: sh, z: -0.5 }, { x: 0.76, y: 0.5, z: 0.76 })
    c.fence(-1.4, 0.55, 1.4, 0.55, 0)
    c.fence(-1.4, 0.55, -1.4, 1.25)
    c.fence(1.4, 0.55, 1.4, 1.25)
    c.fence(-1.4, 1.25, 1.4, 1.25)
    c.animal(-0.6, 0.95, 0.6, 0.26, c.paint.glass, 0.3)
    c.animal(0.6, 0.9, 0.6, 0.26, c.paint.glass, -2.6)
    for (const x of [-1.2, -0.95]) c.cyl(c.paint.metal, { x, y: 0.18, z: 0.35 }, { x: 0.18, y: 0.36, z: 0.18 })
  },

  /** A long barn with stall doors, a paddock, horses, hay. */
  stable(c) {
    c.foundation('slab', { w: 3.2, d: 2.4 })
    const barn = { x: 0, z: -0.55, w: 3.2, d: 1.2 }
    const y = c.stack({ ...barn, h: 0.76, windows: ['n'] })
    c.roof('gable', barn, y)
    for (const x of [-1.0, 0, 1.0]) c.box(c.paint.dark, { x, y: 0.32, z: 0.08 }, { x: 0.6, y: 0.64, z: 0.06 })
    c.sign(barn, 's', 0.62)
    c.fence(-1.5, 0.35, 1.5, 0.35, 0)
    c.fence(-1.5, 0.35, -1.5, 1.35)
    c.fence(1.5, 0.35, 1.5, 1.35)
    c.fence(-1.5, 1.35, 1.5, 1.35)
    c.animal(-0.6, 0.85, 0.7, 0.34, c.paint.wood, 0.5)
    c.animal(0.7, 0.95, 0.7, 0.34, c.paint.dark, -0.4)
    for (const [x, z] of [
      [1.3, 0.55],
      [1.3, 0.95],
    ]) c.cyl(c.paint.crop, { x, y: 0.16, z }, { x: 0.3, y: 0.4, z: 0.3 }, { z: Math.PI / 2 })
    c.box(c.paint.dark, { x: -1.2, y: 0.12, z: 0.6 }, { x: 0.5, y: 0.2, z: 0.28 })
    c.box(c.paint.glass, { x: -1.2, y: 0.2, z: 0.6 }, { x: 0.42, y: 0.04, z: 0.2 })
  },

  /** A wide clinic: taller centre, two wings, a cross, an ambulance canopy, a helipad. */
  hospital(c) {
    c.foundation('stepped', { w: 3.0, d: 2.0 })
    const y = c.stack({ w: 1.4, d: 2.0, windows: ['n', 'e', 'w'] })
    const wingTop = Math.max(1, c.capacity - 1)
    for (const x of [-1.1, 1.1]) {
      const yw = c.stack({ x, w: 0.8, d: 1.7, to: wingTop, windows: ['n', 's'] })
      c.roof('flat', { x, z: 0, w: 0.8, d: 1.7 }, yw)
      if (x > 0) {
        c.cyl(c.paint.base, { x, y: yw + 0.2, z: 0 }, { x: 0.7, y: 0.04, z: 0.7 })
        c.box(c.paint.accent, { x, y: yw + 0.23, z: 0 }, { x: 0.3, y: 0.02, z: 0.05 })
        c.box(c.paint.accent, { x: x - 0.12, y: yw + 0.23, z: 0 }, { x: 0.05, y: 0.02, z: 0.3 })
        c.box(c.paint.accent, { x: x + 0.12, y: yw + 0.23, z: 0 }, { x: 0.05, y: 0.02, z: 0.3 })
      }
    }
    c.roof('flat', { x: 0, z: 0, w: 1.4, d: 2.0 }, y)
    c.box(c.paint.accent, { y: y + 0.55 }, { x: 0.7, y: 0.22, z: 0.16 })
    c.box(c.paint.accent, { y: y + 0.55 }, { x: 0.22, y: 0.7, z: 0.16 })
    c.door({ x: 0, z: 0, w: 1.4, d: 2.0 }, 's', 0.8)
    c.sign({ x: 0, z: 0, w: 1.4, d: 2.0 }, 's')
    for (const x of [-0.7, 0.7]) c.cyl(c.paint.metal, { x, y: 0.5, z: 1.7 }, { x: 0.06, y: 1.0, z: 0.06 })
    c.box(c.paint.glass, { y: 1.03, z: 1.4 }, { x: 1.7, y: 0.06, z: 0.8 })
  },

  /** Steps, a colonnade, a pediment, and the scales on top of it. */
  courthouse(c) {
    c.foundation('stepped', { w: 2.8, d: 2.0 })
    const block = { x: 0, z: -0.25, w: 2.6, d: 1.5 }
    const y = c.stack({ ...block, windows: ['n', 'e', 'w'] })
    c.roof('dome', block, y)
    const ch = y + 0.05
    c.columns([-1.05, -0.63, -0.21, 0.21, 0.63, 1.05], 0.95, ch)
    c.box(c.paint.base, { y: ch + 0.08, z: 0.95 }, { x: 2.7, y: 0.16, z: 0.5 })
    c.m('prism', c.paint.roof, { y: ch + 0.44, z: 0.95 }, { x: 2.8, y: 0.56, z: 0.6 }, { y: Math.PI / 2 })
    c.cyl(c.paint.dark, { y: ch + 1.0, z: 0.95 }, { x: 0.07, y: 0.5, z: 0.07 })
    c.box(c.paint.dark, { y: ch + 1.22, z: 0.95 }, { x: 0.8, y: 0.05, z: 0.05 })
    for (const s of [-1, 1]) c.box(c.paint.accent, { x: s * 0.36, y: ch + 1.08, z: 0.95 }, { x: 0.22, y: 0.05, z: 0.22 })
    c.door(block, 's', 0.7)
    c.sign(block, 's')
    c.steps(0, 1.25, 2.4)
  },

  /** The grandest civic front: a central tower, long wings, a colonnade, flags. */
  ministry(c) {
    c.foundation('stepped', { w: 3.4, d: 2.0 })
    const y = c.stack({ w: 1.4, d: 2.0, h: 0.9, windows: ['n'] })
    const wingTop = Math.max(1, c.capacity - 1)
    for (const x of [-1.2, 1.2]) {
      const yw = c.stack({ x, w: 1.0, d: 1.6, to: wingTop, h: 0.9, windows: ['n', 's'] })
      c.roof('hip', { x, z: 0, w: 1.0, d: 1.6 }, yw)
      c.flagpole(x, -0.5, yw + 0.9)
    }
    c.roof('tower', { x: 0, z: 0, w: 1.4, d: 2.0 }, y)
    c.columns([-0.5, -0.17, 0.17, 0.5], 1.15, y)
    c.box(c.paint.trim, { y: y + 0.04, z: 1.15 }, { x: 1.5, y: 0.1, z: 0.4 })
    c.door({ x: 0, z: 0, w: 1.4, d: 2.0 }, 's', 0.8)
    c.sign({ x: 0, z: 0, w: 1.4, d: 2.0 }, 's')
    c.steps(0, 1.4, 1.8, 3)
  },

  /** A hillside: tunnel mouth, headframe with a wheel, rails, a cart, ore piles, an office shack. */
  mine(c) {
    c.foundation('mound', { w: 2.6, d: 2.4 })
    c.box(c.paint.dark, { y: 0.4, z: -0.75 }, { x: 0.9, y: 0.8, z: 0.7 })
    for (const x of [-0.5, 0.5]) c.box(c.paint.wood, { x, y: 0.45, z: -0.4 }, { x: 0.14, y: 0.9, z: 0.14 })
    c.box(c.paint.wood, { y: 0.95, z: -0.4 }, { x: 1.2, y: 0.14, z: 0.18 })
    for (const dx of [-0.16, 0.16]) c.box(c.paint.metal, { x: dx, y: 0.02, z: 0.5 }, { x: 0.04, y: 0.03, z: 2.2 })
    for (let i = 0; i < 7; i += 1) c.box(c.paint.wood, { y: 0.01, z: -0.5 + i * 0.32 }, { x: 0.5, y: 0.02, z: 0.08 })
    c.box(c.paint.metal, { y: 0.2, z: 0.9 }, { x: 0.44, y: 0.28, z: 0.5 })
    for (const dz of [-0.16, 0.16]) c.cyl(c.paint.dark, { x: 0, y: 0.07, z: 0.9 + dz }, { x: 0.14, y: 0.5, z: 0.14 }, { z: Math.PI / 2 })
    c.m('cone', c.paint.accent, { y: 0.44, z: 0.9 }, { x: 0.36, y: 0.24, z: 0.4 })
    const hx = -1.0
    const hz = 0.35
    for (const [dx, dz] of [
      [-0.3, -0.3],
      [0.3, -0.3],
      [-0.3, 0.3],
      [0.3, 0.3],
    ]) c.cyl(c.paint.wood, { x: hx + dx * 0.7, y: 0.8, z: hz + dz * 0.7 }, { x: 0.08, y: 1.6, z: 0.08 }, { x: -dz * 0.3, z: dx * 0.3 })
    c.box(c.paint.wood, { x: hx, y: 1.6, z: hz }, { x: 0.6, y: 0.08, z: 0.6 })
    c.cyl(c.paint.metal, { x: hx, y: 1.85, z: hz }, { x: 0.5, y: 0.06, z: 0.5 }, { x: Math.PI / 2 })
    c.m('cone', c.paint.dark, { x: 1.0, y: 0.2, z: 1.0 }, { x: 0.6, y: 0.4, z: 0.6 })
    c.m('cone', c.paint.accent, { x: 0.7, y: 0.14, z: 1.3 }, { x: 0.4, y: 0.28, z: 0.4 })
    const shack = { x: 1.0, z: 0.1, w: 0.9, d: 0.8 }
    const y = c.stack({ ...shack, h: 0.7, windows: ['e', 'n'] })
    c.roof('flat', shack, y)
    c.door(shack, 's', 0.42)
    c.sign(shack, 's', 0.6)
  },

  /** A warehouse on piers with a loading dock, barrels and crates, and a crane. */
  trade(c) {
    c.foundation('piers', { w: 2.8, d: 2.2 })
    const house = { x: 0, z: -0.3, w: 2.8, d: 1.7 }
    const y = c.stack({ ...house, h: 0.84, windows: ['n', 'e', 'w'] })
    c.roof('gable', house, y)
    c.door(house, 's', 0.9)
    c.sign(house, 's')
    c.box(c.paint.wood, { y: 0.14, z: 1.0 }, { x: 2.8, y: 0.16, z: 0.9 })
    c.crate(-1.0, 0.85, 0.36, 0.4)
    c.crate(-0.65, 0.9, 0.3, 0.37, 0.4)
    c.crate(-1.0, 0.85, 0.28, 0.72, 0.2)
    c.barrel(0.9, 0.95, 0.3, 0.42)
    c.barrel(1.25, 1.1, 0.26, 0.36)
    c.cyl(c.paint.wood, { x: 1.55, y: 1.0, z: 0.2 }, { x: 0.12, y: 2.0, z: 0.12 })
    c.box(c.paint.wood, { x: 1.1, y: 1.9, z: 0.55 }, { x: 1.2, y: 0.1, z: 0.1 }, { y: -0.6 })
    c.cyl(c.paint.dark, { x: 0.65, y: 1.45, z: 0.85 }, { x: 0.02, y: 0.8, z: 0.02 })
    c.crate(0.65, 0.85, 0.3, 0.9)
  },

  /** A factory: sawtooth roof, smokestacks, a great gear on the front, a conveyor in the yard. */
  industry(c) {
    c.foundation('slab', { w: 3.0, d: 2.0 })
    const hall = { x: 0, z: 0, w: 3.0, d: 2.0 }
    const y = c.stack({ ...hall, h: 0.9, windows: ['e', 'w', 'n'] })
    for (const x of [-1.0, 0, 1.0]) c.roof('gable', { x, z: 0, w: 0.75, d: 2.0 }, y)
    for (const x of [-0.8, 0.6]) {
      c.cyl(c.paint.dark, { x, y: y + 1.0, z: -0.6 }, { x: 0.3, y: 2.0, z: 0.3 })
      c.cyl(c.paint.trim, { x, y: y + 1.98, z: -0.6 }, { x: 0.38, y: 0.08, z: 0.38 })
      c.m('sphere', c.paint.ground, { x: x + 0.1, y: y + 2.3, z: -0.6 }, { x: 0.4, y: 0.32, z: 0.4 })
    }
    c.cyl(c.paint.metal, { x: -0.9, y: 0.75, z: 1.04 }, { x: 0.7, y: 0.06, z: 0.7 }, { x: Math.PI / 2 })
    for (let k = 0; k < 4; k += 1) {
      c.box(c.paint.metal, { x: -0.9, y: 0.75, z: 1.06 }, { x: 0.82, y: 0.1, z: 0.04 }, { z: (k * Math.PI) / 4 })
    }
    c.door(hall, 's', 0.8)
    c.sign(hall, 's')
    c.box(c.paint.metal, { x: 0.9, y: 0.4, z: 1.5 }, { x: 1.6, y: 0.08, z: 0.34 })
    for (const dx of [-0.6, 0.6]) c.box(c.paint.dark, { x: 0.9 + dx, y: 0.18, z: 1.5 }, { x: 0.08, y: 0.36, z: 0.3 })
    c.cyl(c.paint.metal, { x: 1.6, y: 0.9, z: 0 }, { x: 0.14, y: 1.8, z: 0.14 })
    c.cyl(c.paint.metal, { x: 1.6, y: 1.8, z: -0.4 }, { x: 0.14, y: 0.9, z: 0.14 }, { x: Math.PI / 2 })
  },

  /** An open shed with a saw bench, log piles, planks, and a small office. */
  sawmill(c) {
    c.foundation('piers', { w: 3.0, d: 2.2 })
    const shed = { x: -0.45, z: -0.2, w: 2.0, d: 1.7 }
    for (const dx of [-0.9, 0.9]) {
      for (const dz of [-0.75, 0.75]) c.box(c.paint.wood, { x: shed.x + dx, y: 0.55, z: shed.z + dz }, { x: 0.14, y: 1.1, z: 0.14 })
    }
    c.roof('gable', shed, 1.1)
    c.box(c.paint.wood, { x: shed.x, y: 0.36, z: shed.z }, { x: 1.4, y: 0.08, z: 0.6 })
    c.cyl(c.paint.metal, { x: shed.x, y: 0.62, z: shed.z }, { x: 0.6, y: 0.04, z: 0.6 }, { x: Math.PI / 2 })
    for (const [x, z, yy] of [
      [-0.5, 0.95, 0.12],
      [-0.5, 1.2, 0.12],
      [-0.5, 1.07, 0.34],
    ]) c.cyl(c.paint.wood, { x, y: yy, z }, { x: 0.24, y: 1.2, z: 0.24 }, { z: Math.PI / 2 })
    for (let i = 0; i < 4; i += 1) c.box(c.paint.crop, { x: 0.7, y: 0.03 + i * 0.05, z: 1.0 }, { x: 0.3, y: 0.04, z: 1.0 })
    const office = { x: 1.15, z: -0.35, w: 0.85, d: 0.85 }
    const y = c.stack({ ...office, h: 0.7, windows: ['e', 'n'] })
    c.roof('flat', office, y)
    c.door(office, 's', 0.42)
    c.sign(office, 's', 0.6)
  },

  /** A tailor's shop: a mannequin in the window, fabric rolls, the spool over the door. */
  tailor(c) {
    c.foundation('slab', { w: 2.0, d: 1.6 })
    const shop = { x: 0, z: 0, w: 2.0, d: 1.6 }
    const y = c.stack({ ...shop, h: 0.84, windows: ['n', 'e', 'w'] })
    c.roof('hip', shop, y)
    c.door(shop, 's', 0.5)
    c.sign(shop, 's')
    c.awning(shop, 's', 0.86, 1.4)
    c.cyl(c.paint.accent, { x: -0.55, y: 1.25, z: 0.85 }, { x: 0.34, y: 0.4, z: 0.34 }, { z: Math.PI / 2 })
    c.cyl(c.paint.dark, { x: -0.78, y: 1.25, z: 0.85 }, { x: 0.42, y: 0.05, z: 0.42 }, { z: Math.PI / 2 })
    c.cyl(c.paint.dark, { x: -0.32, y: 1.25, z: 0.85 }, { x: 0.42, y: 0.05, z: 0.42 }, { z: Math.PI / 2 })
    c.box(c.paint.glass, { x: -0.55, y: 0.45, z: 0.82 }, { x: 0.6, y: 0.5, z: 0.04 })
    c.cyl(c.paint.metal, { x: -0.55, y: 0.2, z: 1.0 }, { x: 0.05, y: 0.4, z: 0.05 })
    c.cyl(c.paint.wall, { x: -0.55, y: 0.6, z: 1.0 }, { x: 0.22, y: 0.4, z: 0.16 })
    c.m('sphere', c.paint.base, { x: -0.55, y: 0.9, z: 1.0 }, { x: 0.16, y: 0.16, z: 0.16 })
    c.box(c.paint.wood, { x: 0.8, y: 0.3, z: 1.05 }, { x: 0.7, y: 0.05, z: 0.5 })
    for (const [dx, m] of [
      [-0.2, c.paint.accent],
      [0, c.paint.glass],
      [0.2, c.paint.roof],
    ] as const) c.cyl(m, { x: 0.8 + dx, y: 0.42, z: 1.05 }, { x: 0.16, y: 0.5, z: 0.16 }, { x: Math.PI / 2 })
  },

  /** A forge: the furnace and its chimney glowing beside a stone workshop, an anvil out front. */
  smithy(c) {
    c.foundation('slab', { w: 2.6, d: 2.0 })
    const shop = { x: -0.35, z: 0, w: 1.8, d: 1.8 }
    const y = c.stack({ ...shop, h: 0.84, windows: ['n', 'w'] })
    c.roof('gable', shop, y)
    c.door(shop, 's', 0.9)
    c.sign(shop, 's')
    const fh = c.capacity * 1.0 + 1.1
    c.box(c.paint.base, { x: 0.95, y: fh / 2, z: -0.45 }, { x: 0.8, y: fh, z: 0.8 })
    c.box(c.paint.glass, { x: 0.95, y: 0.4, z: -0.02 }, { x: 0.44, y: 0.44, z: 0.06 })
    c.box(c.paint.dark, { x: 0.95, y: fh + 0.06, z: -0.45 }, { x: 0.94, y: 0.12, z: 0.94 })
    c.box(c.paint.wood, { x: 0.9, y: 0.16, z: 0.75 }, { x: 0.36, y: 0.32, z: 0.36 })
    c.box(c.paint.metal, { x: 0.9, y: 0.4, z: 0.75 }, { x: 0.7, y: 0.16, z: 0.28 })
    c.m('cone', c.paint.metal, { x: 1.35, y: 0.4, z: 0.75 }, { x: 0.22, y: 0.3, z: 0.22 }, { z: -Math.PI / 2 })
    c.barrel(-1.35, 0.9, 0.26, 0.4)
    c.cyl(c.paint.wood, { x: 0.45, y: 0.12, z: 1.05 }, { x: 0.05, y: 0.5, z: 0.05 }, { z: 1.1 })
    c.box(c.paint.metal, { x: 0.65, y: 0.2, z: 1.05 }, { x: 0.16, y: 0.12, z: 0.14 })
  },

  /** A columned front with steps, and a great open book on the roof. */
  library(c) {
    c.foundation('stepped', { w: 2.8, d: 2.0 })
    const block = { x: 0, z: -0.2, w: 2.6, d: 1.6 }
    const y = c.stack({ ...block, h: 0.9, windows: ['n', 'e', 'w'] })
    c.roof('hip', block, y)
    c.columns([-0.85, -0.3, 0.3, 0.85], 0.9, y)
    c.box(c.paint.trim, { y: y + 0.04, z: 0.9 }, { x: 2.3, y: 0.1, z: 0.4 })
    c.box(c.paint.accent, { x: -0.3, y: y + 0.55, z: -0.2 }, { x: 0.7, y: 0.08, z: 0.9 }, { z: 0.35 })
    c.box(c.paint.accent, { x: 0.3, y: y + 0.55, z: -0.2 }, { x: 0.7, y: 0.08, z: 0.9 }, { z: -0.35 })
    c.box(c.paint.glass, { x: -0.3, y: y + 0.6, z: -0.2 }, { x: 0.6, y: 0.02, z: 0.8 }, { z: 0.35 })
    c.box(c.paint.glass, { x: 0.3, y: y + 0.6, z: -0.2 }, { x: 0.6, y: 0.02, z: 0.8 }, { z: -0.35 })
    c.door(block, 's', 0.7)
    c.sign(block, 's')
    c.steps(0, 1.25, 2.2)
    c.lantern(-1.25, 1.3)
    c.lantern(1.25, 1.3)
  },

  /** عوارضی: a road through the plot, a booth, a striped barrier arm, a gantry with a sign. */
  toll(c) {
    c.foundation('slab', { w: 3.0, d: 3.0 })
    c.box(c.paint.dark, { y: 0.02 }, { x: 1.3, y: 0.04, z: 3.8 })
    for (let i = 0; i < 6; i += 1) c.box(c.paint.glass, { y: 0.045, z: -1.6 + i * 0.6 }, { x: 0.06, y: 0.01, z: 0.3 })
    c.box(c.paint.glass, { y: 0.045, z: 0.55 }, { x: 1.2, y: 0.01, z: 0.08 })
    const booth = { x: 1.15, z: 0, w: 0.9, d: 0.9 }
    const y = c.stack({ ...booth, h: 0.9, windows: ['w', 'n', 's'] })
    c.roof('hip', booth, y)
    c.door(booth, 'e', 0.45)
    c.sign(booth, 's', 0.7)
    c.box(c.paint.metal, { x: 0.68, y: 0.45, z: 0.35 }, { x: 0.16, y: 0.9, z: 0.16 })
    for (let i = 0; i < 5; i += 1) {
      c.box(i % 2 ? c.paint.glass : c.paint.accent, { x: 0.5 - i * 0.27, y: 0.82, z: 0.35 }, { x: 0.27, y: 0.08, z: 0.08 })
    }
    for (const x of [-0.85, 0.85]) c.cyl(c.paint.metal, { x, y: 0.9, z: -0.7 }, { x: 0.1, y: 1.8, z: 0.1 })
    c.box(c.paint.metal, { y: 1.82, z: -0.7 }, { x: 1.9, y: 0.1, z: 0.14 })
    c.box(c.paint.accent, { y: 1.55, z: -0.7 }, { x: 1.1, y: 0.4, z: 0.06 })
    c.box(c.paint.glass, { y: 1.55, z: -0.66 }, { x: 0.9, y: 0.22, z: 0.02 })
    c.lantern(-0.85, 0.35, 0.7)
    c.lantern(-1.25, 1.1, 0.7)
  },

  /**
   * مرکز شهر: the city hall at the heart of the map.
   *
   * A square stone building read straight off the brief — one storey on the
   * ground, then a colonnade of eight columns, another storey, another
   * colonnade, and a third storey under a flat roof. The three storeys are the
   * three seats. The eight columns are the eight neighbourhoods: each stands at
   * the bearing its neighbourhood has on the map (sector k is centred on
   * 22.5° + 45°·k, which puts two on every side, each pair facing the pair
   * across the floor) and wears that neighbourhood's colour, so the building is
   * a compass of the city. Walls, cornices and capitals are fixed ivory stone
   * rather than the sector-0 theme it technically sits in, because the centre
   * belongs to everyone.
   */
  center(c) {
    const ivory = solid(0xfbf6ec)
    const stone = solid(0xe3d8c4)
    const dark = solid(0x3b332c)
    const pane = glassMaterial(0xffe6ad)

    const S = 3.4 // ground plan
    const U = 3.0 // upper storeys
    const GH = 1.3 // ground storey height
    const UH = 0.95 // upper storey height
    const SHAFT = 0.96

    c.emptyWall = ivory
    c.dressing = false
    c.foundation('stepped', { w: S, d: S })

    // Every face of a square, as (unit normal, yaw that turns a +z piece onto it).
    interface FaceInfo {
      nx: number
      nz: number
      rotY: number
    }
    const FACES: FaceInfo[] = [
      { nx: 0, nz: 1, rotY: 0 },
      { nx: 0, nz: -1, rotY: Math.PI },
      { nx: 1, nz: 0, rotY: Math.PI / 2 },
      { nx: -1, nz: 0, rotY: -Math.PI / 2 },
    ]
    /** A point on a face: `along` runs across the face, `out` is proud of the wall. */
    const onFace = (f: FaceInfo, half: number, along: number, y: number, out: number): Placement => ({
      x: f.nx * (half + out) + (f.nz !== 0 ? along * f.nz : 0),
      y,
      z: f.nz * (half + out) + (f.nx !== 0 ? -along * f.nx : 0),
      rotY: f.rotY,
    })
    const shift = (list: Placement[], out: number, dy: number): Placement[] =>
      list.map((p) => ({
        x: p.x + Math.sin(p.rotY) * out,
        y: p.y + dy,
        z: p.z + Math.cos(p.rotY) * out,
        rotY: p.rotY,
      }))

    /**
     * A pointed-arch window kit, instanced: a proud stone frame, a dark recess
     * and a lit pane, each a box with a four-sided cone squashed flat on top —
     * viewed square-on that cone is a triangle, which is the arch.
     */
    const archWindows = (anchors: Placement[], w: number, h: number) => {
      const layers: Array<[Material, number, number, number, number]> = [
        [stone, 0.03, w + 0.16, h + 0.06, 0.06],
        [dark, 0.07, w, h, 0.05],
        [pane, 0.09, w - 0.12, h - 0.1, 0.03],
      ]
      for (const [material, out, lw, lh, depth] of layers) {
        const tip = lw * 0.55
        c.instances('box', material, { x: lw, y: lh, z: depth }, shift(anchors, out, 0))
        c.instances('pyramid', material, { x: lw, y: tip, z: depth }, shift(anchors, out, lh / 2 + tip / 2))
      }
    }

    /** Two-step cornice capping a storey of side `side` whose top is `y`. */
    const cornice = (side: number, y: number): number => {
      c.box(stone, { y: y + 0.07 }, { x: side + 0.24, y: 0.14, z: side + 0.24 })
      c.box(stone, { y: y + 0.18 }, { x: side + 0.42, y: 0.08, z: side + 0.42 })
      return y + 0.22
    }

    /** Corner piers and, on the upper storeys, pilasters between the window bays. */
    const piers = (side: number, y0: number, h: number, width: number, pilasters: boolean) => {
      const at = side / 2 - width / 2 + 0.03
      const corners: Placement[] = []
      for (const sx of [-1, 1]) {
        for (const sz of [-1, 1]) corners.push({ x: sx * at, y: y0 + h / 2, z: sz * at, rotY: 0 })
      }
      c.instances('box', stone, { x: width, y: h, z: width }, corners)
      if (!pilasters) return
      const list: Placement[] = []
      for (const f of FACES) {
        for (const along of [-0.45, 0.45]) list.push(onFace(f, side / 2, along, y0 + h / 2, 0.03))
      }
      c.instances('box', stone, { x: 0.12, y: h, z: 0.06 }, list)
    }

    /**
     * An open colonnade over a slab at `y`: eight columns, one per neighbourhood.
     * Plinths, rings and capitals are one instanced draw each; only the shafts
     * are individual meshes, because each wears its own neighbourhood's paint.
     */
    const colonnade = (y: number): number => {
      c.box(stone, { y: y + 0.07 }, { x: U + 0.36, y: 0.14, z: U + 0.36 })
      c.box(stone, { y: y + 0.17 }, { x: U + 0.2, y: 0.06, z: U + 0.2 })
      const base = y + 0.2
      const half = U / 2 - 0.1
      const feet: Placement[] = []
      for (let k = 0; k < SECTOR_COUNT; k += 1) {
        // Sector k's bisector in map terms (theta counter-clockwise, y down),
        // mapped onto the model's ground plane: x east, -z north.
        const a = ((k * 45 + 22.5) * Math.PI) / 180
        const dx = Math.cos(a)
        const dz = -Math.sin(a)
        const m = Math.max(Math.abs(dx), Math.abs(dz))
        const x = (dx / m) * half
        const z = (dz / m) * half
        feet.push({ x, y: base, z, rotY: 0 })
        const shaft = c.cyl(stone, { x, y: base + 0.14 + SHAFT / 2, z }, { x: 0.22, y: SHAFT, z: 0.22 })
        c.sectorMesh(k, shaft)
      }
      const lift = (dy: number) => feet.map((p) => ({ ...p, y: p.y + dy }))
      c.instances('box', stone, { x: 0.34, y: 0.1, z: 0.34 }, lift(0.05))
      c.instances('cylinder', stone, { x: 0.28, y: 0.05, z: 0.28 }, lift(0.12))
      c.instances('cylinder', stone, { x: 0.28, y: 0.05, z: 0.28 }, lift(0.14 + SHAFT + 0.02))
      c.instances('box', stone, { x: 0.36, y: 0.12, z: 0.36 }, lift(0.14 + SHAFT + 0.11))
      const top = base + 0.14 + SHAFT + 0.17
      c.box(stone, { y: top + 0.08 }, { x: U + 0.36, y: 0.16, z: U + 0.36 })
      return top + 0.16
    }

    /** An upper storey: the seat itself, its bays of windows, its piers, its cornice. */
    const upper = (floor: number, y0: number): number => {
      const y1 = c.storey({ floor, w: U, d: U, y0, h: UH, trim: false, material: ivory })
      piers(U, y0, UH, 0.26, true)
      const list: Placement[] = []
      for (const f of FACES) {
        for (const along of [-0.9, 0, 0.9]) list.push(onFace(f, U / 2, along, y0 + 0.44, 0))
      }
      archWindows(list, 0.3, 0.46)
      return cornice(U, y1)
    }

    // ---- ground storey: the portal, tall windows, heavy corners ----
    let y = c.storey({ floor: 1, w: S, d: S, y0: 0, h: GH, trim: false, material: ivory })
    c.box(stone, { y: 0.08 }, { x: S + 0.16, y: 0.16, z: S + 0.16 })
    piers(S, 0, GH + 0.04, 0.4, false)
    {
      const list: Placement[] = []
      for (const f of FACES) {
        const bays = f.rotY === 0 ? [-1.1, 1.1] : [-1.1, 0, 1.1]
        for (const along of bays) list.push(onFace(f, S / 2, along, 0.64, 0))
      }
      archWindows(list, 0.36, 0.56)
    }
    // The portal: a proud stone frame around a dark pointed arch, on the south face.
    const front = S / 2
    c.box(stone, { y: 0.45, z: front + 0.07 }, { x: 1.0, y: 0.9, z: 0.14 })
    c.m('pyramid', stone, { y: 0.9 + 0.19, z: front + 0.07 }, { x: 1.0, y: 0.38, z: 0.14 })
    c.box(dark, { y: 0.42, z: front + 0.15 }, { x: 0.72, y: 0.84, z: 0.06 })
    c.m('pyramid', dark, { y: 0.84 + 0.14, z: front + 0.15 }, { x: 0.72, y: 0.28, z: 0.06 })
    c.box(pane, { y: 0.7, z: front + 0.19 }, { x: 0.44, y: 0.04, z: 0.02 })
    y = cornice(S, y)

    // ---- colonnade, storey, colonnade, storey ----
    y = colonnade(y)
    y = upper(2, y)
    y = colonnade(y)
    y = upper(3, y)

    // ---- the flat roof: a slab and a low parapet ----
    c.box(stone, { y: y + 0.04 }, { x: U + 0.1, y: 0.08, z: U + 0.1 })
    for (const f of FACES) {
      const p = onFace(f, U / 2 + 0.16, 0, y + 0.13, 0)
      const long = f.nz !== 0
      c.box(stone, { x: p.x, y: p.y, z: p.z }, { x: long ? U + 0.42 : 0.1, y: 0.1, z: long ? 0.1 : U + 0.42 })
    }

    // ---- the approach: steps to the portal, lanterns beside them ----
    c.steps(0, front + 0.24, 1.6, 3)
    for (const s of [-1, 1]) c.lantern(s * 1.2, front + 0.55, 0.8)
  },

  /** The team's home: a pavilion whose base and banner wear the team colour. */
  spawn(c) {
    c.foundation('round', { w: 2.0, d: 2.0 })
    c.storey({ floor: 1, w: 1.9, d: 1.9, y0: 0, h: 0.45, round: true })
    for (const [dx, dz] of [
      [-0.7, -0.7],
      [0.7, -0.7],
      [-0.7, 0.7],
      [0.7, 0.7],
    ]) c.cyl(c.paint.wood, { x: dx, y: 1.15, z: dz }, { x: 0.1, y: 1.2, z: 0.1 })
    c.m('pyramid', c.paint.roof, { y: 2.05 }, { x: 2.3 * Math.SQRT2, y: 0.6, z: 2.3 * Math.SQRT2 }, { y: Math.PI / 4 })
    c.cyl(c.paint.metal, { y: 2.9 }, { x: 0.06, y: 1.2, z: 0.06 })
    const flag = c.box(c.paint.wall, { x: 0.28, y: 3.3 }, { x: 0.56, y: 0.34, z: 0.03 })
    c.floors[0]?.bodies.push(flag)
    c.box(c.paint.accent, { y: 1.45, z: 0.95 }, { x: 1.4, y: 0.4, z: 0.05 })
    c.parts.push(...buildEmblem(c.theme.emblem, c.paint, { x: 0, y: 1.45, z: 0.99 }, 0))
    c.steps(0, 1.0, 1.2, 2)
    for (const s of [-1, 1]) c.lantern(s * 1.2, 1.2, 0.8)
  },
}

export function buildArchetype(archetype: Archetype, capacity: number, paint: Paint, theme: Theme): Built {
  const c = new Ctx(capacity, paint, theme)
  const builder = BUILDERS[archetype.key] ?? BUILDERS.grocery
  builder(c)
  return c.finish()
}

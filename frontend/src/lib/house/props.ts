/**
 * The shared vocabulary the per-type builders in `buildings.ts` speak:
 * foundations sized to a footprint, roofs that know where their own surface
 * is, the neighbourhood emblem for a sign, and the neighbourhood motif that
 * dresses the plot.
 *
 * All of it is built from the eight pooled geometries in `geometry.ts` by
 * scaling — see that file for why. The one rule this file adds is that a
 * roof-mounted piece asks the roof where its surface is (`RoofInfo.surfaceY`)
 * instead of guessing a height, which is what keeps a chimney sitting *on* a
 * slope rather than floating above the ridge.
 */
import { Mesh, Object3D, type Material } from 'three'

import type { FoundationKind, RoofKind } from './archetypes'
import { geometry, type GeometryKey } from './geometry'
import type { EmblemKind, MotifKind } from './themes'

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
  /** Grass and crops: fixed greens, because a pitch is green in every neighbourhood. */
  grass: Material
  crop: Material
  /** Bare timber. */
  wood: Material
  /** Iron and steel. */
  metal: Material
}

export interface Footprint {
  x: number
  z: number
  w: number
  d: number
}

// ---- foundations ------------------------------------------------------------

export interface FoundationInfo {
  parts: Object3D[]
  /** Lowest point of the model, where the contact shadow goes. */
  groundY: number
}

/** A plinth the size of the plot, plus the ground it stands on. */
export function buildFoundation(kind: FoundationKind, paint: Paint, plot: Footprint): FoundationInfo {
  const parts: Object3D[] = []
  const { x, z, w, d } = plot
  const plinth = (pad = 0.28, h = 0.16) =>
    mesh('box', paint.base, { x, y: -h / 2, z }, { x: w + pad, y: h, z: d + pad })

  switch (kind) {
    case 'stepped': {
      parts.push(mesh('box', paint.ground, { x, y: -0.42, z }, { x: w + 1.3, y: 0.16, z: d + 1.3 }))
      parts.push(mesh('box', paint.base, { x, y: -0.26, z }, { x: w + 0.9, y: 0.16, z: d + 0.9 }))
      parts.push(mesh('box', paint.base, { x, y: -0.1, z }, { x: w + 0.4, y: 0.2, z: d + 0.4 }))
      return { parts, groundY: -0.5 }
    }
    case 'round': {
      const r = Math.max(w, d)
      parts.push(mesh('cylinder', paint.ground, { x, y: -0.3, z }, { x: r + 1.2, y: 0.28, z: r + 1.2 }))
      parts.push(mesh('cylinder', paint.base, { x, y: -0.08, z }, { x: r + 0.6, y: 0.16, z: r + 0.6 }))
      return { parts, groundY: -0.44 }
    }
    case 'piers': {
      parts.push(mesh('box', paint.base, { x, y: -0.16, z }, { x: w + 0.5, y: 0.16, z: d + 0.5 }))
      for (const sx of [-1, 1]) {
        for (const sz of [-1, 1]) {
          parts.push(
            mesh('cylinder', paint.wood, { x: x + (sx * (w + 0.1)) / 2, y: -0.44, z: z + (sz * (d + 0.1)) / 2 }, {
              x: 0.22,
              y: 0.4,
              z: 0.22,
            }),
          )
        }
      }
      parts.push(mesh('box', paint.ground, { x, y: -0.7, z }, { x: w + 1.0, y: 0.12, z: d + 1.0 }))
      return { parts, groundY: -0.76 }
    }
    case 'walled': {
      parts.push(mesh('box', paint.ground, { x, y: -0.3, z }, { x: w + 1.4, y: 0.28, z: d + 1.4 }))
      parts.push(plinth())
      const rx = (w + 1.4) / 2
      const rz = (d + 1.4) / 2
      // Three full walls and a front wall with a gap for the path to the door.
      parts.push(mesh('box', paint.base, { x, y: 0.02, z: z - rz }, { x: w + 1.4, y: 0.34, z: 0.12 }))
      parts.push(mesh('box', paint.base, { x: x - rx, y: 0.02, z }, { x: 0.12, y: 0.34, z: d + 1.4 }))
      parts.push(mesh('box', paint.base, { x: x + rx, y: 0.02, z }, { x: 0.12, y: 0.34, z: d + 1.4 }))
      const seg = (w + 1.4) / 2 - 0.45
      parts.push(mesh('box', paint.base, { x: x - rx + seg / 2, y: 0.02, z: z + rz }, { x: seg, y: 0.34, z: 0.12 }))
      parts.push(mesh('box', paint.base, { x: x + rx - seg / 2, y: 0.02, z: z + rz }, { x: seg, y: 0.34, z: 0.12 }))
      return { parts, groundY: -0.44 }
    }
    case 'mound': {
      const r = Math.max(w, d)
      parts.push(mesh('dome', paint.ground, { x, y: -0.46, z }, { x: r + 2.0, y: 0.7, z: r + 2.0 }))
      parts.push(mesh('cylinder', paint.base, { x, y: -0.08, z }, { x: r + 0.5, y: 0.22, z: r + 0.5 }))
      return { parts, groundY: -0.46 }
    }
    case 'slab':
    default: {
      parts.push(mesh('box', paint.ground, { x, y: -0.3, z }, { x: w + 1.0, y: 0.28, z: d + 1.0 }))
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

/** A roof over a given footprint, with a little overhang. */
export function roofOn(kind: RoofKind, plot: Footprint, base: number, paint: Paint): RoofInfo {
  const parts: Object3D[] = []
  const { x, z, w, d } = plot
  const ow = w + 0.3
  const od = d + 0.3

  switch (kind) {
    case 'gable': {
      const height = Math.min(0.9, 0.34 * ow + 0.1)
      parts.push(mesh('prism', paint.roof, { x, y: base + height / 2, z }, { x: ow, y: height, z: od }))
      return {
        parts,
        top: base + height,
        surfaceY: (px) => base + height * (1 - Math.min(1, Math.abs(px - x) / (ow / 2))),
      }
    }
    case 'hip': {
      const height = Math.min(0.9, 0.36 * Math.min(ow, od) + 0.1)
      // A 4-segment cone is a diamond on the axes; rotating 45° squares it up,
      // at which point its half-side is radius / √2 — hence the √2 in the scale.
      parts.push(
        mesh(
          'pyramid',
          paint.roof,
          { x, y: base + height / 2, z },
          { x: ow * Math.SQRT2, y: height, z: od * Math.SQRT2 },
          { y: Math.PI / 4 },
        ),
      )
      return {
        parts,
        top: base + height,
        surfaceY: (px, pz) =>
          base +
          height *
            (1 - Math.min(1, Math.max(Math.abs(px - x) / (ow / 2), Math.abs(pz - z) / (od / 2)))),
      }
    }
    case 'dome': {
      const r = Math.min(ow, od) * 0.42
      const rise = r * 0.72
      parts.push(mesh('box', paint.base, { x, y: base + 0.09, z }, { x: w + 0.22, y: 0.18, z: d + 0.22 }))
      parts.push(mesh('cylinder', paint.base, { x, y: base + 0.32, z }, { x: r * 1.8, y: 0.3, z: r * 1.8 }))
      const centre = base + 0.46
      parts.push(mesh('dome', paint.roof, { x, y: centre, z }, { x: r * 2, y: rise * 2, z: r * 2 }))
      return {
        parts,
        top: centre + rise,
        surfaceY: (px, pz) => {
          const dist = Math.hypot(px - x, pz - z)
          if (dist > r) return base + 0.18
          return centre + rise * Math.sqrt(Math.max(0, 1 - (dist / r) ** 2))
        },
      }
    }
    case 'tiered': {
      parts.push(mesh('box', paint.base, { x, y: base + 0.08, z }, { x: w + 0.24, y: 0.16, z: d + 0.24 }))
      parts.push(mesh('box', paint.roof, { x, y: base + 0.4, z }, { x: w * 0.7, y: 0.48, z: d * 0.7 }))
      parts.push(mesh('box', paint.base, { x, y: base + 0.73, z }, { x: w * 0.42, y: 0.18, z: d * 0.42 }))
      return {
        parts,
        top: base + 0.82,
        surfaceY: (px, pz) => {
          const reach = Math.max(Math.abs(px - x) / (w / 2), Math.abs(pz - z) / (d / 2))
          if (reach < 0.42) return base + 0.82
          if (reach < 0.7) return base + 0.64
          return base + 0.16
        },
      }
    }
    case 'tower': {
      parts.push(mesh('box', paint.base, { x, y: base + 0.08, z }, { x: w + 0.24, y: 0.16, z: d + 0.24 }))
      const tw = Math.min(w, d) * 0.42
      parts.push(mesh('box', paint.wall, { x, y: base + 0.86, z }, { x: tw, y: 1.4, z: tw }))
      parts.push(mesh('box', paint.trim, { x, y: base + 1.6, z }, { x: tw + 0.12, y: 0.08, z: tw + 0.12 }))
      const cap = (tw + 0.1) * Math.SQRT2
      parts.push(mesh('pyramid', paint.roof, { x, y: base + 1.9, z }, { x: cap, y: 0.52, z: cap }, { y: Math.PI / 4 }))
      return {
        parts,
        top: base + 2.16,
        surfaceY: (px, pz) =>
          Math.max(Math.abs(px - x), Math.abs(pz - z)) < tw / 2 ? base + 2.16 : base + 0.16,
      }
    }
    case 'open': {
      // No roof: a rail around the top so the last storey reads as a deck.
      const rw = w + 0.16
      const rd = d + 0.16
      for (const side of [-1, 1]) {
        parts.push(mesh('box', paint.trim, { x, y: base + 0.1, z: z + (side * rd) / 2 }, { x: rw, y: 0.2, z: 0.08 }))
        parts.push(mesh('box', paint.trim, { x: x + (side * rw) / 2, y: base + 0.1, z }, { x: 0.08, y: 0.2, z: rd }))
      }
      return { parts, top: base + 0.2, surfaceY: () => base }
    }
    case 'flat':
    default: {
      const rw = w + 0.24
      const rd = d + 0.24
      parts.push(mesh('box', paint.base, { x, y: base + 0.08, z }, { x: rw, y: 0.16, z: rd }))
      for (const side of [-1, 1]) {
        parts.push(mesh('box', paint.roof, { x, y: base + 0.26, z: z + (side * rd) / 2 }, { x: rw, y: 0.2, z: 0.1 }))
        parts.push(mesh('box', paint.roof, { x: x + (side * rw) / 2, y: base + 0.26, z }, { x: 0.1, y: 0.2, z: rd }))
      }
      return { parts, top: base + 0.36, surfaceY: () => base + 0.16 }
    }
  }
}

// ---- theme dressing ---------------------------------------------------------------

/** The neighbourhood's symbol, mounted on a sign face at `at`, facing `rotY`. */
export function buildEmblem(
  kind: EmblemKind,
  paint: Paint,
  at: { x: number; y: number; z: number },
  rotY = 0,
): Object3D[] {
  const parts: Object3D[] = []
  // Work in the sign's own frame, then rotate every piece about the sign.
  const local = (dx: number, dy: number, dz: number) => ({
    x: at.x + dx * Math.cos(rotY) + dz * Math.sin(rotY),
    y: at.y + dy,
    z: at.z - dx * Math.sin(rotY) + dz * Math.cos(rotY),
  })
  const rot = (extra: { x?: number; z?: number } = {}) => ({ x: extra.x ?? 0, y: rotY, z: extra.z ?? 0 })

  switch (kind) {
    case 'drop':
      parts.push(mesh('sphere', paint.glass, local(0, -0.02, 0), { x: 0.16, y: 0.16, z: 0.12 }, rot()))
      parts.push(mesh('cone', paint.glass, local(0, 0.1, 0), { x: 0.14, y: 0.16, z: 0.1 }, rot()))
      break
    case 'flame':
      parts.push(mesh('cone', paint.accent, local(0, 0.02, 0), { x: 0.18, y: 0.28, z: 0.12 }, rot()))
      parts.push(mesh('cone', paint.glass, local(0, -0.02, 0.02), { x: 0.09, y: 0.16, z: 0.08 }, rot()))
      break
    case 'bolt':
      parts.push(mesh('box', paint.accent, local(0.04, 0.08, 0), { x: 0.07, y: 0.14, z: 0.04 }, rot({ z: 0.5 })))
      parts.push(mesh('box', paint.accent, local(-0.02, -0.02, 0), { x: 0.07, y: 0.14, z: 0.04 }, rot({ z: -0.6 })))
      parts.push(mesh('box', paint.accent, local(0.02, -0.12, 0), { x: 0.07, y: 0.12, z: 0.04 }, rot({ z: 0.5 })))
      break
    case 'lens':
      parts.push(mesh('cylinder', paint.dark, local(0, 0.02, 0), { x: 0.22, y: 0.04, z: 0.22 }, rot({ x: Math.PI / 2 })))
      parts.push(mesh('cylinder', paint.glass, local(0, 0.02, 0.02), { x: 0.15, y: 0.04, z: 0.15 }, rot({ x: Math.PI / 2 })))
      parts.push(mesh('box', paint.dark, local(0.12, -0.12, 0), { x: 0.05, y: 0.16, z: 0.04 }, rot({ z: 0.8 })))
      break
    case 'dumbbell':
      parts.push(mesh('cylinder', paint.dark, local(0, 0, 0), { x: 0.04, y: 0.26, z: 0.04 }, rot({ z: Math.PI / 2 })))
      for (const side of [-1, 1]) {
        parts.push(mesh('sphere', paint.accent, local(side * 0.13, 0, 0), { x: 0.1, y: 0.1, z: 0.1 }))
      }
      break
    case 'book':
      parts.push(mesh('box', paint.glass, local(-0.07, 0, 0), { x: 0.14, y: 0.18, z: 0.03 }, { x: 0, y: rotY + 0.5, z: 0 }))
      parts.push(mesh('box', paint.glass, local(0.07, 0, 0), { x: 0.14, y: 0.18, z: 0.03 }, { x: 0, y: rotY - 0.5, z: 0 }))
      break
    case 'tablet':
      parts.push(mesh('box', paint.dark, local(0, 0, 0), { x: 0.18, y: 0.22, z: 0.04 }, rot()))
      parts.push(mesh('box', paint.glass, local(0, 0.05, 0.02), { x: 0.12, y: 0.02, z: 0.02 }, rot()))
      parts.push(mesh('box', paint.glass, local(0, -0.02, 0.02), { x: 0.12, y: 0.02, z: 0.02 }, rot()))
      break
    case 'seed':
      parts.push(mesh('sphere', paint.dark, local(0, -0.04, 0), { x: 0.14, y: 0.12, z: 0.1 }))
      parts.push(mesh('cone', paint.accent, local(0.02, 0.1, 0), { x: 0.08, y: 0.16, z: 0.06 }, rot({ z: -0.4 })))
      break
    case 'none':
    default:
      break
  }
  return parts
}

/**
 * One signature piece per neighbourhood, dressing the plot around the house.
 * Placed at the plot's corners, so it never collides with the building.
 */
export function buildMotif(
  kind: MotifKind,
  plot: Footprint,
  groundY: number,
  paint: Paint,
  capacity: number,
): Object3D[] {
  const parts: Object3D[] = []
  const rx = plot.w / 2 + 0.55
  const rz = plot.d / 2 + 0.55
  const nw = { x: plot.x - rx, z: plot.z - rz }
  const ne = { x: plot.x + rx, z: plot.z - rz }
  const sw = { x: plot.x - rx, z: plot.z + rz }
  const se = { x: plot.x + rx, z: plot.z + rz }

  switch (kind) {
    case 'well': {
      // Sorgilesh's trade: a stone ring, two posts, a little roof, a bucket.
      const { x, z } = se
      parts.push(mesh('cylinder', paint.base, { x, y: 0.17, z }, { x: 0.62, y: 0.34, z: 0.62 }))
      parts.push(mesh('cylinder', paint.glass, { x, y: 0.31, z }, { x: 0.46, y: 0.06, z: 0.46 }))
      for (const side of [-1, 1]) {
        parts.push(mesh('box', paint.wood, { x: x + side * 0.28, y: 0.6, z }, { x: 0.06, y: 0.7, z: 0.06 }))
      }
      parts.push(mesh('prism', paint.roof, { x, y: 1.02, z }, { x: 0.82, y: 0.24, z: 0.6 }))
      parts.push(mesh('cylinder', paint.wood, { x, y: 0.88, z }, { x: 0.05, y: 0.6, z: 0.05 }, { z: Math.PI / 2 }))
      parts.push(mesh('cylinder', paint.metal, { x, y: 0.62, z: z + 0.16 }, { x: 0.14, y: 0.14, z: 0.14 }))
      break
    }
    case 'spikes': {
      // Ghargileh's angular temper: spiked finials at every corner, embers at their feet.
      for (const c of [nw, ne, sw, se]) {
        parts.push(mesh('cone', paint.dark, { x: c.x, y: 0.5, z: c.z }, { x: 0.18, y: 1.0, z: 0.18 }))
        parts.push(mesh('cone', paint.accent, { x: c.x, y: 0.2, z: c.z }, { x: 0.32, y: 0.4, z: 0.32 }))
        parts.push(mesh('cone', paint.glass, { x: c.x, y: 0.14, z: c.z }, { x: 0.16, y: 0.24, z: 0.16 }))
      }
      break
    }
    case 'compass': {
      // Fergoleh's compass rose on the ground and a bolt-topped signpost.
      const { x, z } = sw
      parts.push(mesh('cylinder', paint.base, { x, y: 0.02, z }, { x: 1.0, y: 0.04, z: 1.0 }))
      parts.push(mesh('box', paint.accent, { x, y: 0.05, z }, { x: 0.9, y: 0.02, z: 0.1 }))
      parts.push(mesh('box', paint.accent, { x, y: 0.05, z }, { x: 0.1, y: 0.02, z: 0.9 }))
      parts.push(mesh('box', paint.dark, { x, y: 0.06, z }, { x: 0.5, y: 0.02, z: 0.06 }, { y: Math.PI / 4 }))
      parts.push(mesh('box', paint.dark, { x, y: 0.06, z }, { x: 0.06, y: 0.02, z: 0.5 }, { y: Math.PI / 4 }))
      const px = ne.x
      const pz = ne.z
      parts.push(mesh('cylinder', paint.wood, { x: px, y: 0.6, z: pz }, { x: 0.08, y: 1.2, z: 0.08 }))
      parts.push(mesh('box', paint.accent, { x: px, y: 1.05, z: pz }, { x: 0.5, y: 0.16, z: 0.05 }, { y: -0.4 }))
      parts.push(mesh('box', paint.accent, { x: px + 0.04, y: 1.34, z: pz }, { x: 0.08, y: 0.22, z: 0.05 }, { z: 0.5 }))
      parts.push(mesh('box', paint.accent, { x: px - 0.03, y: 1.2, z: pz }, { x: 0.08, y: 0.2, z: 0.05 }, { z: -0.6 }))
      break
    }
    case 'ruins': {
      const { x, z } = sw
      parts.push(mesh('cylinder', paint.base, { x, y: 0.4, z }, { x: 0.22, y: 0.8, z: 0.22 }))
      parts.push(mesh('cylinder', paint.base, { x: x + 0.5, y: 0.22, z: z - 0.1 }, { x: 0.22, y: 0.44, z: 0.22 }))
      parts.push(
        mesh('cylinder', paint.base, { x: x + 0.3, y: 0.11, z: z + 0.5 }, { x: 0.2, y: 0.7, z: 0.2 }, { z: Math.PI / 2, y: 0.6 }),
      )
      parts.push(mesh('box', paint.base, { x: ne.x, y: 0.06, z: ne.z }, { x: 0.6, y: 0.12, z: 0.4 }, { y: 0.3 }))
      break
    }
    case 'sun': {
      // Hogila: sun-shaped and calm. A sun disc on a pole with rays, a bow beneath.
      const { x, z } = se
      parts.push(mesh('cylinder', paint.wood, { x, y: 0.7, z }, { x: 0.08, y: 1.4, z: 0.08 }))
      parts.push(mesh('cylinder', paint.accent, { x, y: 1.55, z }, { x: 0.5, y: 0.06, z: 0.5 }, { x: Math.PI / 2 }))
      for (let i = 0; i < 8; i += 1) {
        const a = (i * Math.PI) / 4
        parts.push(
          mesh('box', paint.accent, { x: x + Math.cos(a) * 0.36, y: 1.55 + Math.sin(a) * 0.36, z }, { x: 0.16, y: 0.06, z: 0.04 }, { z: a }),
        )
      }
      parts.push(mesh('cone', paint.glass, { x: x - 0.08, y: 1.16, z }, { x: 0.12, y: 0.14, z: 0.06 }, { z: Math.PI / 2 }))
      parts.push(mesh('cone', paint.glass, { x: x + 0.08, y: 1.16, z }, { x: 0.12, y: 0.14, z: 0.06 }, { z: -Math.PI / 2 }))
      break
    }
    case 'lectern': {
      // Geispli the scribe: a lectern with an open scroll and a quill.
      const { x, z } = se
      parts.push(mesh('box', paint.wood, { x, y: 0.4, z }, { x: 0.16, y: 0.8, z: 0.16 }))
      parts.push(mesh('box', paint.wood, { x, y: 0.84, z }, { x: 0.6, y: 0.06, z: 0.44 }, { x: -0.35 }))
      parts.push(mesh('cylinder', paint.glass, { x, y: 0.92, z: z + 0.06 }, { x: 0.12, y: 0.5, z: 0.12 }, { z: Math.PI / 2 }))
      parts.push(mesh('cone', paint.glass, { x: x + 0.22, y: 1.08, z: z - 0.05 }, { x: 0.05, y: 0.36, z: 0.05 }, { z: -0.5 }))
      break
    }
    case 'construction': {
      // A site: poles up every corner of the plot, a crane, and one royal flag
      // for Gilbib, the king whose city this will be.
      const height = capacity * FLOOR_H + 0.4
      for (const c of [nw, ne, sw, se]) {
        parts.push(mesh('cylinder', paint.scaffold, { x: c.x, y: height / 2, z: c.z }, { x: 0.07, y: height, z: 0.07 }))
      }
      parts.push(mesh('box', paint.scaffold, { x: plot.x, y: height, z: sw.z }, { x: rx * 2, y: 0.06, z: 0.08 }))
      const cx = ne.x + 0.2
      const cz = ne.z
      parts.push(mesh('cylinder', paint.accent, { x: cx, y: height / 2 + 0.4, z: cz }, { x: 0.12, y: height + 0.8, z: 0.12 }))
      parts.push(mesh('box', paint.accent, { x: cx - 0.9, y: height + 0.75, z: cz }, { x: 2.0, y: 0.1, z: 0.1 }))
      parts.push(mesh('cylinder', paint.dark, { x: cx - 1.6, y: height + 0.3, z: cz }, { x: 0.02, y: 0.9, z: 0.02 }))
      parts.push(mesh('box', paint.dark, { x: cx - 1.6, y: height - 0.2, z: cz }, { x: 0.24, y: 0.2, z: 0.24 }))
      parts.push(mesh('cylinder', paint.wood, { x: sw.x, y: height + 0.6, z: sw.z }, { x: 0.05, y: 0.5, z: 0.05 }))
      parts.push(mesh('box', paint.accent, { x: sw.x + 0.16, y: height + 0.76, z: sw.z }, { x: 0.32, y: 0.2, z: 0.03 }))
      break
    }
    case 'halo': {
      // Fingeil: torches, a totem, and his floating halo above it.
      for (const c of [sw, se]) {
        parts.push(mesh('cylinder', paint.dark, { x: c.x, y: 0.45, z: c.z }, { x: 0.08, y: 0.9, z: 0.08 }))
        parts.push(mesh('cone', paint.accent, { x: c.x, y: 1.02, z: c.z }, { x: 0.2, y: 0.28, z: 0.2 }))
      }
      const { x, z } = nw
      parts.push(mesh('box', paint.dark, { x, y: 0.35, z }, { x: 0.36, y: 0.7, z: 0.36 }))
      parts.push(mesh('box', paint.accent, { x, y: 0.85, z }, { x: 0.3, y: 0.3, z: 0.3 }, { y: 0.4 }))
      parts.push(mesh('box', paint.dark, { x, y: 1.15, z }, { x: 0.36, y: 0.3, z: 0.36 }))
      parts.push(mesh('cylinder', paint.glass, { x, y: 1.5, z }, { x: 0.5, y: 0.04, z: 0.5 }))
      parts.push(mesh('cylinder', paint.dark, { x, y: 1.5, z }, { x: 0.36, y: 0.05, z: 0.36 }))
      break
    }
    case 'roots': {
      // Golmari: roots, sprouts, and the elder farmer's cane and satchel by the gate.
      for (const angle of [0.4, 1.9, 3.4, 4.9]) {
        const x = plot.x + Math.cos(angle) * (rx + 0.2)
        const z = plot.z + Math.sin(angle) * (rz + 0.2)
        parts.push(mesh('cylinder', paint.dark, { x, y: groundY + 0.12, z }, { x: 0.16, y: 0.9, z: 0.16 }, { z: Math.PI / 2, y: -angle }))
      }
      parts.push(mesh('cone', paint.accent, { x: ne.x, y: 0.22, z: ne.z }, { x: 0.22, y: 0.44, z: 0.22 }))
      parts.push(mesh('cone', paint.accent, { x: ne.x + 0.14, y: 0.14, z: ne.z + 0.05 }, { x: 0.14, y: 0.28, z: 0.14 }, { z: -0.4 }))
      parts.push(mesh('cylinder', paint.wood, { x: se.x, y: 0.4, z: se.z }, { x: 0.05, y: 0.8, z: 0.05 }, { z: 0.12 }))
      parts.push(mesh('sphere', paint.wood, { x: se.x + 0.05, y: 0.82, z: se.z }, { x: 0.1, y: 0.1, z: 0.1 }))
      parts.push(mesh('box', paint.dark, { x: se.x - 0.3, y: 0.14, z: se.z }, { x: 0.3, y: 0.28, z: 0.16 }))
      break
    }
    case 'none':
    default:
      break
  }
  return parts
}

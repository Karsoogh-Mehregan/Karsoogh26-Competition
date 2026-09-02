/**
 * One material per colour, for the whole session.
 *
 * Forty-eight team colours plus a handful of neutrals is the entire universe of
 * paint this board can ask for, so the pool is bounded and nothing is ever
 * disposed. Sharing them also means two floors held by the same team merge into
 * one draw call.
 *
 * `flatShading` is the look: the reference art is hand-drawn and faceted, not
 * smooth-shaded, and it costs nothing.
 */
import { Color, DoubleSide, MeshBasicMaterial, MeshLambertMaterial, type Material } from 'three'

import { contactShadowTexture } from './geometry'

/** Unclaimed stone. Matches `HOUSE_FILL` in GraphView so map and model agree. */
export const NEUTRAL = 0xe2cfa6
export const NEUTRAL_DARK = 0xc9b48c
export const STONE = 0xd8bb99
export const GLASS = 0xffe6b0
export const SCAFFOLD = 0x8c7a63
export const GROUND = 0xefe6d8

const solids = new Map<number, MeshLambertMaterial>()

export function solid(color: number): MeshLambertMaterial {
  let material = solids.get(color)
  if (material === undefined) {
    material = new MeshLambertMaterial({ color, flatShading: true })
    solids.set(color, material)
  }
  return material
}

/** Windows: unlit so they read as glowing panes without a second light. */
let glassMaterial: MeshBasicMaterial | null = null
export function glass(): MeshBasicMaterial {
  glassMaterial ??= new MeshBasicMaterial({ color: GLASS })
  return glassMaterial
}

let shadowMaterial: MeshBasicMaterial | null = null
export function contactShadow(): MeshBasicMaterial {
  shadowMaterial ??= new MeshBasicMaterial({
    map: contactShadowTexture(),
    transparent: true,
    depthWrite: false,
    side: DoubleSide,
  })
  return shadowMaterial
}

const HEX = /^#?([0-9a-f]{6})$/i

/** A team's `#rrggbb`, or the unclaimed stone when the team has no colour yet. */
export function teamColor(hex: string | null | undefined): number {
  if (!hex) return NEUTRAL
  const match = HEX.exec(hex.trim())
  if (!match) return NEUTRAL
  return Number.parseInt(match[1], 16)
}

/** Slightly darker than its floor, for the trim band that caps each storey. */
const shades = new Map<number, number>()
export function shade(color: number, amount = 0.78): number {
  const key = color * 1000 + Math.round(amount * 100)
  let value = shades.get(key)
  if (value === undefined) {
    value = new Color(color).multiplyScalar(amount).getHex()
    shades.set(key, value)
  }
  return value
}

export type HouseMaterial = Material

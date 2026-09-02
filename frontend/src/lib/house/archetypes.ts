/**
 * The fourteen buildings of Gil Behesht, plus the two special plots.
 *
 * A house is a shared chassis wearing an archetype's hat: the floor stack,
 * windows and base are identical everywhere, and only the roof, the rooftop
 * prop and the accent colour change. That is what buys 473 visually distinct
 * buildings out of a geometry library of about a dozen shapes.
 *
 * The pick is a hash of the node code, so a node looks the same on every
 * client and across reloads without anything being stored for it.
 */
import type { Level } from '@/lib/mapLevels'

export type RoofKind = 'gable' | 'dome' | 'flat' | 'hip' | 'tiered'
export type PropKind =
  | 'none'
  | 'telescope'
  | 'vault'
  | 'scales'
  | 'cross'
  | 'cone'
  | 'books'
  | 'clock'
  | 'chimney'
  | 'antenna'
  | 'flag'
  | 'banner'
  | 'crate'

export interface Archetype {
  key: string
  label: string
  roof: RoofKind
  prop: PropKind
  /** Roof and trim colour, so an empty plot still reads as a specific building. */
  accent: number
  /** Drawn as an awning over the ground-floor door. */
  awning: boolean
}

export const ARCHETYPES: Archetype[] = [
  { key: 'bank', label: 'بانک', roof: 'dome', prop: 'vault', accent: 0xc98b3a, awning: false },
  { key: 'bakery', label: 'نانوایی', roof: 'gable', prop: 'chimney', accent: 0xd07a44, awning: true },
  { key: 'library', label: 'کتابخانه', roof: 'hip', prop: 'books', accent: 0x9a6b4f, awning: false },
  { key: 'observatory', label: 'رصدخانه', roof: 'dome', prop: 'telescope', accent: 0x6f7fa8, awning: false },
  { key: 'hospital', label: 'بیمارستان', roof: 'flat', prop: 'cross', accent: 0xb8524f, awning: false },
  { key: 'courthouse', label: 'دادگستری', roof: 'dome', prop: 'scales', accent: 0x8f8f9c, awning: false },
  { key: 'hotel', label: 'هتل', roof: 'tiered', prop: 'flag', accent: 0xb5604a, awning: true },
  { key: 'restaurant', label: 'رستوران', roof: 'gable', prop: 'chimney', accent: 0xc25f3e, awning: true },
  { key: 'icecream', label: 'بستنی‌فروشی', roof: 'gable', prop: 'cone', accent: 0xd98f74, awning: true },
  { key: 'newsstand', label: 'روزنامه‌فروشی', roof: 'flat', prop: 'banner', accent: 0x7c8a72, awning: true },
  { key: 'school', label: 'مدرسه', roof: 'gable', prop: 'clock', accent: 0xa87550, awning: false },
  { key: 'shop', label: 'مغازه', roof: 'flat', prop: 'crate', accent: 0xc07a52, awning: true },
  { key: 'workshop', label: 'کارگاه', roof: 'gable', prop: 'crate', accent: 0x8a6a52, awning: false },
  { key: 'taxoffice', label: 'خانهٔ مالیات', roof: 'hip', prop: 'clock', accent: 0xa9894f, awning: false },
]

const SPAWN: Archetype = {
  key: 'spawn',
  label: 'خانهٔ شروع',
  roof: 'tiered',
  prop: 'banner',
  accent: 0xd9b23a,
  awning: false,
}

const TOLL: Archetype = {
  key: 'toll',
  label: 'عوارضی',
  roof: 'flat',
  prop: 'antenna',
  accent: 0x8c8c8c,
  awning: false,
}

/** FNV-1a, so the same node code always lands on the same building. */
function hash(value: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < value.length; i += 1) {
    h ^= value.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

export function archetypeFor(nodeCode: string, level: Level): Archetype {
  if (level === 'spawn') return SPAWN
  if (level === 'toll') return TOLL
  return ARCHETYPES[hash(nodeCode) % ARCHETYPES.length]
}

/** A stable 0..1 per node, for the small placement jitters that break up a row. */
export function seedOf(nodeCode: string): number {
  return (hash(`${nodeCode}#seed`) % 10000) / 10000
}

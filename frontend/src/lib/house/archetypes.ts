/**
 * The twenty-six buildings of Gil Behesht, plus the three special plots.
 *
 * A building is a shared chassis wearing a type's hat: the storeys and windows
 * are identical everywhere, and the type decides the roof, the foundation it
 * stands on, and which props sit on and around it. The neighbourhood theme then
 * decides the paint. Keys mirror `backend/game/design.py::ARCHETYPES`, which is
 * what a Designer's pin is validated against.
 *
 * Which type an unpinned node wears is decided in `lib/mapArchetypes.ts`, so
 * that no two adjacent nodes share one. This file only says what each looks like.
 */
import type { Level } from '@/lib/mapLevels'

export type RoofKind = 'gable' | 'dome' | 'flat' | 'hip' | 'tiered' | 'tower' | 'open'

export type FoundationKind = 'slab' | 'stepped' | 'round' | 'piers' | 'walled' | 'mound'

export type PropKind =
  | 'coin'
  | 'cupola'
  | 'chimney'
  | 'bell'
  | 'cone'
  | 'press'
  | 'flag'
  | 'gate'
  | 'goalposts'
  | 'plots'
  | 'watchtower'
  | 'telescope'
  | 'crates'
  | 'silo'
  | 'trough'
  | 'cross'
  | 'scales'
  | 'columns'
  | 'orepile'
  | 'smokestack'
  | 'logs'
  | 'spool'
  | 'anvil'
  | 'books'
  | 'banner'
  | 'antenna'

export interface Archetype {
  key: string
  label: string
  roof: RoofKind
  foundation: FoundationKind
  props: PropKind[]
  /** Drawn as an awning over the ground-floor door. */
  awning: boolean
}

export const ARCHETYPES: Archetype[] = [
  { key: 'mint', label: 'ضراب‌خانه', roof: 'dome', foundation: 'stepped', props: ['coin'], awning: false },
  { key: 'cityhall', label: 'شهرداری', roof: 'hip', foundation: 'stepped', props: ['cupola', 'flag'], awning: false },
  { key: 'bakery', label: 'نانوایی', roof: 'gable', foundation: 'slab', props: ['chimney'], awning: true },
  { key: 'restaurant', label: 'رستوران', roof: 'gable', foundation: 'walled', props: ['chimney', 'crates'], awning: true },
  { key: 'school', label: 'مدرسه', roof: 'gable', foundation: 'slab', props: ['bell'], awning: false },
  { key: 'icecream', label: 'بستنی‌فروشی', roof: 'gable', foundation: 'round', props: ['cone'], awning: true },
  { key: 'newspaper', label: 'روزنامهٔ گیل‌بهشت', roof: 'flat', foundation: 'slab', props: ['press', 'banner'], awning: true },
  { key: 'hotel', label: 'مهمان‌سرا', roof: 'tiered', foundation: 'stepped', props: ['flag'], awning: true },
  { key: 'caravanserai', label: 'کاروانسرا', roof: 'flat', foundation: 'walled', props: ['gate'], awning: false },
  { key: 'stadium', label: 'زمین چولیگان', roof: 'open', foundation: 'round', props: ['goalposts'], awning: false },
  { key: 'farm', label: 'زمین کشاورزی', roof: 'open', foundation: 'walled', props: ['plots', 'silo'], awning: false },
  { key: 'guardpost', label: 'نگهبانی دیوار', roof: 'flat', foundation: 'walled', props: ['watchtower'], awning: false },
  { key: 'observatory', label: 'رصدخانه', roof: 'dome', foundation: 'round', props: ['telescope'], awning: false },
  { key: 'grocery', label: 'بقالی', roof: 'flat', foundation: 'slab', props: ['crates'], awning: true },
  { key: 'dairy', label: 'گاوداری', roof: 'gable', foundation: 'piers', props: ['silo', 'trough'], awning: false },
  { key: 'stable', label: 'اسب‌داری', roof: 'gable', foundation: 'walled', props: ['trough'], awning: false },
  { key: 'hospital', label: 'شفاخانه', roof: 'flat', foundation: 'stepped', props: ['cross'], awning: false },
  { key: 'courthouse', label: 'دادسرا', roof: 'dome', foundation: 'stepped', props: ['scales', 'columns'], awning: false },
  { key: 'ministry', label: 'وزارتخانه', roof: 'tower', foundation: 'stepped', props: ['columns', 'flag'], awning: false },
  { key: 'mine', label: 'معدن', roof: 'open', foundation: 'mound', props: ['orepile', 'gate'], awning: false },
  { key: 'trade', label: 'تجارت‌خانه', roof: 'hip', foundation: 'piers', props: ['crates', 'coin'], awning: true },
  { key: 'industry', label: 'کارخانه', roof: 'flat', foundation: 'slab', props: ['smokestack'], awning: false },
  { key: 'sawmill', label: 'کارگاه چوب‌بری', roof: 'gable', foundation: 'piers', props: ['logs'], awning: false },
  { key: 'tailor', label: 'کارگاه لباس‌دوزی', roof: 'hip', foundation: 'slab', props: ['spool'], awning: true },
  { key: 'smithy', label: 'کارگاه آهنگری', roof: 'gable', foundation: 'slab', props: ['anvil', 'chimney'], awning: false },
  { key: 'library', label: 'کتابخانه', roof: 'hip', foundation: 'stepped', props: ['books'], awning: false },
]

/** Keys the assignment may hand out; the three special plots are excluded. */
export const ASSIGNABLE_KEYS: readonly string[] = ARCHETYPES.map((archetype) => archetype.key)

export const ARCHETYPE_BY_KEY: ReadonlyMap<string, Archetype> = new Map(
  ARCHETYPES.map((archetype) => [archetype.key, archetype]),
)

export const SPAWN_ARCHETYPE: Archetype = {
  key: 'spawn',
  label: 'خانهٔ شروع',
  roof: 'tiered',
  foundation: 'stepped',
  props: ['banner'],
  awning: false,
}

export const TOLL_ARCHETYPE: Archetype = {
  key: 'toll',
  label: 'عوارضی',
  roof: 'flat',
  foundation: 'slab',
  props: ['antenna', 'gate'],
  awning: false,
}

/**
 * مرکز شهر — the one `CENTER` node. A city hall of three storeys over two open
 * colonnades, eight columns to each: one per neighbourhood, standing at that
 * neighbourhood's bearing on the map and wearing its colour. Fixed to the
 * level like spawn and toll, so a Designer's pin never replaces it.
 */
export const CENTER_ARCHETYPE: Archetype = {
  key: 'center',
  label: 'شهرداری گیل‌بهشت',
  roof: 'flat',
  foundation: 'stepped',
  props: ['columns'],
  awning: false,
}

/** FNV-1a, so the same node code always lands on the same building. */
export function hashCode(value: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < value.length; i += 1) {
    h ^= value.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

/** The type for a node with no pin and no neighbours to avoid — the plain hash. */
export function fallbackArchetypeFor(nodeCode: string, level: Level): Archetype {
  if (level === 'spawn') return SPAWN_ARCHETYPE
  if (level === 'toll') return TOLL_ARCHETYPE
  if (level === 'center') return CENTER_ARCHETYPE
  return ARCHETYPES[hashCode(nodeCode) % ARCHETYPES.length]
}

export function archetypeByKey(key: string, level: Level): Archetype {
  if (level === 'spawn') return SPAWN_ARCHETYPE
  if (level === 'toll') return TOLL_ARCHETYPE
  if (level === 'center') return CENTER_ARCHETYPE
  return ARCHETYPE_BY_KEY.get(key) ?? ARCHETYPES[0]
}

/** A stable 0..1 per node, for the small placement jitters that break up a row. */
export function seedOf(nodeCode: string): number {
  return (hashCode(`${nodeCode}#seed`) % 10000) / 10000
}

/**
 * The nine neighbourhood themes, each carrying the feel of the character who
 * wears its colour in the story (see `karsoogh-mehregan-characters.md`).
 *
 * A theme is applied *over* a building type: the type decides the massing,
 * the theme decides the paint, the symbol on the sign, and one signature motif
 * that dresses the plot. The motif is where the character lives:
 *
 *   water      Sorgilesh — the well-digger. A stone well with a bucket.
 *   fire       Ghargileh — angular, anxious. Spiked finials and embers.
 *   lightning  Fergoleh  — the explorer. A compass rose and a bolt signpost.
 *   history    (no character) — an archaeologist's dig: ruins and a lens.
 *   sport      Hogila    — sun-shaped, calm, a bow. A sun on a pole.
 *   knowledge  Geispli   — the scribe. A lectern with scroll and quill.
 *   unbuilt    Gilbib    — the king who sends a peace offer. A site with a crane, and one royal flag.
 *   tribal     Fingeil   — the only grey one, glasses, a halo. Torches, a totem, a floating halo.
 *   soil       Golmari   — the elder farmer with a cane. Roots, sprouts, cane and satchel.
 *
 * `wall` is the colour of an *unclaimed* storey. Claimed storeys always wear the
 * holding team's colour, so a theme never hides who owns what.
 */
import type { NeighborhoodTheme } from '@/types/api'

export type EmblemKind =
  | 'none'
  | 'drop'
  | 'flame'
  | 'bolt'
  | 'lens'
  | 'dumbbell'
  | 'book'
  | 'tablet'
  | 'seed'

export type MotifKind =
  | 'none'
  | 'well'
  | 'spikes'
  | 'compass'
  | 'ruins'
  | 'sun'
  | 'lectern'
  | 'construction'
  | 'halo'
  | 'roots'

export interface Palette {
  /** Unclaimed storey. */
  wall: number
  roof: number
  trim: number
  accent: number
  glass: number
  ground: number
  base: number
}

export interface Theme {
  key: NeighborhoodTheme
  label: string
  symbol: string
  character: string
  palette: Palette
  emblem: EmblemKind
  motif: MotifKind
}

export const THEMES: Record<NeighborhoodTheme, Theme> = {
  water: {
    key: 'water',
    label: 'آب',
    symbol: 'قطره',
    character: 'سورگیلش',
    palette: {
      wall: 0xd7e6ee,
      roof: 0x2a6a9c,
      trim: 0x1c4a6e,
      accent: 0x46b0dc,
      glass: 0xbdefff,
      ground: 0xdfeaf0,
      base: 0x93b1c3,
    },
    emblem: 'drop',
    motif: 'well',
  },
  fire: {
    key: 'fire',
    label: 'آتش',
    symbol: 'شعله',
    character: 'غرگیله',
    palette: {
      wall: 0xf0cfbd,
      roof: 0x8c2418,
      trim: 0x561610,
      accent: 0xec5227,
      glass: 0xffb15e,
      ground: 0xf1ddd0,
      base: 0xb26f60,
    },
    emblem: 'flame',
    motif: 'spikes',
  },
  lightning: {
    key: 'lightning',
    label: 'رعد و برق',
    symbol: 'صاعقه',
    character: 'فرگوله',
    palette: {
      wall: 0xf5dfbc,
      roof: 0xd96f18,
      trim: 0x86440f,
      accent: 0xf5b41a,
      glass: 0xfff1a0,
      ground: 0xf5e8d0,
      base: 0xc48f4f,
    },
    emblem: 'bolt',
    motif: 'compass',
  },
  history: {
    key: 'history',
    label: 'باستان‌شناسی',
    symbol: 'ذره‌بین',
    character: '—',
    palette: {
      wall: 0xe4dfc4,
      roof: 0x587a41,
      trim: 0x3a562c,
      accent: 0x88a457,
      glass: 0xf0ebc2,
      ground: 0xe6e2cb,
      base: 0xa4a080,
    },
    emblem: 'lens',
    motif: 'ruins',
  },
  sport: {
    key: 'sport',
    label: 'ورزش',
    symbol: 'دمبل',
    character: 'هوگیلا',
    palette: {
      wall: 0xf7ecc2,
      roof: 0xdba618,
      trim: 0x8a6810,
      accent: 0xf4c744,
      glass: 0xfff7bf,
      ground: 0xf7efd2,
      base: 0xbca055,
    },
    emblem: 'dumbbell',
    motif: 'sun',
  },
  knowledge: {
    key: 'knowledge',
    label: 'دانش',
    symbol: 'کتاب',
    character: 'گیسپلی',
    palette: {
      wall: 0xe6dbf0,
      roof: 0x5a3b8e,
      trim: 0x3a275c,
      accent: 0xa077d4,
      glass: 0xf4e5ff,
      ground: 0xebe3f2,
      base: 0xa091b6,
    },
    emblem: 'book',
    motif: 'lectern',
  },
  unbuilt: {
    key: 'unbuilt',
    label: 'نیمه‌ساخته',
    symbol: '—',
    character: 'گیلبیب',
    palette: {
      wall: 0xededed,
      roof: 0xb7b7b7,
      trim: 0x8c8c8c,
      accent: 0xd8b95a,
      glass: 0xf7f7f7,
      ground: 0xe4e4e4,
      base: 0xaeaeae,
    },
    emblem: 'none',
    motif: 'construction',
  },
  tribal: {
    key: 'tribal',
    label: 'قبیله‌ای',
    symbol: 'کتیبه',
    character: 'فینگیل',
    palette: {
      wall: 0xd6d0c4,
      roof: 0x46454e,
      trim: 0x2c2b33,
      accent: 0x6a5891,
      glass: 0xcdb8ff,
      ground: 0xdad4ca,
      base: 0x89847c,
    },
    emblem: 'tablet',
    motif: 'halo',
  },
  soil: {
    key: 'soil',
    label: 'خاک',
    symbol: 'بذر',
    character: 'گلمری',
    palette: {
      wall: 0xe5d5bd,
      roof: 0x6b4630,
      trim: 0x462e1e,
      accent: 0x8ea54a,
      glass: 0xf5e5c6,
      ground: 0xe0d0b8,
      base: 0x875f40,
    },
    emblem: 'seed',
    motif: 'roots',
  },
}

export const THEME_LIST: Theme[] = Object.values(THEMES)

/** A safe fallback before the design query has answered. */
export const DEFAULT_THEME: Theme = THEMES.soil

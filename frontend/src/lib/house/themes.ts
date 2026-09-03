/**
 * The nine neighbourhood themes.
 *
 * A theme is applied *over* a building type: the type decides the shape, the
 * theme decides the paint, the symbol on the shop sign, and one signature motif
 * that dresses the plot. That is how 26 types × 9 themes stay distinct without
 * 234 hand-built models — the brief's per-building prose is the reference the
 * motifs were chosen from, not a spec each one reproduces.
 *
 * `wall` is the colour of an *unclaimed* storey. Claimed storeys always wear
 * the holding team's colour, so a theme never hides who owns what.
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
  | 'moat'
  | 'embers'
  | 'sparks'
  | 'ruins'
  | 'pillars'
  | 'pages'
  | 'construction'
  | 'torches'
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
  palette: Palette
  emblem: EmblemKind
  motif: MotifKind
}

export const THEMES: Record<NeighborhoodTheme, Theme> = {
  water: {
    key: 'water',
    label: 'آب',
    symbol: 'قطره',
    palette: {
      wall: 0xd9e6ec,
      roof: 0x2f6f9f,
      trim: 0x1f4f73,
      accent: 0x4fb3d9,
      glass: 0xbfefff,
      ground: 0xe3eef3,
      base: 0x9db9c9,
    },
    emblem: 'drop',
    motif: 'moat',
  },
  fire: {
    key: 'fire',
    label: 'آتش',
    symbol: 'شعله',
    palette: {
      wall: 0xf0d3c2,
      roof: 0x8f2a1e,
      trim: 0x5c1a12,
      accent: 0xe8552b,
      glass: 0xffb36b,
      ground: 0xf2e1d6,
      base: 0xb9776a,
    },
    emblem: 'flame',
    motif: 'embers',
  },
  lightning: {
    key: 'lightning',
    label: 'رعد و برق',
    symbol: 'صاعقه',
    palette: {
      wall: 0xf4dfc0,
      roof: 0xd9741f,
      trim: 0x8a4a12,
      accent: 0xf2b21f,
      glass: 0xfff0a8,
      ground: 0xf5e9d6,
      base: 0xc79457,
    },
    emblem: 'bolt',
    motif: 'sparks',
  },
  history: {
    key: 'history',
    label: 'باستان‌شناسی',
    symbol: 'ذره‌بین',
    palette: {
      wall: 0xe4e0c8,
      roof: 0x5e7d46,
      trim: 0x3f5a30,
      accent: 0x8aa35c,
      glass: 0xf0ecc8,
      ground: 0xe8e4d0,
      base: 0xa9a586,
    },
    emblem: 'lens',
    motif: 'ruins',
  },
  sport: {
    key: 'sport',
    label: 'ورزش',
    symbol: 'دمبل',
    palette: {
      wall: 0xf6ebc4,
      roof: 0xd9a51f,
      trim: 0x8a6a12,
      accent: 0xf2c94c,
      glass: 0xfff6c2,
      ground: 0xf7efd6,
      base: 0xbfa25a,
    },
    emblem: 'dumbbell',
    motif: 'pillars',
  },
  knowledge: {
    key: 'knowledge',
    label: 'دانش',
    symbol: 'کتاب',
    palette: {
      wall: 0xe6dcef,
      roof: 0x5e3f8f,
      trim: 0x3d2a5e,
      accent: 0xa07cd0,
      glass: 0xf3e6ff,
      ground: 0xece5f2,
      base: 0xa393b8,
    },
    emblem: 'book',
    motif: 'pages',
  },
  unbuilt: {
    key: 'unbuilt',
    label: 'نیمه‌ساخته',
    symbol: '—',
    palette: {
      wall: 0xeeeeee,
      roof: 0xb9b9b9,
      trim: 0x8f8f8f,
      accent: 0xa8a8a8,
      glass: 0xf6f6f6,
      ground: 0xe6e6e6,
      base: 0xb0b0b0,
    },
    emblem: 'none',
    motif: 'construction',
  },
  tribal: {
    key: 'tribal',
    label: 'قبیله‌ای',
    symbol: 'کتیبه',
    palette: {
      wall: 0xd8d2c6,
      roof: 0x4b4a52,
      trim: 0x2f2e36,
      accent: 0x6b5a8f,
      glass: 0xcdb8ff,
      ground: 0xdcd6cc,
      base: 0x8d8880,
    },
    emblem: 'tablet',
    motif: 'torches',
  },
  soil: {
    key: 'soil',
    label: 'خاک',
    symbol: 'بذر',
    palette: {
      wall: 0xe6d6bf,
      roof: 0x6f4a2f,
      trim: 0x4a3120,
      accent: 0x8fa64a,
      glass: 0xf5e6c8,
      ground: 0xe2d2bb,
      base: 0x8a6242,
    },
    emblem: 'seed',
    motif: 'roots',
  },
}

export const THEME_LIST: Theme[] = Object.values(THEMES)

/** A safe fallback before the design query has answered. */
export const DEFAULT_THEME: Theme = THEMES.soil

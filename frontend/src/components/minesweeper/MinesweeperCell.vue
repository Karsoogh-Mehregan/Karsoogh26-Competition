<script setup lang="ts">
import { BombIcon, FlagIcon, FlagOffIcon } from '@lucide/vue'
import { formatBalance } from '@/lib/format'
import { cn } from '@/lib/utils'

export type MinesweeperCellView =
  | { kind: 'hidden'; flagged: boolean }
  | { kind: 'revealed'; adjacent: number }
  | { kind: 'mine'; exploded: boolean; flagged: boolean }
  | { kind: 'wrong-flag' }

const NUMBER_CLASS = [
  '',
  'text-blue-700 dark:text-blue-400',
  'text-emerald-700 dark:text-emerald-400',
  'text-red-600 dark:text-red-400',
  'text-indigo-800 dark:text-indigo-300',
  'text-amber-800 dark:text-amber-400',
  'text-cyan-700 dark:text-cyan-400',
  'text-foreground',
  'text-muted-foreground',
] as const

const props = defineProps<{
  row: number
  col: number
  view: MinesweeperCellView
  interactive: boolean
  flagMode: boolean
}>()

const emit = defineEmits<{
  reveal: [row: number, col: number]
  flag: [row: number, col: number]
}>()

let ignoreNextClick = false

function label(): string {
  const place = `خانه ردیف ${formatBalance(props.row + 1)}، ستون ${formatBalance(props.col + 1)}`
  const { view } = props
  if (view.kind === 'hidden') {
    return view.flagged ? `${place}، پرچم‌گذاری شده` : `${place}، باز نشده`
  }
  if (view.kind === 'revealed') {
    if (view.adjacent === 0) return `${place}، باز شده، خالی`
    return `${place}، باز شده، ${formatBalance(view.adjacent)} مین مجاور`
  }
  if (view.kind === 'wrong-flag') return `${place}، پرچم نادرست`
  if (view.exploded) return `${place}، مین منفجرشده`
  if (view.flagged) return `${place}، مین پرچم‌گذاری‌شده`
  return `${place}، مین`
}

function onClick(): void {
  if (!props.interactive) return
  if (ignoreNextClick) {
    ignoreNextClick = false
    return
  }
  if (props.flagMode) {
    emit('flag', props.row, props.col)
    return
  }
  emit('reveal', props.row, props.col)
}

function onContextMenu(event: MouseEvent): void {
  event.preventDefault()
  if (!props.interactive) return
  ignoreNextClick = true
  emit('flag', props.row, props.col)
}
</script>

<template>
  <button
    type="button"
    :disabled="!interactive"
    :aria-label="label()"
    :aria-pressed="view.kind === 'hidden' && view.flagged"
    class="flex size-full items-center justify-center rounded-[3px] border text-sm font-bold tabular-nums select-none"
    :class="
      cn(
        'touch-manipulation focus-visible:ring-ring focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:outline-none',
        view.kind === 'hidden' &&
          'border-border/80 bg-secondary shadow-[inset_0_1px_0_0_color-mix(in_oklab,white_55%,transparent)]',
        view.kind === 'hidden' &&
          interactive &&
          'hover:bg-accent hover:text-accent-foreground active:translate-y-px',
        view.kind === 'revealed' && 'border-border/60 bg-background text-foreground',
        view.kind === 'mine' && view.exploded && 'border-destructive/40 bg-destructive/20 text-destructive',
        view.kind === 'mine' && !view.exploded && 'border-border/60 bg-muted text-foreground',
        view.kind === 'wrong-flag' && 'border-destructive/40 bg-destructive/10 text-destructive',
        view.kind === 'revealed' && view.adjacent > 0 && NUMBER_CLASS[view.adjacent],
        !interactive && 'cursor-default',
      )
    "
    @click="onClick"
    @contextmenu="onContextMenu"
  >
    <FlagIcon
      v-if="view.kind === 'hidden' && view.flagged"
      class="size-3.5"
      aria-hidden="true"
    />
    <FlagIcon
      v-else-if="view.kind === 'mine' && view.flagged && !view.exploded"
      class="size-3.5 text-destructive"
      aria-hidden="true"
    />
    <BombIcon
      v-else-if="view.kind === 'mine'"
      class="size-3.5"
      aria-hidden="true"
    />
    <FlagOffIcon v-else-if="view.kind === 'wrong-flag'" class="size-3.5" aria-hidden="true" />
    <span v-else-if="view.kind === 'revealed' && view.adjacent > 0">
      {{ formatBalance(view.adjacent) }}
    </span>
  </button>
</template>

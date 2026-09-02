<script setup lang="ts">
import type { MinesweeperGame } from '@/types/api'
import MinesweeperCell, { type MinesweeperCellView } from './MinesweeperCell.vue'

const props = defineProps<{
  game: MinesweeperGame
  interactive: boolean
  flagMode: boolean
  busy: boolean
}>()

const emit = defineEmits<{
  reveal: [row: number, col: number]
  flag: [row: number, col: number]
}>()

function cellView(row: number, col: number): MinesweeperCellView {
  if (props.game.status === 'in_progress') {
    const cell = props.game.board.cells[row][col]
    if (cell.revealed) {
      return { kind: 'revealed', adjacent: cell.adjacent_mines }
    }
    return { kind: 'hidden', flagged: cell.flagged }
  }
  const cell = props.game.board.cells[row][col]
  if (cell.mine) {
    return { kind: 'mine', exploded: cell.revealed, flagged: cell.flagged }
  }
  if (cell.flagged) {
    return { kind: 'wrong-flag' }
  }
  if (cell.revealed) {
    return { kind: 'revealed', adjacent: cell.adjacent_mines }
  }
  return { kind: 'hidden', flagged: false }
}

function cellSize(): string {
  if (props.game.width <= 9) return '2.25rem'
  if (props.game.width <= 16) return '2rem'
  return '1.75rem'
}

function onReveal(row: number, col: number): void {
  if (!props.interactive || props.busy) return
  const view = cellView(row, col)
  if (view.kind !== 'hidden' || view.flagged) return
  emit('reveal', row, col)
}

function onFlag(row: number, col: number): void {
  if (!props.interactive || props.busy) return
  const view = cellView(row, col)
  if (view.kind !== 'hidden') return
  emit('flag', row, col)
}
</script>

<template>
  <div
    class="min-w-0 max-w-full overflow-x-auto overscroll-x-contain"
    @contextmenu.prevent
    @dragstart.prevent
  >
    <div
      dir="ltr"
      role="grid"
      :aria-rowcount="game.height"
      :aria-colcount="game.width"
      :aria-busy="busy"
      :aria-disabled="!interactive"
      class="mx-auto w-max select-none"
      :style="{
        display: 'grid',
        gridTemplateColumns: `repeat(${game.width}, ${cellSize()})`,
        gridTemplateRows: `repeat(${game.height}, ${cellSize()})`,
        gap: '1px',
        background: 'var(--border)',
        padding: '1px',
        borderRadius: '0.4rem',
      }"
    >
      <template v-for="(rowCells, row) in game.board.cells" :key="row">
        <div v-for="(_cell, col) in rowCells" :key="`${row}-${col}`" role="gridcell">
          <MinesweeperCell
            :row="row"
            :col="col"
            :view="cellView(row, col)"
            :interactive="interactive && !busy"
            :flag-mode="flagMode"
            @reveal="onReveal"
            @flag="onFlag"
          />
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { TargetIcon } from '@lucide/vue'
import type { CSSProperties } from 'vue'
import type { TerritoryCell, TerritoryGame, TerritoryTeam } from '@/types/api'

const props = defineProps<{
  game: TerritoryGame
  selectableKeys: Set<string>
  selectedKey: string | null
  myTeamCode: string | null
  busy: boolean
}>()

const emit = defineEmits<{
  select: [cell: TerritoryCell]
}>()

const FALLBACK_COLORS = ['#2b6ca8', '#e67e22']

function cellKey(cell: TerritoryCell): string {
  return `${cell.row}:${cell.column}`
}

function ownerColor(owner: TerritoryTeam | null): string {
  if (!owner) return ''
  const index = props.game.players.findIndex((player) => player.code === owner.code)
  return owner.color ?? FALLBACK_COLORS[Math.max(0, index)]
}

function cellStyle(cell: TerritoryCell): CSSProperties {
  const color = ownerColor(cell.owner)
  return color ? ({ '--owner-color': color } as CSSProperties) : {}
}

function isMine(cell: TerritoryCell): boolean {
  return cell.owner?.code === props.myTeamCode
}

function isSelectable(cell: TerritoryCell): boolean {
  return props.selectableKeys.has(cellKey(cell))
}

function cellLabel(cell: TerritoryCell): string {
  const position = `ردیف ${cell.row + 1}، ستون ${cell.column + 1}`
  const owner = cell.owner ? `متعلق به ${cell.owner.name}` : 'بدون مالک'
  const action = isSelectable(cell) ? '، قابل انتخاب' : ''
  return `${position}، ارزش ${cell.value}، ${owner}${action}`
}
</script>

<template>
  <div class="board-shell" aria-label="صفحه پنج در پنج نبرد قلمرو">
    <div class="territory-grid" dir="ltr">
      <button
        v-for="cell in game.board.flat()"
        :key="cellKey(cell)"
        type="button"
        dir="rtl"
        class="territory-cell"
        :class="{
          'is-owned': !!cell.owner,
          'is-mine': isMine(cell),
          'is-selectable': isSelectable(cell),
          'is-selected': selectedKey === cellKey(cell),
        }"
        :data-value="cell.value"
        :style="cellStyle(cell)"
        :disabled="busy || !isSelectable(cell)"
        :aria-pressed="selectedKey === cellKey(cell)"
        :aria-label="cellLabel(cell)"
        @click="emit('select', cell)"
      >
        <span class="cell-coordinate">{{ cell.row + 1 }}·{{ cell.column + 1 }}</span>
        <span class="cell-value" aria-hidden="true">{{ cell.value }}</span>
        <span v-if="cell.owner" class="cell-owner">
          <span class="owner-dot" />
          <span class="truncate">{{ cell.owner.name }}</span>
        </span>
        <span v-else class="cell-owner text-muted-foreground">آزاد</span>
        <span v-if="selectedKey === cellKey(cell)" class="selected-mark" aria-hidden="true">
          <TargetIcon class="size-4" />
        </span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.board-shell {
  position: relative;
  overflow: hidden;
  width: 100%;
  padding: clamp(0.5rem, 1.4vw, 0.875rem);
  border: 1px solid color-mix(in oklab, var(--border) 78%, #2b6ca8 22%);
  border-radius: calc(var(--radius) * 2.1);
  background:
    radial-gradient(circle at 15% 5%, rgb(43 108 168 / 10%), transparent 32%),
    radial-gradient(circle at 90% 95%, rgb(230 126 34 / 8%), transparent 30%),
    color-mix(in oklab, var(--card) 94%, #eaf3fa 6%);
  box-shadow: 0 24px 60px -34px rgb(15 23 42 / 48%);
}

.territory-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: clamp(0.35rem, 0.9vw, 0.65rem);
}

.territory-cell {
  position: relative;
  display: flex;
  aspect-ratio: 1;
  min-width: 0;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid color-mix(in oklab, var(--border) 86%, #2b6ca8 14%);
  border-radius: clamp(0.65rem, 1.35vw, 1rem);
  background: linear-gradient(145deg, #fff, #f5f8fb);
  color: var(--foreground);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 72%), 0 7px 16px -13px rgb(15 23 42 / 70%);
  transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
}

.territory-cell[data-value='1'] { background: linear-gradient(145deg, #fff, #f0f8fc); }
.territory-cell[data-value='2'] { background: linear-gradient(145deg, #fff, #edf6fb); }
.territory-cell[data-value='3'] { background: linear-gradient(145deg, #fff, #f1f4f8); }
.territory-cell[data-value='4'] { background: linear-gradient(145deg, #fff, #f5f2ee); }
.territory-cell[data-value='5'] { background: linear-gradient(145deg, #fff, #f8eee7); }

.territory-cell.is-owned {
  border-color: color-mix(in oklab, var(--owner-color) 78%, #111 22%);
  background:
    linear-gradient(155deg, rgb(255 255 255 / 22%), transparent 42%),
    color-mix(in oklab, var(--owner-color) 82%, #16202c 18%);
  color: white;
  text-shadow: 0 1px 2px rgb(0 0 0 / 28%);
}

.territory-cell.is-owned::after {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 50% 110%, rgb(255 255 255 / 20%), transparent 55%);
  content: '';
  pointer-events: none;
}

.territory-cell.is-selectable {
  cursor: pointer;
  border-color: #2b6ca8;
  box-shadow: 0 0 0 2px rgb(43 108 168 / 16%), 0 14px 26px -18px rgb(43 108 168 / 90%);
  animation: available-pulse 2.4s ease-in-out infinite;
}

.territory-cell.is-selectable:hover,
.territory-cell.is-selectable:focus-visible {
  z-index: 2;
  transform: translateY(-3px) scale(1.025);
  outline: none;
  box-shadow: 0 0 0 3px rgb(43 108 168 / 24%), 0 18px 30px -18px rgb(43 108 168 / 90%);
}

.territory-cell.is-selected {
  z-index: 3;
  border-color: #e67e22;
  transform: translateY(-3px) scale(1.035);
  box-shadow: 0 0 0 3px rgb(230 126 34 / 30%), 0 22px 36px -20px rgb(230 126 34 / 90%);
  animation: none;
}

.territory-cell:disabled:not(.is-selectable) { cursor: default; }
.cell-coordinate { position: absolute; inset-block-start: 0.4rem; inset-inline-start: 0.5rem; font-family: var(--font-secondary); font-size: clamp(0.55rem, 1vw, 0.7rem); opacity: 0.62; }
.cell-value { font-family: var(--font-secondary); font-size: clamp(1.35rem, 4.1vw, 2.65rem); line-height: 1; font-weight: 900; font-variant-numeric: tabular-nums; }
.cell-owner { position: absolute; inset-inline: 0.35rem; inset-block-end: 0.35rem; display: flex; align-items: center; justify-content: center; gap: 0.3rem; font-size: clamp(0.55rem, 1.05vw, 0.72rem); }
.owner-dot { width: 0.4rem; height: 0.4rem; flex: none; border: 1px solid rgb(255 255 255 / 65%); border-radius: 999px; background: var(--owner-color); box-shadow: 0 0 0 1px rgb(0 0 0 / 18%); }
.selected-mark { position: absolute; inset-block-start: 0.35rem; inset-inline-end: 0.4rem; display: grid; place-items: center; color: #fff; filter: drop-shadow(0 1px 2px rgb(0 0 0 / 45%)); }

@media (min-width: 1024px) {
  .board-shell {
    display: flex;
  }

  .territory-grid {
    min-height: 0;
    flex: 1;
    grid-template-rows: repeat(5, minmax(0, 1fr));
  }

  .territory-cell {
    aspect-ratio: auto;
    min-height: 0;
  }
}

@media (max-width: 480px) {
  .board-shell {
    padding: 0.35rem;
    border-radius: calc(var(--radius) * 1.45);
  }

  .territory-grid {
    gap: 0.25rem;
  }

  .territory-cell {
    border-radius: 0.55rem;
  }

  .cell-coordinate {
    inset-block-start: 0.22rem;
    inset-inline-start: 0.3rem;
    font-size: 0.48rem;
  }

  .cell-owner {
    inset-block-end: 0.2rem;
    font-size: 0.48rem;
  }
}

@keyframes available-pulse {
  0%, 100% { box-shadow: 0 0 0 2px rgb(43 108 168 / 13%), 0 12px 24px -18px rgb(43 108 168 / 75%); }
  50% { box-shadow: 0 0 0 4px rgb(43 108 168 / 20%), 0 16px 28px -18px rgb(43 108 168 / 95%); }
}

@media (prefers-reduced-motion: reduce) {
  .territory-cell { transition: none; }
  .territory-cell.is-selectable { animation: none; }
}
</style>

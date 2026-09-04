import { computed } from 'vue'
import { useMeQuery } from '@/queries/auth'
import { useBoardStore } from '@/stores/board'
import type { Board } from '@/types/api'

/**
 * The board every board-scoped query should key and filter on.
 *
 * A team is locked to its own; an organiser picks, and the pick lives in
 * `stores/board.ts`. The API applies the same rule server-side, so a team
 * sending someone else's board changes nothing.
 */
export function useBoard() {
  const me = useMeQuery()
  const store = useBoardStore()

  const board = computed<Board>(
    () => me.data.value?.team?.board ?? store.viewingBoard,
  )
  const canSwitchBoard = computed(() => !!me.data.value && !me.data.value.team)

  return { board, canSwitchBoard, setViewingBoard: store.setViewingBoard }
}

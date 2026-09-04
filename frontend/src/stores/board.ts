import { useLocalStorage } from '@vueuse/core'
import { defineStore } from 'pinia'
import type { Board } from '@/types/api'

const STORAGE_KEY = 'karsoogh.viewing-board'

/**
 * Which contest an organiser is looking at.
 *
 * Only organisers have a choice here: a team's board comes from `me` and is not
 * selectable, which is why `useBoard()` prefers that over this store.
 */
export const useBoardStore = defineStore('board', () => {
  const viewingBoard = useLocalStorage<Board>(STORAGE_KEY, 'girls')

  function setViewingBoard(board: Board): boolean {
    if (board === viewingBoard.value) {
      return false
    }
    viewingBoard.value = board
    return true
  }

  return { viewingBoard, setViewingBoard }
})

import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAttemptStore = defineStore('attempt', () => {
  const selectedOccupancyId = ref<number | null>(null)

  function select(id: number | null): void {
    selectedOccupancyId.value = id
  }

  return { selectedOccupancyId, select }
})

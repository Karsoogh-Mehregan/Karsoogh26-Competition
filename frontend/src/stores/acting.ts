import { useLocalStorage } from '@vueuse/core'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'karsoogh.acting-team'

export const useActingStore = defineStore('acting', () => {
  const actingCode = useLocalStorage<string | null>(STORAGE_KEY, null)

  function setActingCode(code: string | null): boolean {
    if (code === actingCode.value) {
      return false
    }
    actingCode.value = code
    return true
  }

  return { actingCode, setActingCode }
})

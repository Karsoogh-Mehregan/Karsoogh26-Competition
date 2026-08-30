import { ref } from 'vue'
import { toast } from 'vue-sonner'
import { api, ensureCsrf, readApiError } from '../lib/api.js'
import { useGraph } from './useGraph.js'

let singleton = null

const STORAGE_KEY = 'karsoogh.acting-team'

function readStoredCode() {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStoredCode(code) {
  try {
    if (code) {
      localStorage.setItem(STORAGE_KEY, code)
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  } catch {
    // A browser with site data blocked still works, it just forgets on reload.
  }
}

function createActingState() {
  const me = ref(null)
  const teams = ref([])
  // The team whose turn we are playing. Client-side only: the server takes it
  // as a path segment on every team-scoped call.
  const actingTeam = ref(null)
  const loading = ref(true)
  const error = ref('')
  const submitting = ref(false)

  async function loadTeams() {
    const response = await api('/api/teams/')
    if (!response.ok) {
      throw new Error(await readApiError(response))
    }
    teams.value = await response.json()
  }

  function restoreActingTeam() {
    const code = readStoredCode()
    const team = code ? teams.value.find((item) => item.code === code) : null
    actingTeam.value = team ?? null
    if (code && !team) {
      writeStoredCode(null)
    }
  }

  async function bootstrap() {
    loading.value = true
    error.value = ''
    try {
      await ensureCsrf()
      const response = await api('/api/auth/me/')
      if (response.status === 403) {
        me.value = null
        teams.value = []
        actingTeam.value = null
        return
      }
      if (!response.ok) {
        throw new Error(await readApiError(response))
      }
      me.value = await response.json()
      await loadTeams()
      restoreActingTeam()
    } catch (err) {
      error.value = err.message || 'بارگذاری ناموفق بود.'
    } finally {
      loading.value = false
    }
  }

  async function login(username, password) {
    submitting.value = true
    error.value = ''
    try {
      await ensureCsrf()
      const response = await api('/api/auth/login/', {
        method: 'POST',
        json: { username, password },
      })
      if (!response.ok) {
        error.value =
          response.status === 400
            ? 'نام کاربری یا رمز عبور نادرست است.'
            : await readApiError(response)
        return
      }
      me.value = await response.json()
      await loadTeams()
      restoreActingTeam()
    } catch (err) {
      error.value = err.message || 'ورود ناموفق بود.'
    } finally {
      submitting.value = false
    }
  }

  function actAs(team) {
    const selectedCode = team?.code ?? null
    if (selectedCode === (actingTeam.value?.code ?? null)) {
      return
    }
    actingTeam.value = team ?? null
    writeStoredCode(selectedCode)
    error.value = ''
    useGraph().reset()
    toast.success(team ? `تیم «${team.name}» انتخاب شد` : 'انتخاب تیم برداشته شد')
  }

  async function logout() {
    submitting.value = true
    error.value = ''
    try {
      await ensureCsrf()
      const response = await api('/api/auth/logout/', { method: 'POST' })
      if (!response.ok) {
        error.value = await readApiError(response)
        return
      }
      me.value = null
      teams.value = []
      actingTeam.value = null
      writeStoredCode(null)
      useGraph().reset()
      await ensureCsrf()
    } catch (err) {
      error.value = err.message || 'خروج ناموفق بود.'
    } finally {
      submitting.value = false
    }
  }

  async function claimStart(nodeId) {
    const code = actingTeam.value?.code
    if (!code) {
      throw new Error('ابتدا یک تیم انتخاب کنید.')
    }
    await ensureCsrf()
    const response = await api(`/api/teams/${encodeURIComponent(code)}/claim-start/`, {
      method: 'POST',
      json: { node: nodeId },
    })
    if (!response.ok) {
      throw new Error(await readApiError(response))
    }
    const team = await response.json()
    actingTeam.value = team
    teams.value = teams.value.map((item) => (item.code === team.code ? { ...item, ...team } : item))
    return team
  }

  return {
    me,
    teams,
    actingTeam,
    loading,
    error,
    submitting,
    bootstrap,
    login,
    actAs,
    logout,
    claimStart,
  }
}

export function useActing() {
  if (!singleton) {
    singleton = createActingState()
  }
  return singleton
}

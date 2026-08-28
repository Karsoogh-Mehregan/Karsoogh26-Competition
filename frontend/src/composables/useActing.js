import { ref } from 'vue'
import { toast } from 'vue-sonner'
import { api, ensureCsrf, readApiError } from '../lib/api.js'
import { useGraph } from './useGraph.js'

let singleton = null

function createActingState() {
  const me = ref(null)
  const teams = ref([])
  const loading = ref(true)
  const error = ref('')
  const selecting = ref(null)
  const submitting = ref(false)

  async function loadTeams() {
    const response = await api('/api/teams/')
    if (!response.ok) {
      throw new Error(await readApiError(response))
    }
    teams.value = await response.json()
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
        return
      }
      if (!response.ok) {
        throw new Error(await readApiError(response))
      }
      me.value = await response.json()
      await loadTeams()
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
    } catch (err) {
      error.value = err.message || 'ورود ناموفق بود.'
    } finally {
      submitting.value = false
    }
  }

  async function actAs(team) {
    if (me.value?.acting_team?.code === team.code) {
      return
    }
    selecting.value = team.code
    error.value = ''
    try {
      await ensureCsrf()
      const response = await api('/api/auth/act-as/', {
        method: 'POST',
        json: { team: team.code },
      })
      if (!response.ok) {
        throw new Error(await readApiError(response))
      }
      me.value = await response.json()
      toast.success(`تیم «${team.name}» انتخاب شد`)
    } catch (err) {
      error.value = err.message || 'انتخاب تیم ناموفق بود.'
      toast.error(error.value)
    } finally {
      selecting.value = null
    }
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
      useGraph().reset()
      await ensureCsrf()
    } catch (err) {
      error.value = err.message || 'خروج ناموفق بود.'
    } finally {
      submitting.value = false
    }
  }

  return { me, teams, loading, error, selecting, submitting, bootstrap, login, actAs, logout }
}

export function useActing() {
  if (!singleton) {
    singleton = createActingState()
  }
  return singleton
}

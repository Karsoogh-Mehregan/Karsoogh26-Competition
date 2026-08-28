let csrfToken = ''

function readCookie(name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : ''
}

function refreshCsrfFromCookie() {
  const fromCookie = readCookie('csrftoken')
  if (fromCookie) {
    csrfToken = fromCookie
  }
}

export async function ensureCsrf() {
  const response = await fetch('/api/auth/csrf/', { credentials: 'include' })
  try {
    const data = await response.json()
    if (typeof data.csrf_token === 'string' && data.csrf_token) {
      csrfToken = data.csrf_token
      return
    }
  } catch {
    // fall through to the cookie
  }
  refreshCsrfFromCookie()
}

export async function api(path, { method = 'GET', json } = {}) {
  const headers = {}
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  const token = csrfToken || readCookie('csrftoken')
  if (token && method !== 'GET' && method !== 'HEAD') {
    headers['X-CSRFToken'] = token
  }
  const response = await fetch(path, {
    method,
    credentials: 'include',
    headers,
    body: json !== undefined ? JSON.stringify(json) : undefined,
  })
  refreshCsrfFromCookie()
  return response
}

export async function readApiError(response) {
  try {
    const data = await response.json()
    if (typeof data.detail === 'string') {
      return data.detail
    }
  } catch {
    // fall through
  }
  return response.statusText
}

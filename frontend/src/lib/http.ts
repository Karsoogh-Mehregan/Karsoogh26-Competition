const BASE = '/api'
const CSRF_COOKIE = 'csrftoken'
const CSRF_HEADER = 'X-CSRFToken'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE'])

// `fetch` waits forever by default and nginx gives /api/ a 24h read timeout so
// that SSE can hold a stream open. Between the two, a request that stalls never
// fails — the button spins until the player reloads the page. This is the only
// place that ends one.
const REQUEST_TIMEOUT_MS = 20_000
// An answer carries an image over event wifi, so uploads get their own budget.
const UPLOAD_TIMEOUT_MS = 120_000
const TIMED_OUT = Symbol('request timed out')

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface RequestOptions {
  method?: HttpMethod
  json?: unknown
  form?: FormData
  signal?: AbortSignal
  timeoutMs?: number
}

type FieldErrors = Record<string, string[]>

export class ApiError extends Error {
  status: number
  detail: string
  fieldErrors: FieldErrors | null
  data: unknown

  constructor(status: number, detail: string, fieldErrors: FieldErrors | null, data: unknown) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.fieldErrors = fieldErrors
    this.data = data
  }
}

let csrfToken = ''

function readCookie(name: string): string {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : ''
}

function refreshCsrfFromCookie(): void {
  const fromCookie = readCookie(CSRF_COOKIE)
  if (fromCookie) {
    csrfToken = fromCookie
  }
}

async function timedFetch(
  url: string,
  init: RequestInit,
  signal?: AbortSignal,
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(TIMED_OUT), timeoutMs)
  // The caller's signal is how TanStack cancels a query, so it has to keep
  // aborting with its own reason rather than being reported as a timeout.
  const relay = () => controller.abort(signal?.reason)
  signal?.addEventListener('abort', relay)

  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } catch (error) {
    if (controller.signal.reason === TIMED_OUT) {
      throw new ApiError(408, 'پاسخی از سرور نرسید؛ دوباره تلاش کنید.', null, null)
    }
    throw error
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', relay)
  }
}

export async function ensureCsrf(): Promise<void> {
  const response = await timedFetch(`${BASE}/auth/csrf/`, { credentials: 'include' })
  try {
    const data = (await response.json()) as { csrf_token?: unknown }
    if (typeof data.csrf_token === 'string' && data.csrf_token) {
      csrfToken = data.csrf_token
      return
    }
  } catch {
    refreshCsrfFromCookie()
    return
  }
  refreshCsrfFromCookie()
}

function isFieldErrors(data: object): data is FieldErrors {
  return Object.values(data).some(
    (value) => Array.isArray(value) && value.every((item) => typeof item === 'string'),
  )
}

function fallbackDetail(status: number): string {
  if (status === 403) return 'مجوز این کار را ندارید.'
  if (status === 404) return 'یافت نشد.'
  if (status >= 500) return 'خطای سرور'
  return 'خطا در ارتباط با سرور.'
}

async function toApiError(response: Response): Promise<ApiError> {
  let data: unknown = null
  try {
    data = await response.json()
  } catch {
    data = null
  }

  let detail = ''
  let fieldErrors: FieldErrors | null = null

  if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
    const maybeDetail = (data as { detail?: unknown }).detail
    if (typeof maybeDetail === 'string') {
      detail = maybeDetail
    }
    if (isFieldErrors(data)) {
      fieldErrors = data as FieldErrors
      if (!detail) {
        const first = Object.values(fieldErrors).find((messages) => messages.length > 0)
        detail = first?.[0] ?? ''
      }
    }
  }

  return new ApiError(response.status, detail || fallbackDetail(response.status), fieldErrors, data)
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', json, form, signal, timeoutMs } = options
  const headers: Record<string, string> = {}

  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  // No Content-Type for `form`: the browser sets multipart/form-data with the boundary itself.

  if (!SAFE_METHODS.has(method)) {
    if (!csrfToken) {
      refreshCsrfFromCookie()
    }
    if (!csrfToken) {
      await ensureCsrf()
    }
    if (csrfToken) {
      headers[CSRF_HEADER] = csrfToken
    }
  }

  const response = await timedFetch(
    `${BASE}${path}`,
    {
      method,
      credentials: 'include',
      headers,
      body: form ?? (json !== undefined ? JSON.stringify(json) : undefined),
    },
    signal,
    timeoutMs ?? (form ? UPLOAD_TIMEOUT_MS : REQUEST_TIMEOUT_MS),
  )

  // Django rotates the token on login(); the response carries the new cookie.
  refreshCsrfFromCookie()

  if (!response.ok) {
    throw await toApiError(response)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { method: 'GET', signal })
}

export function post<T>(path: string, json?: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { method: 'POST', json, signal })
}

export function patch<T>(path: string, json?: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { method: 'PATCH', json, signal })
}

export function postForm<T>(path: string, form: FormData, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { method: 'POST', form, signal })
}

export function del<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { method: 'DELETE', signal })
}

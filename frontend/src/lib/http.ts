const BASE = '/api'
const CSRF_COOKIE = 'csrftoken'
const CSRF_HEADER = 'X-CSRFToken'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE'])

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface RequestOptions {
  method?: HttpMethod
  json?: unknown
  signal?: AbortSignal
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

export async function ensureCsrf(): Promise<void> {
  const response = await fetch(`${BASE}/auth/csrf/`, { credentials: 'include' })
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
  const { method = 'GET', json, signal } = options
  const headers: Record<string, string> = {}

  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

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

  const response = await fetch(`${BASE}${path}`, {
    method,
    credentials: 'include',
    headers,
    body: json !== undefined ? JSON.stringify(json) : undefined,
    signal,
  })

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

export function del<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { method: 'DELETE', signal })
}

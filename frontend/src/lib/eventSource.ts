const STREAM_URL = '/api/realtime/stream/'

export interface BoardStreamHandlers {
  events: readonly string[]
  onEvent: (eventType: string, data: unknown) => void
  onOpen?: () => void
  onError?: (closed: boolean) => void
}

function parse(raw: string): unknown {
  try {
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

/** Opens the stream and returns its closer.
 *
 *  The browser retries a connection that drops once it is established, but a
 *  non-2xx answer — a 502 while the backend restarts, a 401 — fails the stream
 *  for good and is never retried. `onError` reports which of the two happened
 *  through `closed`; only the caller can reopen the second kind. */
export function openBoardStream(handlers: BoardStreamHandlers): () => void {
  const source = new EventSource(STREAM_URL, { withCredentials: true })

  source.onopen = () => handlers.onOpen?.()
  source.onerror = () => handlers.onError?.(source.readyState === EventSource.CLOSED)

  for (const eventType of handlers.events) {
    source.addEventListener(eventType, (event) => {
      handlers.onEvent(eventType, parse((event as MessageEvent).data))
    })
  }

  return () => {
    source.onopen = null
    source.onerror = null
    source.close()
  }
}

const STREAM_URL = '/api/realtime/stream/'

export interface BoardStreamHandlers {
  onEvent: (eventType: string, data: unknown) => void
  onOpen?: () => void
  onError?: (closed: boolean) => void
}

export const BOARD_EVENTS = [
  'board.spawn.claimed',
  'board.node.claimed',
  'board.graded',
  'board.released',
  'question.assigned',
  'mentor.submission.created',
  'resync',
] as const

function parse(raw: string): unknown {
  try {
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

/** Opens the stream and returns its closer. Reconnection is the browser's job:
 *  EventSource retries on its own and honours the server's `retry:` field. */
export function openBoardStream(handlers: BoardStreamHandlers): () => void {
  const source = new EventSource(STREAM_URL, { withCredentials: true })

  source.onopen = () => handlers.onOpen?.()
  source.onerror = () => handlers.onError?.(source.readyState === EventSource.CLOSED)

  for (const eventType of BOARD_EVENTS) {
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

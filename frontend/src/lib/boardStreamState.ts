import { ref } from 'vue'

// Transport-level, like http.ts's module-scoped csrfToken. Queries import this
// to fall back to polling while the stream is down; importing the composable
// instead would invert the layering.
export const streamConnected = ref(false)

/**
 * The browser's own notification tray.
 *
 * A thin wrapper for three reasons: `window.Notification` collides by name with
 * our own `Notification` model type, the API throws outright in an insecure
 * context, and permission must be asked for from a real user gesture — Chrome
 * rejects a request that is not user-activated, and a prompt fired on page load
 * is the fastest way to get permanently denied.
 *
 * So nothing here asks on its own. `requestPermission()` is wired to a button.
 */

export type NotifyPermission = 'unsupported' | 'default' | 'granted' | 'denied'

export function isSupported(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window
}

export function permission(): NotifyPermission {
  if (!isSupported()) return 'unsupported'
  return window.Notification.permission as NotifyPermission
}

export async function requestPermission(): Promise<NotifyPermission> {
  if (!isSupported()) return 'unsupported'
  try {
    return (await window.Notification.requestPermission()) as NotifyPermission
  } catch {
    // Safari < 16 only has the callback form, and an insecure origin throws.
    return permission()
  }
}

export interface DeskNotice {
  title: string
  body?: string
  tag?: string
}

/** Best-effort: a tray notification is a courtesy, never the only channel. */
export function show(notice: DeskNotice): void {
  if (permission() !== 'granted') return
  try {
    const shown = new window.Notification(notice.title, {
      body: notice.body,
      // Same tag replaces rather than stacks, so a burst of board events does
      // not bury the screen.
      tag: notice.tag,
      lang: 'fa',
      dir: 'rtl',
    })
    shown.onclick = () => {
      window.focus()
      shown.close()
    }
  } catch {
    // Some browsers only allow construction from a service worker.
  }
}

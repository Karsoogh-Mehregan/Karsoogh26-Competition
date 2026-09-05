/**
 * «وقت اضافه», told to the hall.
 *
 * The clock updating on its own is not an announcement: a countdown that jumps
 * from «پایان» back to ten minutes, with the board reopening under it, is a
 * mystery from the floor. The server therefore sends `game.time_extended`
 * beside the usual `game.state` hint, carrying the size of the grant — the one
 * number that exists nowhere else to be refetched from — and this raises it.
 *
 * Same shape as `useNotificationAnnouncer`: called exactly once, from `App.vue`,
 * because a toast owned by a panel is a toast nobody sees while that panel is
 * closed.
 */
import { watch } from 'vue'
import { toast } from 'vue-sonner'
import { consumeTimeExtensionSuppression, lastTimeExtension } from '@/lib/boardStreamState'

/** Call once, from App.vue. */
export function useTimeExtensionAnnouncer(): void {
  watch(lastTimeExtension, (frame) => {
    if (!frame) return
    if (consumeTimeExtensionSuppression()) return
    toast.info(`${frame.minutes} دقیقه وقت اضافه اعلام شد`, {
      description: frame.resumed
        ? 'بازی از سر گرفته شد؛ زمان باقی‌مانده در نوار بالا به‌روز شده است.'
        : 'زمان باقی‌مانده در نوار بالا به‌روز شده است.',
      duration: 8000,
    })
  })
}

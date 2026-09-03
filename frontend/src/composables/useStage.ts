/**
 * Which step of the game the person looking at the screen is on.
 *
 * Derived, never stored: the server already knows everything needed (game
 * status, whether the team holds a spawn, whether an attempt is open), so a
 * separate "stage" field would only be one more thing to get out of sync.
 */
import { computed } from 'vue'
import { useActing } from '@/composables/useActing'
import { useAttempts } from '@/composables/useAttempts'
import { useGameClock } from '@/composables/useGameClock'

export type StageKey = 'signed_out' | 'waiting' | 'spawn' | 'expand' | 'answer' | 'grading' | 'over'

export interface Step {
  key: StageKey
  label: string
}

/** The player's path, in order. Mentors and lobby states sit outside it. */
export const STEPS: Step[] = [
  { key: 'spawn', label: 'خانهٔ شروع' },
  { key: 'expand', label: 'انتخاب خانه' },
  { key: 'answer', label: 'پاسخ به سؤال' },
  { key: 'grading', label: 'در انتظار نمره' },
]

const COPY: Record<StageKey, { title: string; hint: string }> = {
  signed_out: { title: 'خارج از بازی', hint: 'برای شروع وارد حساب تیم شوید.' },
  waiting: { title: 'در انتظار شروع', hint: 'بازی هنوز آغاز نشده است.' },
  spawn: { title: 'خانهٔ شروع', hint: 'روی نقشه خانهٔ شروع رنگ تیم خود را انتخاب کنید.' },
  expand: { title: 'انتخاب خانه', hint: 'یک خانهٔ مجاور را رزرو کنید تا سؤال بگیرید.' },
  answer: { title: 'پاسخ به سؤال', hint: 'سؤال باز دارید — پیش از پایان مهلت پاسخ دهید.' },
  grading: { title: 'در انتظار نمره', hint: 'پاسخ ثبت شد؛ منتظر تصحیح بمانید.' },
  over: { title: 'پایان بازی', hint: 'بازی تمام شد. جدول امتیازات نتیجهٔ نهایی است.' },
}

export function useStage() {
  const { me, actingTeam, isPlayer } = useActing()
  const { state } = useGameClock()
  const { questionAttempts } = useAttempts()

  const stage = computed<StageKey>(() => {
    if (!me.value) return 'signed_out'

    const status = state.value?.status
    if (status === 'finished') return 'over'
    // A mentor watching a team should see that team's step, not a lobby message.
    if (!isPlayer.value) return status === 'running' ? 'expand' : 'waiting'
    if (status === 'not_started' || status === 'paused') return 'waiting'

    if ((actingTeam.value?.holdings.length ?? 0) === 0) return 'spawn'

    const attempts = questionAttempts.value
    if (attempts.some((attempt) => attempt.status === 'open')) return 'answer'
    if (attempts.some((attempt) => attempt.status === 'answered')) return 'grading'
    return 'expand'
  })

  const title = computed(() => COPY[stage.value].title)
  const hint = computed(() => COPY[stage.value].hint)

  /** Index into STEPS, or -1 when the player is not on the path at all. */
  const stepIndex = computed(() => STEPS.findIndex((step) => step.key === stage.value))
  const onPath = computed(() => stepIndex.value >= 0)

  return { stage, title, hint, stepIndex, onPath, steps: STEPS }
}

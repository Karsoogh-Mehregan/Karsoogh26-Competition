let audioContext: AudioContext | null = null

function context(): AudioContext | null {
  if (typeof window === 'undefined') return null
  const AudioContextClass = window.AudioContext
  if (!AudioContextClass) return null
  audioContext ??= new AudioContextClass()
  if (audioContext.state === 'suspended') void audioContext.resume()
  return audioContext
}

function tone(
  ctx: AudioContext,
  frequency: number,
  startsIn: number,
  duration: number,
  gainValue: number,
  type: OscillatorType = 'sine',
): void {
  const oscillator = ctx.createOscillator()
  const gain = ctx.createGain()
  const startsAt = ctx.currentTime + startsIn
  oscillator.type = type
  oscillator.frequency.setValueAtTime(frequency, startsAt)
  gain.gain.setValueAtTime(0.0001, startsAt)
  gain.gain.exponentialRampToValueAtTime(gainValue, startsAt + 0.008)
  gain.gain.exponentialRampToValueAtTime(0.0001, startsAt + duration)
  oscillator.connect(gain).connect(ctx.destination)
  oscillator.start(startsAt)
  oscillator.stop(startsAt + duration + 0.02)
}

export function playDiceRollSound(): void {
  const ctx = context()
  if (!ctx) return
  const clicks = [0, 0.07, 0.14, 0.22, 0.31, 0.41, 0.53, 0.67, 0.83, 1.01]
  clicks.forEach((at, index) => {
    tone(ctx, 150 + (index % 3) * 34, at, 0.055, 0.045, 'square')
    tone(ctx, 82 + (index % 2) * 12, at + 0.015, 0.06, 0.025, 'triangle')
  })
}

export function playResultSound(success: boolean): void {
  const ctx = context()
  if (!ctx) return
  if (success) {
    tone(ctx, 523, 0, 0.18, 0.06)
    tone(ctx, 659, 0.11, 0.22, 0.065)
    tone(ctx, 784, 0.23, 0.32, 0.07)
  } else {
    tone(ctx, 220, 0, 0.2, 0.055, 'triangle')
    tone(ctx, 165, 0.16, 0.3, 0.06, 'triangle')
  }
}

export function playCoinDropSound(): void {
  const ctx = context()
  if (!ctx) return
  tone(ctx, 980, 0, 0.1, 0.045, 'triangle')
  tone(ctx, 1320, 0.07, 0.16, 0.04, 'sine')
  tone(ctx, 760, 0.18, 0.2, 0.03, 'triangle')
}

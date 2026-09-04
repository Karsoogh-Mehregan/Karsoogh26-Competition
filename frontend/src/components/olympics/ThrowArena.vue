<script setup lang="ts">
import { RotateCcwIcon } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import type { OlympicsMiniGame, OlympicsScoringZone } from '@/types/api'

type PlayerIndex = 0 | 1
type PieceState = 'ready' | 'moving' | 'stopped' | 'fallen'
interface Piece {
  id: number
  player: PlayerIndex
  attempt: number
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  state: PieceState
  score: number
}
interface PointSample { x: number; y: number; time: number }
interface ThrowResult {
  mode: OlympicsMiniGame
  outcome?: 'player_one' | 'player_two' | 'tie'
  distances?: [number, number]
  attempts?: [number[], number[]]
  playerDistance?: number
  playerAttempts?: number[]
}

const props = withDefaults(defineProps<{
  mode: OlympicsMiniGame
  playerNames: [string, string]
  playerColors: [string, string]
  scoringZones?: OlympicsScoringZone[]
  attemptsPerPlayer?: number
  playerOnlyIndex?: number | null
  disabled?: boolean
}>(), { scoringZones: () => [], attemptsPerPlayer: 0, playerOnlyIndex: null, disabled: false })

const emit = defineEmits<{ complete: [result: ThrowResult] }>()
const canvas = ref<HTMLCanvasElement | null>(null)
const pieces = ref<Piece[]>([])
const turnIndex = ref(0)
const dragging = ref(false)
const finished = ref(false)
// A fixed world keeps gesture strength, collision geometry and distances fair across devices.
const fieldWidth = ref(600)
const fieldHeight = ref(600)
let samples: PointSample[] = []
let animationFrame = 0
let previousFrame = 0
let resizeObserver: ResizeObserver | null = null

const throwCount = computed(() => props.attemptsPerPlayer || (props.mode === 'coin_near_wall' ? 3 : 4))
const soloPlayer = computed<PlayerIndex | null>(() => props.playerOnlyIndex === 0 || props.playerOnlyIndex === 1 ? props.playerOnlyIndex : null)
const totalTurns = computed(() => throwCount.value * (soloPlayer.value == null ? 2 : 1))
const activePlayer = computed<PlayerIndex>(() => soloPlayer.value ?? (turnIndex.value % 2) as PlayerIndex)
const activeAttempt = computed(() => soloPlayer.value == null ? Math.floor(turnIndex.value / 2) : turnIndex.value)
const activeName = computed(() => props.playerNames[activePlayer.value])

function startPosition(player: PlayerIndex): { x: number; y: number } {
  return {
    x: fieldWidth.value * (player === 0 ? 0.38 : 0.62),
    y: fieldHeight.value * 0.87,
  }
}

function reset(): void {
  cancelAnimationFrame(animationFrame)
  pieces.value = []
  turnIndex.value = 0
  dragging.value = false
  finished.value = false
  spawnActivePiece()
  draw()
}

function spawnActivePiece(): void {
  if (turnIndex.value >= totalTurns.value) return
  const player = activePlayer.value
  const position = startPosition(player)
  pieces.value.push({
    id: turnIndex.value,
    player,
    attempt: activeAttempt.value,
    x: position.x,
    y: position.y,
    vx: 0,
    vy: 0,
    radius: props.mode === 'coin_near_wall' ? 17 : 12,
    state: 'ready',
    score: 0,
  })
}

function currentPiece(): Piece | undefined {
  return pieces.value.find((piece) => piece.id === turnIndex.value && piece.state === 'ready')
}

function pointerPoint(event: PointerEvent): PointSample | null {
  const element = canvas.value
  if (!element) return null
  const rect = element.getBoundingClientRect()
  return {
    x: (event.clientX - rect.left) * fieldWidth.value / rect.width,
    y: (event.clientY - rect.top) * fieldHeight.value / rect.height,
    time: performance.now(),
  }
}

function onPointerDown(event: PointerEvent): void {
  if (props.disabled || finished.value) return
  const point = pointerPoint(event)
  const piece = currentPiece()
  if (!point || !piece || Math.hypot(point.x - piece.x, point.y - piece.y) > piece.radius * 2) return
  dragging.value = true
  samples = [point]
  canvas.value?.setPointerCapture(event.pointerId)
}

function onPointerMove(event: PointerEvent): void {
  if (!dragging.value) return
  const point = pointerPoint(event)
  const piece = currentPiece()
  if (!point || !piece) return
  piece.x = Math.max(piece.radius, Math.min(fieldWidth.value - piece.radius, point.x))
  piece.y = Math.max(fieldHeight.value * 0.75 + piece.radius, Math.min(fieldHeight.value - piece.radius, point.y))
  samples.push({ ...point, x: piece.x, y: piece.y })
  if (samples.length > 6) samples.shift()
  draw()
}

function onPointerUp(event: PointerEvent): void {
  if (!dragging.value) return
  dragging.value = false
  canvas.value?.releasePointerCapture(event.pointerId)
  const piece = currentPiece()
  if (!piece) return
  const recent = samples.slice(-4)
  const first = recent[0]
  const last = recent.at(-1)
  if (!first || !last) return
  const seconds = Math.max(0.016, (last.time - first.time) / 1000)
  const vx = (last.x - first.x) / seconds
  const vy = (last.y - first.y) / seconds
  const previous = recent.length > 2 ? recent[recent.length - 2] : first
  const previousSeconds = Math.max(0.016, (last.time - previous!.time) / 1000)
  const previousVx = (last.x - previous!.x) / previousSeconds
  const previousVy = (last.y - previous!.y) / previousSeconds
  piece.vx = clamp(vx * 0.72 + (vx - previousVx) * 0.18, -1250, 1250)
  piece.vy = clamp(vy * 0.72 + (vy - previousVy) * 0.18, -1450, 900)
  if (Math.hypot(piece.vx, piece.vy) < 90) {
    const position = startPosition(piece.player)
    piece.x = position.x
    piece.y = position.y
    draw()
    return
  }
  piece.state = 'moving'
  previousFrame = performance.now()
  animationFrame = requestAnimationFrame(tick)
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value))
}

function tick(time: number): void {
  const dt = Math.min(0.025, Math.max(0.001, (time - previousFrame) / 1000))
  previousFrame = time
  for (const piece of pieces.value) {
    if (piece.state !== 'moving') continue
    piece.x += piece.vx * dt
    piece.y += piece.vy * dt
    const drag = Math.pow(props.mode === 'coin_near_wall' ? 0.974 : 0.967, dt * 60)
    piece.vx *= drag
    piece.vy *= drag
    handleEdges(piece)
    if (piece.state === 'moving' && Math.hypot(piece.vx, piece.vy) < 12) {
      piece.vx = 0
      piece.vy = 0
      piece.state = 'stopped'
    }
  }
  resolveCollisions()
  draw()
  if (pieces.value.some((piece) => piece.state === 'moving')) {
    animationFrame = requestAnimationFrame(tick)
  } else {
    finishTurn()
  }
}

function handleEdges(piece: Piece): void {
  const margin = piece.radius * 1.4
  if (props.mode === 'coin_near_wall') {
    const wallY = 34
    if (piece.y - piece.radius < wallY && piece.vy < 0) {
      piece.y = wallY + piece.radius
      piece.vy = Math.abs(piece.vy) * 0.48
      piece.vx *= 0.78
    }
    if (piece.x < -margin || piece.x > fieldWidth.value + margin || piece.y > fieldHeight.value + margin) piece.state = 'fallen'
  } else if (piece.x < -margin || piece.x > fieldWidth.value + margin || piece.y < -margin || piece.y > fieldHeight.value + margin) {
    piece.state = 'fallen'
  }
}

function resolveCollisions(): void {
  const live = pieces.value.filter((piece) => piece.state !== 'fallen' && piece.state !== 'ready')
  for (let firstIndex = 0; firstIndex < live.length; firstIndex += 1) {
    for (let secondIndex = firstIndex + 1; secondIndex < live.length; secondIndex += 1) {
      const first = live[firstIndex]!
      const second = live[secondIndex]!
      const dx = second.x - first.x
      const dy = second.y - first.y
      const distance = Math.max(0.01, Math.hypot(dx, dy))
      const minimum = first.radius + second.radius
      if (distance >= minimum) continue
      const nx = dx / distance
      const ny = dy / distance
      const overlap = minimum - distance
      first.x -= nx * overlap * 0.5
      first.y -= ny * overlap * 0.5
      second.x += nx * overlap * 0.5
      second.y += ny * overlap * 0.5
      const relative = (first.vx - second.vx) * nx + (first.vy - second.vy) * ny
      if (relative <= 0) continue
      const impulse = relative * 0.88
      first.vx -= impulse * nx
      first.vy -= impulse * ny
      second.vx += impulse * nx
      second.vy += impulse * ny
      first.state = 'moving'
      second.state = 'moving'
    }
  }
}

function finishTurn(): void {
  const thrown = pieces.value.find((piece) => piece.id === turnIndex.value)
  if (thrown && props.mode === 'marble_target') thrown.score = scoreAt(thrown)
  turnIndex.value += 1
  if (turnIndex.value >= totalTurns.value) {
    finished.value = true
    emitResult()
  } else {
    spawnActivePiece()
  }
  draw()
}

function scoreAt(piece: Piece): number {
  if (piece.state === 'fallen' || !props.scoringZones.length) return 0
  const centerX = fieldWidth.value / 2
  const centerY = fieldHeight.value * 0.39
  const radius = Math.min(fieldWidth.value, fieldHeight.value) * 0.31
  const ratio = Math.hypot(piece.x - centerX, piece.y - centerY) / radius
  if (ratio > 1) return 0
  const index = Math.min(props.scoringZones.length - 1, props.scoringZones.length - 1 - Math.floor(ratio * props.scoringZones.length))
  return props.scoringZones[Math.max(0, index)]?.score ?? 0
}

function emitResult(): void {
  if (props.mode === 'marble_target') {
    const attempts: [number[], number[]] = [[], []]
    for (const piece of pieces.value) attempts[piece.player][piece.attempt] = piece.score
    emit('complete', soloPlayer.value == null
      ? { mode: props.mode, attempts }
      : { mode: props.mode, playerAttempts: attempts[soloPlayer.value] })
    return
  }
  const wallY = 34
  const best = ([0, 1] as PlayerIndex[]).map((player) => {
    const distances = pieces.value
      .filter((piece) => piece.player === player && piece.state !== 'fallen')
      .map((piece) => Math.max(0, piece.y - piece.radius - wallY) / 10)
    return distances.length ? Math.min(...distances) : 9999
  }) as [number, number]
  const rounded: [number, number] = [Number(best[0].toFixed(2)), Number(best[1].toFixed(2))]
  if (soloPlayer.value != null) {
    emit('complete', { mode: props.mode, playerDistance: rounded[soloPlayer.value] })
    return
  }
  const outcome = Math.abs(rounded[0] - rounded[1]) < 0.01 ? 'tie' : rounded[0] < rounded[1] ? 'player_one' : 'player_two'
  emit('complete', { mode: props.mode, distances: rounded, outcome })
}

function resize(): void {
  const element = canvas.value
  if (!element) return
  const rect = element.getBoundingClientRect()
  const dpr = Math.min(2, window.devicePixelRatio || 1)
  element.width = Math.max(1, Math.round(rect.width * dpr))
  element.height = Math.max(1, Math.round(rect.height * dpr))
  draw()
}

function draw(): void {
  const element = canvas.value
  const context = element?.getContext('2d')
  if (!element || !context) return
  context.setTransform(element.width / fieldWidth.value, 0, 0, element.height / fieldHeight.value, 0, 0)
  context.clearRect(0, 0, fieldWidth.value, fieldHeight.value)
  drawField(context)
  for (const piece of pieces.value) drawPiece(context, piece)
}

function drawField(context: CanvasRenderingContext2D): void {
  const width = fieldWidth.value
  const height = fieldHeight.value
  context.fillStyle = '#f8fafc'
  context.fillRect(0, 0, width, height)
  context.strokeStyle = 'rgba(100,116,139,.12)'
  context.setLineDash([2, 12])
  for (let y = 20; y < height; y += 24) {
    context.beginPath(); context.moveTo(0, y); context.lineTo(width, y); context.stroke()
  }
  context.setLineDash([])
  if (props.mode === 'coin_near_wall') {
    context.fillStyle = '#64748b'; context.fillRect(0, 22, width, 12)
    context.fillStyle = '#94a3b8'; context.fillRect(0, 22, width, 4)
  } else {
    const zones = props.scoringZones.length || 1
    const radius = Math.min(width, height) * 0.31
    for (let index = 0; index < zones; index += 1) {
      const ringRadius = radius * ((zones - index) / zones)
      context.beginPath(); context.arc(width / 2, height * 0.39, ringRadius, 0, Math.PI * 2)
      context.fillStyle = `rgba(14,116,144,${0.045 + index * 0.035})`; context.fill()
      context.strokeStyle = 'rgba(14,116,144,.48)'; context.lineWidth = 2; context.stroke()
    }
  }
  context.fillStyle = 'rgba(59,130,246,.075)'
  context.fillRect(0, height * 0.75, width, height * 0.25)
  context.strokeStyle = 'rgba(59,130,246,.4)'
  context.setLineDash([7, 7]); context.beginPath(); context.moveTo(0, height * 0.75); context.lineTo(width, height * 0.75); context.stroke(); context.setLineDash([])
}

function drawPiece(context: CanvasRenderingContext2D, piece: Piece): void {
  if (piece.state === 'fallen') return
  context.save()
  context.shadowColor = 'rgba(15,23,42,.28)'; context.shadowBlur = 10; context.shadowOffsetY = 4
  context.beginPath(); context.arc(piece.x, piece.y, piece.radius, 0, Math.PI * 2)
  const gradient = context.createRadialGradient(piece.x - piece.radius * .35, piece.y - piece.radius * .4, 2, piece.x, piece.y, piece.radius)
  gradient.addColorStop(0, '#fff'); gradient.addColorStop(.18, props.playerColors[piece.player]); gradient.addColorStop(1, '#172033')
  context.fillStyle = gradient; context.fill()
  context.shadowColor = 'transparent'; context.lineWidth = piece.state === 'ready' ? 4 : 2; context.strokeStyle = piece.state === 'ready' ? '#f59e0b' : '#fff'; context.stroke()
  context.restore()
}

watch(() => [props.mode, props.attemptsPerPlayer, props.scoringZones] as const, async () => { await nextTick(); reset() }, { deep: true })
onMounted(() => {
  resizeObserver = new ResizeObserver(resize)
  if (canvas.value) resizeObserver.observe(canvas.value)
  reset()
})
onBeforeUnmount(() => {
  cancelAnimationFrame(animationFrame)
  resizeObserver?.disconnect()
})
</script>

<template>
  <section class="throw-arena" dir="rtl">
    <div class="arena-status">
      <div>
        <p class="text-xs font-bold">{{ finished ? 'پرتاب‌ها کامل شد' : `نوبت ${activeName}` }}</p>
        <p class="text-muted-foreground mt-1 text-[0.65rem]">
          {{ finished ? 'نتیجه آماده ثبت است.' : `مهره را فقط در بخش آبی بکشید و با سرعت رها کنید · پرتاب ${(activeAttempt + 1).toLocaleString('fa-IR')}` }}
        </p>
      </div>
      <Button size="sm" variant="outline" :disabled="disabled || pieces.some((piece) => piece.state === 'moving')" @click="reset"><RotateCcwIcon class="size-3.5" /> شروع دوباره</Button>
    </div>
    <div class="canvas-shell" :class="disabled && 'is-disabled'">
      <canvas ref="canvas" aria-label="زمین تعاملی پرتاب" @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointercancel="onPointerUp" />
      <div v-if="disabled" class="disabled-cover">پرتاب‌های شما ارسال شده‌اند؛ منتظر تأیید نتیجه بمانید.</div>
    </div>
    <div class="player-legend">
      <span v-for="(name, index) in playerNames" :key="name"><i :style="{ background: playerColors[index] }" />{{ name }}</span>
      <span>{{ mode === 'coin_near_wall' ? 'خط بالایی دیوار است' : 'لبه‌ها باز هستند؛ تیله می‌تواند بیرون بیفتد' }}</span>
    </div>
  </section>
</template>

<style scoped>
.throw-arena{display:flex;min-height:24rem;flex:1;flex-direction:column;gap:.65rem}.arena-status{display:flex;align-items:center;justify-content:space-between;gap:1rem}.canvas-shell{position:relative;min-height:21rem;flex:1;overflow:hidden;border:1px solid var(--border);border-radius:1rem;background:#f8fafc;box-shadow:inset 0 1px 16px rgb(15 23 42/.06)}canvas{display:block;width:100%;height:100%;min-height:21rem;cursor:grab;touch-action:none}canvas:active{cursor:grabbing}.disabled-cover{position:absolute;inset:auto 1rem 1rem;z-index:2;padding:.65rem;border-radius:.75rem;background:rgb(15 23 42/.82);color:#fff;text-align:center;font-size:.7rem;backdrop-filter:blur(6px)}.canvas-shell.is-disabled canvas{filter:saturate(.7)}.player-legend{display:flex;flex-wrap:wrap;gap:.45rem 1rem;color:var(--muted-foreground);font-size:.65rem}.player-legend span{display:flex;align-items:center;gap:.35rem}.player-legend i{width:.55rem;height:.55rem;border-radius:999px}@media(max-width:640px){.throw-arena,.canvas-shell,canvas{min-height:23rem}.arena-status{align-items:flex-start}.arena-status button{flex:none}}@media(max-height:780px) and (min-width:1024px){.throw-arena,.canvas-shell,canvas{min-height:18rem}}
</style>

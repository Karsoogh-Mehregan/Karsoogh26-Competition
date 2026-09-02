/**
 * Pan/zoom for the map SVG, driven by its `viewBox`.
 *
 * The viewBox is the camera: moving it pans, shrinking it zooms. Doing it this
 * way instead of a CSS transform keeps strokes, text and hit areas crisp at
 * every zoom level, and lets the map fly to a node in map coordinates.
 *
 * Module-level singleton, like `useGraph()`, so the HUD and the map itself
 * drive one camera.
 */
import { computed, ref, shallowRef } from 'vue'

export interface Box {
  x: number
  y: number
  w: number
  h: number
}

export interface Point {
  x: number
  y: number
}

const MIN_ZOOM = 0.75
const MAX_ZOOM = 16
const WHEEL_STEP = 0.0016
const BUTTON_STEP = 1.45
// Below this the pointer was steady enough to count as a click on a node.
const DRAG_SLOP = 4
const FLY_MS = 480
// Node ids only start appearing once they have room to be read.
export const LABEL_ZOOM = 2.6

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3
}

function clone(box: Box): Box {
  return { x: box.x, y: box.y, w: box.w, h: box.h }
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

function createViewport() {
  const svgEl = shallowRef<SVGSVGElement | null>(null)
  const box = ref<Box>({ x: 0, y: 0, w: 1000, h: 1000 })
  /** The whole-map framing: zoom 1, and what "reset" returns to. */
  const home = ref<Box>({ x: 0, y: 0, w: 1000, h: 1000 })
  const isPanning = ref(false)
  const ready = ref(false)
  /** Rendered size of the svg, so map units can be converted to screen pixels. */
  const pixelWidth = ref(1)

  /** True from the moment a drag passes the slop until the click that ends it. */
  let dragged = false
  let frame = 0
  const pointers = new Map<number, Point>()
  let pinchDistance = 0
  let observer: ResizeObserver | null = null

  const viewBox = computed(
    () => `${box.value.x} ${box.value.y} ${box.value.w} ${box.value.h}`,
  )
  const zoom = computed(() => home.value.w / box.value.w)
  const zoomPercent = computed(() => Math.round(zoom.value * 100))
  const canZoomIn = computed(() => zoom.value < MAX_ZOOM - 0.001)
  const canZoomOut = computed(() => zoom.value > MIN_ZOOM + 0.001)
  const labelsVisible = computed(() => zoom.value >= LABEL_ZOOM)
  /**
   * Map units per screen pixel. Text and hairlines are sized in map units, so
   * multiplying a pixel size by this keeps it the same size on screen at every
   * zoom level. Dividing by `zoom` would not: at zoom 1 the whole 2680-unit map
   * is squeezed into a few hundred pixels, so a unit is already far below 1px.
   */
  const unitsPerPx = computed(() => box.value.w / Math.max(1, pixelWidth.value))

  function aspect(): number {
    const el = svgEl.value
    if (!el) return 1
    const rect = el.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) return 1
    pixelWidth.value = rect.width
    return rect.width / rect.height
  }

  /** Grow a box to the element's aspect ratio so `meet` letterboxing is a no-op. */
  function normalize(target: Box): Box {
    const ratio = aspect()
    const centerX = target.x + target.w / 2
    const centerY = target.y + target.h / 2
    let { w, h } = target
    if (w / h > ratio) {
      h = w / ratio
    } else {
      w = h * ratio
    }
    return { x: centerX - w / 2, y: centerY - h / 2, w, h }
  }

  function cancelFlight() {
    if (frame) {
      cancelAnimationFrame(frame)
      frame = 0
    }
  }

  function apply(target: Box) {
    cancelFlight()
    box.value = target
  }

  /** Animate to `target`; jumps straight there when motion is reduced. */
  function flyTo(target: Box) {
    cancelFlight()
    if (prefersReducedMotion()) {
      box.value = target
      return
    }
    const from = clone(box.value)
    const start = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / FLY_MS)
      const k = easeOutCubic(t)
      box.value = {
        x: from.x + (target.x - from.x) * k,
        y: from.y + (target.y - from.y) * k,
        w: from.w + (target.w - from.w) * k,
        h: from.h + (target.h - from.h) * k,
      }
      frame = t < 1 ? requestAnimationFrame(step) : 0
    }
    frame = requestAnimationFrame(step)
  }

  function toMapPoint(clientX: number, clientY: number): Point | null {
    const el = svgEl.value
    const ctm = el?.getScreenCTM()
    if (!ctm) return null
    const point = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse())
    return { x: point.x, y: point.y }
  }

  /** Scale about a fixed map point, so whatever is under the cursor stays there. */
  function zoomAbout(factor: number, anchor: Point | null) {
    const current = box.value
    const nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom.value * factor))
    const w = home.value.w / nextZoom
    const h = home.value.h / nextZoom
    const pivot = anchor ?? { x: current.x + current.w / 2, y: current.y + current.h / 2 }
    const kx = (pivot.x - current.x) / current.w
    const ky = (pivot.y - current.y) / current.h
    apply({ x: pivot.x - kx * w, y: pivot.y - ky * h, w, h })
  }

  function zoomIn() {
    const current = box.value
    zoomAbout(BUTTON_STEP, { x: current.x + current.w / 2, y: current.y + current.h / 2 })
  }

  function zoomOut() {
    const current = box.value
    zoomAbout(1 / BUTTON_STEP, { x: current.x + current.w / 2, y: current.y + current.h / 2 })
  }

  function reset() {
    flyTo(normalize(home.value))
  }

  /** Frame a set of map points — a team's holdings, or one searched node. */
  function fitTo(points: Point[], padding = 220, maxZoom = 5) {
    if (points.length === 0) return
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (const point of points) {
      minX = Math.min(minX, point.x)
      maxX = Math.max(maxX, point.x)
      minY = Math.min(minY, point.y)
      maxY = Math.max(maxY, point.y)
    }
    const target = normalize({
      x: minX - padding,
      y: minY - padding,
      w: maxX - minX + padding * 2,
      h: maxY - minY + padding * 2,
    })
    // Never fly closer than maxZoom, or a single node fills the screen.
    const tooClose = home.value.w / target.w > maxZoom
    if (tooClose) {
      const w = home.value.w / maxZoom
      const h = home.value.h / maxZoom
      const centerX = target.x + target.w / 2
      const centerY = target.y + target.h / 2
      flyTo(normalize({ x: centerX - w / 2, y: centerY - h / 2, w, h }))
      return
    }
    flyTo(target)
  }

  function focus(point: Point, targetZoom = 4) {
    const level = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, targetZoom))
    const w = home.value.w / level
    const h = home.value.h / level
    flyTo(normalize({ x: point.x - w / 2, y: point.y - h / 2, w, h }))
  }

  function panBy(dxRatio: number, dyRatio: number) {
    const current = box.value
    apply({
      x: current.x + current.w * dxRatio,
      y: current.y + current.h * dyRatio,
      w: current.w,
      h: current.h,
    })
  }

  // ---- input ----------------------------------------------------------------

  function onWheel(event: WheelEvent) {
    event.preventDefault()
    // A trackpad reports lines or pages; normalise so both feel the same.
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 100 : 1
    const factor = Math.exp(-event.deltaY * unit * WHEEL_STEP)
    zoomAbout(factor, toMapPoint(event.clientX, event.clientY))
  }

  function pinchSpan(): number {
    const [a, b] = [...pointers.values()]
    return Math.hypot(a.x - b.x, a.y - b.y)
  }

  function pinchCenter(): Point {
    const [a, b] = [...pointers.values()]
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
  }

  function onPointerDown(event: PointerEvent) {
    if (event.button !== 0 && event.pointerType === 'mouse') return
    cancelFlight()
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
    dragged = false
    if (pointers.size === 2) {
      pinchDistance = pinchSpan()
    }
    isPanning.value = true
    window.addEventListener('pointermove', onPointerMove, { passive: false })
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
  }

  function onPointerMove(event: PointerEvent) {
    const previous = pointers.get(event.pointerId)
    if (!previous) return
    const next = { x: event.clientX, y: event.clientY }

    if (!dragged && Math.hypot(next.x - previous.x, next.y - previous.y) > DRAG_SLOP) {
      dragged = true
    }
    pointers.set(event.pointerId, next)

    if (pointers.size >= 2) {
      const span = pinchSpan()
      if (pinchDistance > 0 && span > 0) {
        dragged = true
        zoomAbout(span / pinchDistance, toMapPoint(pinchCenter().x, pinchCenter().y))
      }
      pinchDistance = span
      return
    }

    // Anchor-follow: put the map point that was grabbed back under the pointer.
    const grabbed = toMapPoint(previous.x, previous.y)
    const now = toMapPoint(next.x, next.y)
    if (!grabbed || !now) return
    const current = box.value
    box.value = {
      x: current.x - (now.x - grabbed.x),
      y: current.y - (now.y - grabbed.y),
      w: current.w,
      h: current.h,
    }
  }

  function onPointerUp(event: PointerEvent) {
    pointers.delete(event.pointerId)
    if (pointers.size < 2) {
      pinchDistance = 0
    }
    if (pointers.size > 0) return
    isPanning.value = false
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    window.removeEventListener('pointercancel', onPointerUp)
    // Let the click that follows this pointerup read `dragged`, then forget it.
    setTimeout(() => {
      dragged = false
    }, 0)
  }

  /** A node click should do nothing if the pointer was actually dragging the map. */
  function consumedByDrag(): boolean {
    return dragged
  }

  function onKeydown(event: KeyboardEvent) {
    const pan = event.shiftKey ? 0.3 : 0.12
    switch (event.key) {
      case '+':
      case '=':
        zoomIn()
        break
      case '-':
      case '_':
        zoomOut()
        break
      case '0':
        reset()
        break
      case 'ArrowLeft':
        panBy(-pan, 0)
        break
      case 'ArrowRight':
        panBy(pan, 0)
        break
      case 'ArrowUp':
        panBy(0, -pan)
        break
      case 'ArrowDown':
        panBy(0, pan)
        break
      default:
        return
    }
    event.preventDefault()
  }

  // ---- lifecycle ------------------------------------------------------------

  function setHome(next: Box) {
    home.value = next
    box.value = normalize(next)
    ready.value = true
  }

  function attach(el: SVGSVGElement | null) {
    detach()
    svgEl.value = el
    if (!el) return
    el.addEventListener('wheel', onWheel, { passive: false })
    el.addEventListener('pointerdown', onPointerDown)
    el.addEventListener('keydown', onKeydown)
    observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width
      if (width) pixelWidth.value = width
      // Keep the framing centred when the pane resizes.
      box.value = normalize(box.value)
    })
    observer.observe(el)
    box.value = normalize(box.value)
  }

  function detach() {
    const el = svgEl.value
    if (el) {
      el.removeEventListener('wheel', onWheel)
      el.removeEventListener('pointerdown', onPointerDown)
      el.removeEventListener('keydown', onKeydown)
    }
    observer?.disconnect()
    observer = null
    cancelFlight()
    pointers.clear()
    isPanning.value = false
    svgEl.value = null
  }

  return {
    viewBox,
    box,
    zoom,
    zoomPercent,
    unitsPerPx,
    labelsVisible,
    canZoomIn,
    canZoomOut,
    isPanning,
    ready,
    attach,
    detach,
    setHome,
    zoomIn,
    zoomOut,
    reset,
    fitTo,
    focus,
    consumedByDrag,
  }
}

let singleton: ReturnType<typeof createViewport> | null = null

export function useMapViewport() {
  if (!singleton) {
    singleton = createViewport()
  }
  return singleton
}

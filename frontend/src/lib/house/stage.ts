/**
 * One WebGL context for the whole session, and zero frames per second while
 * nothing is happening.
 *
 * Three deliberate choices, each fixing a way this kind of panel usually goes
 * wrong:
 *
 * 1. **The stage owns its canvas.** Vue tears its DOM down on every route
 *    change; a renderer bound to a destroyed canvas is dead. So the canvas is
 *    created here once and merely *re-parented* into whatever container is
 *    mounted. Browsers cap live WebGL contexts (Chrome allows 16) and silently
 *    drop the oldest, so building one per open is a bug on a timer.
 *
 * 2. **Render on demand.** No standing `requestAnimationFrame` loop. A frame is
 *    scheduled when something actually changes — a repaint, a drag, a resize,
 *    an entry tween — and the loop stops itself the moment the tween ends. An
 *    idle panel costs nothing, which on a laptop running a three-hour contest
 *    is the difference between a warm fan and a flat battery.
 *
 * 3. **Suspend when unseen.** A hidden tab or a closed panel schedules nothing
 *    at all.
 */
import {
  AmbientLight,
  Color,
  DirectionalLight,
  Group,
  HemisphereLight,
  OrthographicCamera,
  Scene,
  WebGLRenderer,
} from 'three'

import { buildHouse, disposeHouse, type HouseHandle } from './build'
import type { HouseSpec } from './spec'

/** True isometric: equal foreshortening on all three axes. */
const ISO_YAW = Math.PI / 4
const CAMERA_DISTANCE = 24
const ENTRY_MS = 620
const MIN_PITCH = 0.12
const MAX_PITCH = 1.35

export interface StageStats {
  drawCalls: number
  triangles: number
  geometries: number
  textures: number
  programs: number
}

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

function createStage() {
  const canvas = document.createElement('canvas')
  canvas.style.display = 'block'
  canvas.style.width = '100%'
  canvas.style.height = '100%'
  canvas.style.touchAction = 'none'
  canvas.setAttribute('role', 'img')

  let renderer: WebGLRenderer | null = null
  const scene = new Scene()
  scene.background = null

  const camera = new OrthographicCamera(-3, 3, 3, -3, 0.1, 200)

  const pivot = new Group()
  scene.add(pivot)

  scene.add(new HemisphereLight(0xfff2df, 0x7c6a58, 1.05))
  scene.add(new AmbientLight(0xffffff, 0.18))
  const key = new DirectionalLight(0xfff6e8, 0.9)
  key.position.set(4, 7, 5)
  scene.add(key)
  const fill = new DirectionalLight(0xbcd2e8, 0.28)
  fill.position.set(-5, 2, -4)
  scene.add(fill)

  let house: HouseHandle | null = null
  let structureKey = ''
  let modelHeight = 4

  let yaw = ISO_YAW
  let pitch = 0.62
  let entryFrom = 0
  let entryStart = 0
  let entering = false

  let frame = 0
  let suspended = true
  let width = 1
  let height = 1

  // ---- camera ---------------------------------------------------------------

  function placeCamera() {
    const centre = modelHeight * 0.42
    camera.position.set(
      Math.sin(yaw) * Math.cos(pitch) * CAMERA_DISTANCE,
      Math.sin(pitch) * CAMERA_DISTANCE,
      Math.cos(yaw) * Math.cos(pitch) * CAMERA_DISTANCE,
    )
    camera.lookAt(0, centre, 0)
  }

  function frameCamera() {
    // Fit the tallest thing on screen with a little air, then let the aspect
    // ratio widen the frustum rather than scaling the model.
    const span = Math.max(modelHeight + 1.4, 4.5)
    const aspect = width / Math.max(1, height)
    camera.top = span / 2
    camera.bottom = -span / 2
    camera.left = (-span * aspect) / 2
    camera.right = (span * aspect) / 2
    camera.updateProjectionMatrix()
  }

  // ---- the frame pump -------------------------------------------------------

  function step(now: number): boolean {
    if (!entering) return false
    const t = Math.min(1, (now - entryStart) / ENTRY_MS)
    const k = easeOutCubic(t)
    pivot.rotation.y = entryFrom + (0 - entryFrom) * k
    pivot.position.y = (1 - k) * -0.45
    if (t >= 1) {
      entering = false
      pivot.rotation.y = 0
      pivot.position.y = 0
      return false
    }
    return true
  }

  function tick(now: number) {
    frame = 0
    const animating = step(now)
    placeCamera()
    renderer?.render(scene, camera)
    if (animating) frame = requestAnimationFrame(tick)
  }

  function invalidate() {
    if (suspended || renderer === null) return
    if (frame === 0) frame = requestAnimationFrame(tick)
  }

  // ---- input ----------------------------------------------------------------

  let pointerId: number | null = null
  let lastX = 0
  let lastY = 0

  function onPointerDown(event: PointerEvent) {
    if (pointerId !== null) return
    pointerId = event.pointerId
    lastX = event.clientX
    lastY = event.clientY
    canvas.setPointerCapture(event.pointerId)
    entering = false
    pivot.rotation.y = 0
    pivot.position.y = 0
  }

  function onPointerMove(event: PointerEvent) {
    if (pointerId !== event.pointerId) return
    yaw -= (event.clientX - lastX) * 0.011
    pitch = Math.min(MAX_PITCH, Math.max(MIN_PITCH, pitch + (event.clientY - lastY) * 0.006))
    lastX = event.clientX
    lastY = event.clientY
    invalidate()
  }

  function releaseDrag() {
    if (pointerId === null) return
    if (canvas.hasPointerCapture(pointerId)) {
      canvas.releasePointerCapture(pointerId)
    }
    pointerId = null
  }

  function onPointerUp(event: PointerEvent) {
    if (pointerId !== event.pointerId) return
    releaseDrag()
  }

  canvas.addEventListener('pointerdown', onPointerDown)
  canvas.addEventListener('pointermove', onPointerMove)
  canvas.addEventListener('pointerup', onPointerUp)
  canvas.addEventListener('pointercancel', onPointerUp)

  canvas.addEventListener('webglcontextlost', (event) => {
    event.preventDefault()
    if (frame !== 0) {
      cancelAnimationFrame(frame)
      frame = 0
    }
  })
  canvas.addEventListener('webglcontextrestored', () => {
    structureKey = ''
    invalidate()
  })

  function onVisibility() {
    if (document.hidden) {
      if (frame !== 0) {
        cancelAnimationFrame(frame)
        frame = 0
      }
    } else {
      invalidate()
    }
  }
  document.addEventListener('visibilitychange', onVisibility)

  // ---- public surface -------------------------------------------------------

  function ensureRenderer() {
    if (renderer !== null) return renderer
    renderer = new WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
      powerPreference: 'low-power',
    })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.setClearColor(new Color(0x000000), 0)
    return renderer
  }

  return {
    canvas,

    /** Re-parent the one long-lived canvas into a freshly mounted container. */
    mount(container: HTMLElement) {
      ensureRenderer()
      if (canvas.parentElement !== container) {
        container.appendChild(canvas)
      }
      suspended = false
      invalidate()
    },

    unmount() {
      suspended = true
      if (frame !== 0) {
        cancelAnimationFrame(frame)
        frame = 0
      }
      releaseDrag()
      canvas.remove()
    },

    resize(nextWidth: number, nextHeight: number) {
      if (nextWidth < 1 || nextHeight < 1) return
      if (nextWidth === width && nextHeight === height) return
      width = nextWidth
      height = nextHeight
      ensureRenderer().setSize(width, height, false)
      frameCamera()
      invalidate()
    },

    /**
     * The hot path. A spec whose `structureKey` matches the standing model is
     * painted in place; anything else rebuilds. On a live board the first
     * branch is taken far more often than the second.
     */
    setSpec(spec: HouseSpec | null) {
      if (spec === null) {
        if (house) {
          pivot.remove(house.group)
          disposeHouse(house)
          house = null
          structureKey = ''
        }
        invalidate()
        return
      }

      if (house !== null && structureKey === spec.structureKey) {
        house.paint(spec)
        invalidate()
        return
      }

      if (house !== null) {
        pivot.remove(house.group)
        disposeHouse(house)
      }
      house = buildHouse(spec)
      structureKey = spec.structureKey
      modelHeight = house.height
      pivot.add(house.group)
      frameCamera()

      canvas.setAttribute(
        'aria-label',
        `${spec.archetype.label} — خانهٔ ${spec.nodeName} در سطح ${spec.levelLabel}`,
      )

      if (prefersReducedMotion()) {
        pivot.rotation.y = 0
        pivot.position.y = 0
        entering = false
      } else {
        entryFrom = -0.75
        entryStart = performance.now()
        entering = true
      }
      invalidate()
    },

    resetView() {
      yaw = ISO_YAW
      pitch = 0.62
      invalidate()
    },

    stats(): StageStats {
      const info = renderer?.info
      return {
        drawCalls: info?.render.calls ?? 0,
        triangles: info?.render.triangles ?? 0,
        geometries: info?.memory.geometries ?? 0,
        textures: info?.memory.textures ?? 0,
        programs: info?.programs?.length ?? 0,
      }
    },
  }
}

let singleton: ReturnType<typeof createStage> | null = null

/**
 * Module-level singleton, the same shape as `useGraph()` and
 * `useMapViewport()`: one camera, one context, however many components.
 */
export function useHouseStage() {
  singleton ??= createStage()
  return singleton
}

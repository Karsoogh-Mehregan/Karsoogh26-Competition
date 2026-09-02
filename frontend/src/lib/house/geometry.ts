/**
 * Eight geometries, built once, shared by every house for the life of the tab.
 *
 * The trick is that almost nothing needs its own shape: a scaled unit cube is
 * the base, the plinth, a storey, a trim band, a window, a door, a parapet, a
 * crate, a sign and the arms of a hospital cross. Scale lives in the object
 * matrix and costs nothing, so pushing variety into `mesh.scale` instead of
 * into new `BufferGeometry` is what keeps a house at a couple of thousand
 * triangles and keeps rebuilds free of allocation.
 *
 * Nothing here is ever disposed. There are eight of them and they are needed
 * again the moment the player clicks the next node.
 */
import {
  BufferAttribute,
  BufferGeometry,
  CanvasTexture,
  ConeGeometry,
  CylinderGeometry,
  PlaneGeometry,
  SphereGeometry,
  BoxGeometry,
  type Texture,
} from 'three'

export type GeometryKey =
  | 'box'
  | 'cylinder'
  | 'cone'
  | 'pyramid'
  | 'dome'
  | 'sphere'
  | 'prism'
  | 'plane'

const cache = new Map<GeometryKey, BufferGeometry>()

/** A unit triangular prism: 1×1×1, ridge running along +z. */
function makePrism(): BufferGeometry {
  const a = [-0.5, -0.5, -0.5]
  const b = [0.5, -0.5, -0.5]
  const c = [0, 0.5, -0.5]
  const d = [-0.5, -0.5, 0.5]
  const e = [0.5, -0.5, 0.5]
  const f = [0, 0.5, 0.5]

  const triangles = [
    [a, c, b], // gable end, -z
    [d, e, f], // gable end, +z
    [a, d, f], [a, f, c], // left slope
    [b, c, f], [b, f, e], // right slope
    [a, b, e], [a, e, d], // underside
  ]

  const positions = new Float32Array(triangles.length * 9)
  let i = 0
  for (const triangle of triangles) {
    for (const vertex of triangle) {
      positions[i] = vertex[0]
      positions[i + 1] = vertex[1]
      positions[i + 2] = vertex[2]
      i += 3
    }
  }

  const geometry = new BufferGeometry()
  geometry.setAttribute('position', new BufferAttribute(positions, 3))
  geometry.computeVertexNormals()
  return geometry
}

function create(key: GeometryKey): BufferGeometry {
  switch (key) {
    case 'box':
      return new BoxGeometry(1, 1, 1)
    case 'cylinder':
      return new CylinderGeometry(0.5, 0.5, 1, 8)
    case 'cone':
      return new ConeGeometry(0.5, 1, 8)
    case 'pyramid':
      // Four radial segments makes a cone a pyramid; rotate 45° to square it up.
      return new ConeGeometry(0.5, 1, 4)
    case 'dome':
      return new SphereGeometry(0.5, 14, 7, 0, Math.PI * 2, 0, Math.PI / 2)
    case 'sphere':
      return new SphereGeometry(0.5, 10, 8)
    case 'prism':
      return makePrism()
    case 'plane':
      return new PlaneGeometry(1, 1)
  }
}

export function geometry(key: GeometryKey): BufferGeometry {
  let value = cache.get(key)
  if (value === undefined) {
    value = create(key)
    cache.set(key, value)
  }
  return value
}

let shadowTexture: Texture | null = null

/**
 * A blurred blob under the building. One 128px canvas beats a shadow map by a
 * mile here: no depth pass, no second render target, and at this camera angle
 * nobody can tell.
 */
export function contactShadowTexture(): Texture {
  if (shadowTexture !== null) return shadowTexture

  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const context = canvas.getContext('2d')
  if (context) {
    const gradient = context.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
    gradient.addColorStop(0, 'rgba(60, 40, 30, 0.42)')
    gradient.addColorStop(0.55, 'rgba(60, 40, 30, 0.16)')
    gradient.addColorStop(1, 'rgba(60, 40, 30, 0)')
    context.fillStyle = gradient
    context.fillRect(0, 0, size, size)
  }

  shadowTexture = new CanvasTexture(canvas)
  return shadowTexture
}

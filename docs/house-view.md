# The house view — 3D building detail beside the 2D map

Handoff notes for the feature added to `frontend/` on 2026-09-02. Written to be
read cold, by a person or an agent with no memory of the session that built it.

---

## 1. The problem this solves

`frontend/src/data/graph_data.json` is the map: **473 nodes, 780 edges**, laid
out as a six-layer circular graph with baked-in `x`/`y`/`color`/`shape`. The SVG
map draws every node as concentric rings — one ring per capacity slot, filled
with the occupying team's colour.

An earlier attempt replaced those rings with illustrated buildings (the
AI-generated isometric PNGs in `P:\PROJECTS\karsoogh-26-assets\`, ~1.3 MB each,
14 building types). It did not survive contact with 473 nodes.

**The diagnosis was not "wrong asset format", it was "detail at the wrong
scale".** 473 × any detailed illustration is unwinnable in SVG, PNG or WebGL
alike. The fix moves detail off the map entirely:

- The map stays cheap primitives. Untouched.
- Clicking any node opens a side panel that renders **exactly one** building
  in 3D, procedurally, reflecting that node's live state.

Because only one building ever exists, "optimised" stops being about the model
and becomes about three things that actually bite: **bundle weight**, **idle GPU
drain**, and **rebuild churn on every realtime event**. All three are addressed
below.

---

## 2. Core idea: house = chassis + hat + paint

There are no 3D model files. A house is generated from data the board already
has:

| Input | Source | Drives |
|---|---|---|
| `capacity` (1/2/3) | node `type` → level | number of storeys |
| `archetype` | FNV-1a hash of the node code | roof shape, rooftop prop, accent colour, awning |
| per-floor occupancy | `GET /api/teams/` holdings | the colour of each storey |
| `status: reserved` | holding with `grade == null` | scaffolding around that storey |

Fourteen archetypes (bank, bakery, library, observatory, hospital, courthouse,
hotel, restaurant, ice-cream shop, newsstand, school, shop, workshop, tax
office), named after the reference art, plus two specials for `spawn` and `toll`
nodes. The hash is deterministic, so a node looks identical on every client and
across reloads with nothing stored for it.

**Floor 3 is the penthouse.** This matters and is not arbitrary: the backend's
`game/services/mentor.py::grade_attempt` computes `floor = len(ranked) - index`
after sorting best-first, so the highest floor number is the best unit. The
model renders floor N physically highest, so a team promoted by a re-rank
literally moves up the building. The data model and the metaphor already agreed.

---

## 3. The three optimisations

### 3.1 Eight geometries, shared forever

`src/lib/house/geometry.ts` builds **eight** `BufferGeometry` objects lazily,
caches them in a module-level `Map`, and never disposes them.

```
box · cylinder · cone · pyramid · dome · sphere · prism · plane
```

A **scaled unit cube** is the base slab, the plinth, every storey, every trim
band, every window, the door, the parapet, crates, signs, the hospital cross and
the arms of the courthouse scales. Scale lives in the object matrix and costs
nothing, so variety goes into `mesh.scale`, never into new geometry.

`src/lib/house/materials.ts` does the same for materials: a `Map<hex, Material>`
holding at most 48 team colours plus a handful of neutrals, never disposed. Two
floors held by the same team therefore share a material and merge into one draw
call. `flatShading: true` matches the faceted hand-drawn reference style and
costs nothing.

Windows and scaffolding use `InstancedMesh` — ~22 windows collapse to one draw
call.

There are **no shadow maps**. A single 128 px radial-gradient `CanvasTexture` on
a ground plane fakes the contact shadow. At this camera angle nobody can tell,
and it skips an entire depth pass and render target.

### 3.2 Rebuild vs. repaint — the `structureKey`

This is the most important invariant in the feature.

`HouseSpec.structureKey` encodes **only what changes geometry**:

```
`${archetype.key}:${capacity}:${reservedMask}`      e.g. "workshop:3:100"
```

`src/lib/house/stage.ts::setSpec` compares it against the standing model:

- **key matches** → `handle.paint(spec)`, which reassigns material references
  and allocates nothing.
- **key differs** → tear down and `buildHouse(spec)`.

Verified behaviour on one node:

| Board event | key transition | path |
|---|---|---|
| empty → reserved | `…:000` → `…:100` | rebuild (scaffolding is geometry) |
| reserved → graded | `…:100` → `…:000` | rebuild (scaffolding comes down) |
| owned → bought out / duel loss | `…:000` → `…:000` | **paint only** |
| floors re-ranked after a grade | `…:000` → `…:000` | **paint only** |
| any event on an *unrelated* node | unchanged | **paint only** |

That last row is the one that matters at contest scale. Every SSE board frame
invalidates `queryKeys.teams()` (see `composables/useBoardStream.ts`), which
recomputes the spec for the open node too. Almost all such frames concern other
nodes, so the key matches and the cost is one material swap plus one frame.

> **If you change `structureKey`, re-check this table.** Widening it (e.g. to
> include team codes) silently turns every grade in the hall into a geometry
> rebuild.

### 3.3 One context, zero idle frames

`src/lib/house/stage.ts` is a module-level singleton, the same shape as the
existing `useGraph()` and `useMapViewport()`.

- **The stage owns its `<canvas>` element.** Vue destroys component DOM on route
  changes; a `WebGLRenderer` bound to a destroyed canvas is dead. So the canvas
  is created once and *re-parented* into whatever container mounts. Browsers cap
  live WebGL contexts (Chrome: 16) and silently drop the oldest, so creating one
  per panel-open is a bug on a timer.
- **`mount()` / `unmount()`, never `dispose()`.** Closing the panel detaches the
  canvas and cancels any pending frame; the context, geometry pool and material
  pool survive for the next open.
- **Render on demand.** There is no standing `requestAnimationFrame` loop.
  `invalidate()` schedules one frame; `tick()` reschedules only while the entry
  tween is still running. Idle cost is literally zero frames.
- **Suspends** on `visibilitychange` and on unmount.
- Handles `webglcontextlost` / `webglcontextrestored` (clears `structureKey` so
  the next spec forces a rebuild).
- `powerPreference: 'low-power'`, `setPixelRatio(min(dpr, 2))`.

Camera is an `OrthographicCamera` at a true isometric yaw — matches the
reference art and removes perspective distortion. Drag to orbit; `prefers-
reduced-motion` skips the entry tween.

### 3.4 Bundle: three.js is lazy

`HouseCanvas.vue` is the **only** file that imports `three`, and `HousePanel.vue`
pulls it in via `defineAsyncComponent(() => import('./HouseCanvas.vue'))`. Vite
splits it into its own chunk. A mentor who never opens a house, or a team still
on the entry sheet, downloads none of it.

---

## 4. File map

**New — `frontend/src/lib/house/`**

| File | Role |
|---|---|
| `geometry.ts` | The eight cached geometries + the contact-shadow canvas texture |
| `materials.ts` | `Map<hex, Material>` pool, `teamColor()`, `shade()`, palette constants |
| `archetypes.ts` | 14 archetypes + spawn/toll specials; FNV-1a `archetypeFor()` |
| `spec.ts` | `buildSpec(node, holdings)` → `HouseSpec`; owns `structureKey` |
| `build.ts` | `buildHouse(spec)` → `HouseHandle{ group, height, paint() }`; `disposeHouse()` |
| `stage.ts` | The singleton renderer: mount/unmount, resize, setSpec, render-on-demand |

**New — elsewhere**

| File | Role |
|---|---|
| `src/lib/mapLevels.ts` | Shared mirror of the backend's `TYPE_TO_LEVEL` + capacities |
| `src/stores/inspector.ts` | Pinia: which node the panel shows, and the player's intent |
| `src/composables/useHouseSpec.ts` | Inspected node + teams → reactive `HouseSpec` |
| `src/components/HouseCanvas.vue` | The lazy chunk; owns mount/resize/watch lifecycle |
| `src/components/HousePanel.vue` | The column: header, canvas, floor list, action button |

**Modified**

- `src/pages/MapPage.vue` — two-column layout (`GraphView` + `HousePanel`).
- `src/components/GraphView.vue` —
  - `onNodeClick` now calls `inspector.inspect(...)` for **every** node,
    including ones the team can't act on (seeing who holds a building is worth a
    click on its own).
  - The old confirm `<Dialog>` and its `startDuel()` stub were **removed**; the
    action moved into the panel, where you can see the building before
    committing.
  - `slotCount()` now delegates to `capacityForType()` from `lib/mapLevels.ts`.
  - Added an `.is-inspected` blue ring so you can see which node the panel
    belongs to. (Also added the `.search-hit` rule, which was a class applied in
    the template with no CSS behind it.)

**Dependency added:** `three` (+ `@types/three` as a dev dependency).

---

## 5. Data flow

```
graph_data.json (node type)  ─┐
                              ├─► useHouseSpec() ─► HouseSpec ─► HouseCanvas ─► stage.setSpec()
GET /api/teams/ (holdings)   ─┘                                                    │
        ▲                                                                          ├─ key match  → paint()
        └── invalidated by SSE board frames                                        └─ key differs → buildHouse()

GraphView.onNodeClick ─► inspectorStore.inspect(nodeCode, intent, occupancyId?)
```

No new API endpoints and no new fetches. The panel is pure derived state.

### Intent

`GraphView` decides what the player may do, because the adjacency and
entry-sheet rules already live there; duplicating them in the panel is exactly
the kind of thing that drifts apart mid-contest. `HousePanel` only renders the
right button label and calls the matching `useActing()` method.

| Intent | Panel button | Action |
|---|---|---|
| `reserve` | رزرو این خانه | `assignQuestion(nodeCode)` → select attempt → `/solve` |
| `claim_start` | ورود به خانهٔ شروع | `claimStart(nodeCode)` |
| `solve` | رفتن به سؤال | select attempt → `/solve` |
| `entry_gate` | پاسخ به سؤال‌های ورودی | `openEntrySheet()` |
| `view` | *(none)* | — |

`Inspection` is a **discriminated union**, not a struct with a nullable field:
`solve` without the occupancy it means to solve is not a state the panel can act
on, so the type forbids it. `inspect()` carries overloads plus a runtime check,
because the only producer (`GraphView.vue`) is plain untyped JS.

---

## 6. Measured numbers

From the running app (`L6_0`, a hard node with 3 floors — two owned, one
reserved), read out of `renderer.info` and a patched `requestAnimationFrame`:

```
19 draw calls · 584 triangles · 4 GPU geometries · 6 shader programs
0 requestAnimationFrame calls over 3 s idle
1 canvas / 1 WebGL context on the page
```

From `npm run build`:

```
dist/assets/index-*.js         464 kB │ gzip 136 kB   ← main bundle, no three.js
dist/assets/HouseCanvas-*.js   534 kB │ gzip 135 kB   ← lazy, first house only
```

Rolldown warns that both chunks exceed its 500 kB *pre-gzip* default threshold.
That is expected and fine — the split it is asking for is already done.

A dev-only stats readout (`import.meta.env.DEV`) prints draw calls / triangles /
geometries / programs in the canvas corner. It does not ship.

---

## 7. Invariants to preserve

1. **`structureKey` encodes geometry only.** See §3.2.
2. **Never `dispose()` the renderer or the pools** on panel close — `unmount()`
   only. Pooled geometries and materials are meant to outlive every house.
3. **The stage owns the canvas.** Do not let a Vue template create the
   `<canvas>`; `HouseCanvas.vue` supplies an empty container div and the stage
   appends into it.
4. **`three` must stay confined to `HouseCanvas.vue`** and the `lib/house/`
   modules it pulls in. An import from anywhere eagerly loaded drags the whole
   library into the main bundle and silently undoes §3.4.
5. **`lib/mapLevels.ts` mirrors the backend.** If
   `game/management/commands/import_graph.py::TYPE_TO_LEVEL` changes, change it
   here too or the map and the model will disagree about a node's capacity.
6. **Add variety with `mesh.scale`, not new geometry.** A new `BufferGeometry`
   should be a considered decision, not the default way to add a prop.

---

## 8. How to run and verify

```bash
cd backend && uv run manage.py runserver     # :8000
cd frontend && npm run dev                   # :3000
```

Log in as a team, then click any node on the map. The panel is on the
inline-end side (the left, in RTL); it collapses to an icon rail, and under
1024 px it becomes a bottom sheet. Collapse state persists in `localStorage`
under `karsoogh.house-panel-collapsed`.

Three archetypes were confirmed by eye: **کارگاه** (gable roof + crates),
**رصدخانه** (drum + dome + telescope), **بستنی‌فروشی** (gable + cone finial +
awning). The other 11 are untested visually.

To re-check the rebuild/repaint split in the browser console (dev server only,
Vite serves the TS module directly):

```js
const { buildSpec } = await import('/src/lib/house/spec.ts')
const node = { id: 'L6_0', type: 'l6' }
const h = (team, color, slot, floor, grade) => ({
  node_code: 'L6_0', level: 'hard', slot, floor, grade,
  is_spawn: false, color, team_code: team,
})
buildSpec(node, [h('a', '#d92121', 1, 3, 90)]).structureKey   // "workshop:3:000"
buildSpec(node, [h('b', '#21d94d', 1, 3, 90)]).structureKey   // same → paint only
buildSpec(node, [h('a', '#d92121', 1, null, null)]).structureKey // "workshop:3:100" → rebuild
```

---

## 9. Known gaps and follow-ups

- **11 of 14 archetypes are visually untested.** They are built from the same
  primitives as the three that were checked, so the risk is cosmetic
  (intersecting props, floating finials), not structural.
- **No duel or buyout affordance in the panel.** The backend has no endpoint for
  either — `duel_factor`, `buyout_factor`, `Team.last_duel_at`,
  `ReleaseReason.DUEL_LOST` / `BOUGHT_OUT` exist as fields with no service behind
  them. The panel is the natural home for both once they land.
- **House glyphs on the map itself — designed, not built.** The idea: keep the
  concentric rings at low zoom (they encode floors legibly at a glance), and
  above `LABEL_ZOOM` (2.6) swap in a ~6-triangle house silhouette via one SVG
  `<symbol>` + `<use>`. `GraphView` already viewport-culls via `labelledNodes`;
  the same pattern applies, putting 20–40 glyphs on screen instead of 473.
- **`prompts given.txt` in the assets folder is 0 bytes.** Whatever redesign
  prompts were meant to be there never made it.
- The asset PNGs were used as *visual reference only*. Nothing in the shipped
  code loads them.

## 10. Local dev state you may inherit

Three `Occupancy` rows were seeded by hand into `backend/db.sqlite3` on node
`L6_0` (teams `alborz` floor 3 grade 90, `darya` floor 2 grade 60, `homa`
reserved) plus `color` values on those three teams, purely so the paint path had
something to show. The in-app **کنترل بازی → restart** clears all of it
(`game/services/reset.py` resets occupancies, colours and draft order).

Separately: `InfoPanel.vue` uses `<Card>` / `<CardHeader>` / `<CardTitle>` /
`<CardContent>` without importing them, so Vue logs a resolve warning per card on
every render. Pre-existing, unrelated to this feature, being fixed separately.

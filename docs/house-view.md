# The house view — 3D building detail beside the 2D map

Handoff notes for the feature added to `frontend/` on 2026-09-02, and the
neighbourhoods / Designer role layered on it on 2026-09-03. Written to be read
cold, by a person or an agent with no memory of the sessions that built it.

---

## 1. The problem this solves

`frontend/src/data/graph_data.json` is the map: **473 nodes, 780 edges**, laid
out as a six-layer circular graph with baked-in `x`/`y`/`theta`/`shape`. The SVG
map draws every node as concentric rings — one ring per capacity slot, filled
with the occupying team's colour.

An earlier attempt replaced those rings with illustrated buildings (the
AI-generated isometric PNGs in `P:\PROJECTS\karsoogh-26-assets\`, ~1.3 MB each).
It did not survive contact with 473 nodes.

**The diagnosis was not "wrong asset format", it was "detail at the wrong
scale".** 473 × any detailed illustration is unwinnable in SVG, PNG or WebGL
alike. The fix moves detail off the map entirely:

- The map stays cheap primitives, now with a colour wash per neighbourhood and a
  thin ring per node. Still static geometry.
- Clicking any node opens a side panel that renders **exactly one** building
  in 3D, procedurally, reflecting that node's live state.

Because only one building ever exists, "optimised" stops being about the model
and becomes about three things that actually bite: **bundle weight**, **idle GPU
drain**, and **rebuild churn on every realtime event**. All three are addressed
in §3.

---

## 2. Core idea: house = chassis + type + theme + paint

There are no 3D model files. A house is generated from data the board already
has:

| Input | Source | Drives |
|---|---|---|
| `capacity` (1/2/3) | `GET /api/map/design/` node row (falls back to map JSON type) | number of storeys |
| building type | Designer pin, else adjacency-aware assignment (§2.2) | roof, foundation, props, awning |
| neighbourhood theme | `floor(theta / 45)` → sector → `Neighborhood.theme` | palette, sign emblem, one motif around the plot |
| per-floor occupancy | `GET /api/teams/` holdings | the colour of each storey |
| `status: reserved` | holding with `grade == null` | scaffolding around that storey |

**Floor 3 is the penthouse.** The backend's `grade_attempt` computes
`floor = len(ranked) - index` after sorting best-first, so the highest floor
number is the best unit. The model renders floor N physically highest, so a team
promoted by a re-rank literally moves up the building.

### 2.1 Twenty-six building types

`frontend/src/lib/house/archetypes.ts`, keyed identically to
`backend/game/design.py::ARCHETYPES` (which validates Designer pins): mint,
cityhall, bakery, restaurant, school, icecream, newspaper, hotel, caravanserai,
stadium, farm, guardpost, observatory, grocery, dairy, stable, hospital,
courthouse, ministry, mine, trade, industry, sawmill, tailor, smithy, library.
Plus two fixed specials for `spawn` and `toll` plots.

Each is `{ roof, foundation, props[], awning }`:

- **Roofs:** gable · hip · dome · flat · tiered · tower · open.
- **Foundations** (the "unique foundation" ask): slab · stepped · round · piers ·
  walled · mound.
- **Props** (26 kinds, 2–6 primitives each) in `lib/house/props.ts`.

### 2.2 No two neighbours alike

`frontend/src/lib/mapArchetypes.ts` is a greedy graph colouring with 26
colours: nodes in fixed order, each takes the first type in its own hash-rotated
preference list that no already-decided neighbour took. The densest node (an L6:
K8 + three L5s + CENTER) has degree 11, so greedy never fails. Designer pins are
placed first and never moved — a pin wins over the tidiness rule. Deterministic
on (order, adjacency, pins), so every client agrees and nothing is stored;
memoised in `useMapDesign` so it runs once per design change.

### 2.3 Eight sectors, nine themes

The map has eight 45° sectors. Every connectivity group in `generateGraph.mjs`
(L3 → C34 → L4 → C45 → L5 → L6) sits inside one, and with the baked layer
offsets `floor(theta / 45)` puts a team's whole tree in the same slice with no
node on a boundary. So **sector membership is geometry the client computes**
(`lib/mapNeighborhoods.ts`); the server only stores what each sector is called,
which theme it wears, and its 2D colour.

The brief lists nine themes (آبی، قرمز، نارنجی، سبز، زرد، بنفش، سفید، خاکستری،
قهوه‌ای) for "eight neighbourhoods". Resolution: eight sectors, nine themes, the
Designer picks which eight. The seed leaves out **سفید / unbuilt** — the theme
for not having an identity yet.

A theme (`lib/house/themes.ts`) is `{ palette, emblem, motif }`:

| theme | emblem on the sign | motif around the plot |
|---|---|---|
| water | drop | moat ring under the base |
| fire | flame | ember cones on the corners |
| lightning | bolt | standing zigzag + sparks |
| history | lens | broken columns, one fallen |
| sport | dumbbell | dumbbell pillars flanking the door |
| knowledge | book | open books on the ground |
| unbuilt | — | scaffold poles on every corner + a crane |
| tribal | tablet | torches flanking the door + a totem |
| soil | seed | root logs radiating + sprouts |

`palette.wall` is the colour of an *unclaimed* storey; claimed storeys always
wear the team's colour, so a theme never hides who owns what.

> The brief's per-building-per-neighbourhood prose (~90 descriptions) is the
> reference these motifs were chosen from, not a spec each one reproduces.
> Modelling them literally from primitives that still run on a weak laptop was
> judged not worth it; the theme layer is where that fidelity would go.

---

## 3. The three optimisations

### 3.1 Eight geometries, shared forever

`src/lib/house/geometry.ts` builds **eight** `BufferGeometry` objects lazily,
caches them in a module-level `Map`, and never disposes them:

```
box · cylinder · cone · pyramid · dome · sphere · prism · plane
```

A **scaled unit cube** is the base slab, every storey, every trim band, every
window, the door, crates, signs, the hospital cross and the arms of the
courthouse scales. Scale lives in the object matrix and costs nothing, so
variety goes into `mesh.scale`, never into new geometry. Twenty-six types × nine
themes come out of those eight shapes.

`src/lib/house/materials.ts` pools materials by colour (`solid()` for Lambert,
`glass()` for the unlit panes), never disposed. `flatShading: true` matches the
faceted hand-drawn reference style and costs nothing.

Windows and scaffolding use `InstancedMesh`. No shadow maps: one 128 px
radial-gradient `CanvasTexture` on a ground plane fakes the contact shadow.

### 3.2 Rebuild vs. repaint — the `structureKey`

This is the most important invariant in the feature.

`HouseSpec.structureKey` encodes **only what changes geometry**:

```
`${archetype.key}:${theme.key}:${capacity}:${reservedMask}`   e.g. "observatory:water:3:100"
```

`stage.ts::setSpec` compares it against the standing model: **match → `paint()`**
(material reassignment, zero allocation); **differ → rebuild**.

| Board event | key transition | path |
|---|---|---|
| empty → reserved | `…:000` → `…:100` | rebuild (scaffolding is geometry) |
| reserved → graded | `…:100` → `…:000` | rebuild (scaffolding comes down) |
| owned → bought out / duel loss | unchanged | **paint only** |
| floors re-ranked after a grade | unchanged | **paint only** |
| any event on an *unrelated* node | unchanged | **paint only** |
| Designer pins a different type | `observatory:…` → `mint:…` | rebuild (as it should) |

Every SSE board frame invalidates `queryKeys.teams()`, which recomputes the
spec for the open node too. Almost all such frames concern other nodes, so the
key matches and the cost is one material swap plus one frame.

> **If you change `structureKey`, re-check this table.** Widening it (e.g. to
> include team codes) silently turns every grade in the hall into a rebuild.

### 3.3 One context, zero idle frames

`src/lib/house/stage.ts` is a module-level singleton like `useGraph()`.

- **The stage owns its `<canvas>`.** Vue destroys component DOM on route
  changes; a renderer bound to a destroyed canvas is dead. The canvas is created
  once and re-parented into whatever container mounts. Browsers cap live WebGL
  contexts (Chrome: 16) and silently drop the oldest.
- **`mount()` / `unmount()`, never `dispose()`.** Pools survive.
- **Render on demand.** No standing rAF loop; `invalidate()` schedules one
  frame; the loop self-stops after the entry tween. Idle = zero frames.
- **Zoom** (added 2026-09-03): wheel on the canvas and ± buttons scale the
  orthographic frustum, clamped 0.6×–2.6×; reset restores yaw, pitch and zoom.
- Suspends on `visibilitychange`; handles context loss/restore.

### 3.4 Bundle: three.js is lazy

`HouseCanvas.vue` is the **only** file that imports `three`; `HousePanel.vue`
loads it via `defineAsyncComponent`. Vite splits it into its own chunk.

---

## 4. The Designer role

A third permission tier beside mentors and game gods, and deliberately narrower
than both: a Designer changes how the board **looks**, never who holds what or
whether the clock runs.

**Backend** (`game/design.py`, `game/views_design.py`, migrations 0016–0017):

- `game.design_map` permission; `Designers` group seeded; `is_designer` on
  `GET /api/auth/me/`.
- `Neighborhood` rows 0–7: `name`, `theme` (nine choices), `color` (`#rrggbb`).
- `MapDesign` singleton: `road_style` (straight/curved/dashed), `tint_strength`,
  `halo_strength` (0–100).
- `Node.archetype`: a pin, blank = renderer chooses.

| Endpoint | Who | Does |
|---|---|---|
| `GET /api/map/design/` | any logged-in user | settings + 8 neighbourhoods + every node's `{level, capacity, archetype}` |
| `PATCH /api/map/design/` | Designer | any subset of settings; `neighborhoods: [{index, …}]` patched by index |
| `PATCH /api/map/nodes/<code>/` | Designer | `archetype` pin/unpin; `level` move — **409 while any team holds a seat there** |

A write publishes a `map.design` SSE frame; clients invalidate `mapDesign`.

**The level-of-record moved.** Before this, the SVG map derived capacity from
the JSON `type`. Now it reads `GET /api/map/design/` and falls back to the JSON
only until that answers. Otherwise a Designer moving a node between tiers would
change entry cost and capacity on the server while the map kept drawing the old
ring count. `lib/mapLevels.ts` still mirrors `TYPE_TO_LEVEL` as that fallback.

**Frontend:**

- `/design` (`pages/DesignPage.vue`, `requiresDesigner`): road style, the two
  strength sliders, and eight rows of name / theme / colour.
- Per-node pins live in the **house panel**: a Designer sees a "طراحی" block
  under the floor list with a type picker (26 + "خودکار — <what the renderer
  chose>") and a tier picker, the model doubling as live preview. The tier
  picker is disabled while the node is occupied, matching the server's 409.

The shadcn `select` component could not be added (registry unreachable), so
both pickers are native `<select>` styled to match `Input`. Swap them when the
CLI is reachable.

---

## 5. File map

**`frontend/src/lib/house/`**

| File | Role |
|---|---|
| `geometry.ts` | Eight cached geometries + the contact-shadow texture |
| `materials.ts` | Colour-keyed pools: `solid()`, `glass()`, `shade()`, `teamColor()` |
| `archetypes.ts` | 26 building types + spawn/toll; `hashCode()` |
| `themes.ts` | 9 themes: palette, emblem, motif |
| `props.ts` | Foundations, roofs (with `surfaceY`), props, emblems, motifs |
| `spec.ts` | `buildSpec(code, meta, holdings)` → `HouseSpec`; owns `structureKey` |
| `build.ts` | `buildHouse(spec)` → `{ group, height, paint() }`; `disposeHouse()` |
| `stage.ts` | Singleton renderer: mount/unmount, resize, zoom, setSpec, render-on-demand |

**Elsewhere in `frontend/src/`**

| File | Role |
|---|---|
| `lib/mapLevels.ts` | Mirror of the backend's `TYPE_TO_LEVEL`; the fallback before the design query |
| `lib/mapNeighborhoods.ts` | `sectorOf(node)`, `wedgePath()`, `sectorLabelPoint()` |
| `lib/mapArchetypes.ts` | `assignArchetypes()` — the greedy no-two-alike colouring |
| `composables/useMapDesign.ts` | The design query resolved per node: level, capacity, neighbourhood, theme, archetype |
| `composables/useHouseSpec.ts` | Inspected node + design meta + teams → reactive `HouseSpec` |
| `stores/inspector.ts` | Which node the panel shows + the player's intent (discriminated union) |
| `components/HouseCanvas.vue` | The lazy chunk; mount/resize/watch; zoom buttons |
| `components/HousePanel.vue` | Header, canvas, floor list, Designer block, action button |
| `pages/DesignPage.vue` | Map-wide Designer knobs |
| `services/design.ts`, `queries/design.ts` | Transport + TanStack layer for the design API |

**Modified:** `GraphView.vue` (sector wedges + labels, per-node halo, `<path>`
roads with `edgeD()`, capacity from the design query, clicks → inspector, old
confirm dialog removed), `MapPage.vue` (two columns), `router.ts` (`/design`),
`InfoPanel.vue` (nav link), `useBoardStream.ts` (`map.design` route),
`types/api.ts`, `queries/keys.ts`.

**Dependency added:** `three` (+ `@types/three`).

---

## 6. Data flow

```
graph_data.json (theta, type) ─┐
GET /api/map/design/ ──────────┼─► useMapDesign().metaOf(node) ─┐
   (level, pins, neighbourhoods)│                                ├─► buildSpec() ─► HouseCanvas ─► stage.setSpec()
GET /api/teams/ (holdings) ─────┘────────────────────────────────┘                       ├─ key match  → paint()
        ▲                                                                                └─ key differs → buildHouse()
        └── invalidated by SSE: board.* → teams, map.design → mapDesign

GraphView.onNodeClick ─► inspectorStore.inspect(nodeCode, intent, occupancyId?)
```

### Intent

`GraphView` decides what the player may do (adjacency and entry-sheet rules
live there); `HousePanel` only renders the right button and calls the matching
`useActing()` method.

| Intent | Button | Action |
|---|---|---|
| `reserve` | رزرو این خانه | `assignQuestion()` → `/solve` |
| `claim_start` | ورود به خانهٔ شروع | `claimStart()` |
| `solve` | رفتن به سؤال | select attempt → `/solve` |
| `entry_gate` | پاسخ به سؤال‌های ورودی | `openEntrySheet()` |
| `view` | *(none)* | — |

---

## 7. Measured numbers

Live app, `L6_0` pinned to observatory, water theme, three floors (two owned,
one reserved):

```
25 draw calls · 1102 triangles · 6 GPU geometries · 6 shader programs
0 requestAnimationFrame calls while idle
1 canvas / 1 WebGL context on the page
473 halo rings · 8 sector wedges · 780 road paths (static SVG)
```

From `npm run build`:

```
dist/assets/index-*.js         483 kB │ gzip 143 kB   ← main bundle, no three.js
dist/assets/HouseCanvas-*.js   546 kB │ gzip 138 kB   ← lazy, first house only
```

Backend: 285 tests pass (19 new in `tests/test_map_design.py`), ruff clean, no
migration drift.

---

## 8. Invariants to preserve

1. **`structureKey` encodes geometry only.** §3.2.
2. **Never `dispose()` the renderer or the pools** on panel close.
3. **The stage owns the canvas.** `HouseCanvas.vue` supplies a container div.
4. **`three` stays confined to `HouseCanvas.vue` and `lib/house/`.**
5. **Archetype keys are duplicated on purpose** — `backend/game/design.py` and
   `frontend/src/lib/house/archetypes.ts`. Add to both or a pin will 400.
6. **Sector = `floor(theta/45)`.** If `generateGraph.mjs` ever changes layer
   offsets, re-check that no node lands on a 45° boundary.
7. **Roof-mounted props ask `roof.surfaceY(x, z)`.** That is what fixed the
   floating chimney. A new prop should never guess a height.
8. **Add variety with `mesh.scale`, not new geometry.**

---

## 9. How to run and verify

```bash
cd backend && uv run manage.py migrate && uv run manage.py runserver   # :8000
cd frontend && npm run dev                                             # :3000
```

Make a Designer: add a user to the `Designers` group in admin (or
`user.groups.add(Group.objects.get(name="Designers"))`). Log in, open `/design`
for the map-wide knobs, click any node on the map for the per-node pin.

Verified by eye: observatory (water), newspaper (water), and the three from the
first session under the old flat palette. The other types and themes are built
from the same primitives; risk is cosmetic (a prop intersecting a roof edge),
not structural.

**Known quirk, pre-existing:** the very first click on a node after a full page
load sometimes does not register (the map's drag-slop guard); the second always
does. Not introduced by this work; worth a look in `useMapViewport.ts`.

Rebuild/repaint check in the dev console:

```js
const { buildSpec } = await import('/src/lib/house/spec.ts')
const { THEMES } = await import('/src/lib/house/themes.ts')
const { ARCHETYPES } = await import('/src/lib/house/archetypes.ts')
const meta = { level: 'hard', capacity: 3, archetype: ARCHETYPES[0], theme: THEMES.water, neighborhoodName: '' }
const h = (team, color, slot, floor, grade) => ({ node_code: 'L6_0', level: 'hard', slot, floor, grade, is_spawn: false, color, team_code: team })
buildSpec('L6_0', meta, [h('a', '#d92121', 1, 3, 90)]).structureKey     // "mint:water:3:000"
buildSpec('L6_0', meta, [h('b', '#21d94d', 1, 3, 90)]).structureKey     // same → paint only
buildSpec('L6_0', meta, [h('a', '#d92121', 1, null, null)]).structureKey // "mint:water:3:100" → rebuild
```

---

## 10. Known gaps and follow-ups

- **Per-building-per-theme prose is not modelled.** See §2.3. The theme layer
  is where to add fidelity: e.g. a `water` observatory could swap its dome for a
  glass one by checking `spec.theme.key` inside `buildRoof`.
- **No duel or buyout affordance.** The backend has no endpoint for either.
- **Road style is global.** The brief describes per-neighbourhood road
  character (zigzag for lightning, cobbles for history…). `edgeD()` already has
  both endpoints; a per-sector style is a `sectorOf(a)` lookup away.
- **House glyphs on the map itself — still not built.** Keep rings at low zoom;
  above `LABEL_ZOOM` swap in a `<symbol>`/`<use>` silhouette, viewport-culled
  like `labelledNodes`.
- **`prompts given.txt` in the assets folder is 0 bytes.**

## 11. Local dev state you may inherit

`backend/db.sqlite3` on this machine has: a `designer` / `demo1234` login in
the `Designers` group; `L6_0` pinned to `observatory`; road style set to
`curved`; three seeded `Occupancy` rows on `L6_0` (البرز floor 3, دریا floor 2,
هما reserved) with colours on those teams. **کنترل بازی → restart** clears the
occupancies and colours; the pin and road style are design data and survive a
restart by design — change them on `/design` or in admin.

`InfoPanel.vue` was missing its `Card` imports (Vue resolve warnings on every
render); that was being fixed in a separate session.

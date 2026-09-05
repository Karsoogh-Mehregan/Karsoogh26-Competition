# The house view — 3D building detail beside the 2D map

Handoff notes for the feature added to `frontend/` on 2026-09-02, the
neighbourhoods / Designer role layered on it on 2026-09-03, and the same-day
rework that gave every building type its own massing. Written to be read cold,
by a person or an agent with no memory of the sessions that built it.

---

## 1. The problem this solves

`frontend/src/data/graph_data.json` is the map: **473 nodes, 780 edges**, laid
out as a six-layer circular graph with baked-in `x`/`y`/`theta`/`r`/`shape`.
The SVG map draws every node as concentric rings — one ring per capacity slot,
filled with the occupying team's colour.

An earlier attempt replaced those rings with illustrated buildings (the
AI-generated isometric PNGs in `P:\PROJECTS\karsoogh-26-assets\`, ~1.3 MB each).
It did not survive contact with 473 nodes.

**The diagnosis was not "wrong asset format", it was "detail at the wrong
scale".** The fix moves detail off the map entirely:

- The map stays cheap primitives, with a colour wash per neighbourhood, a
  wandering border between them, and a thin ring per node. Static geometry.
- Clicking any node opens a side panel that renders **exactly one** building
  in 3D, procedurally, reflecting that node's live state.

Because only one building ever exists, "optimised" is about **bundle weight**,
**idle GPU drain**, and **rebuild churn on realtime events** — §4.

---

## 2. Core idea: every type has its own massing; every theme has a character

There are no 3D model files. A house is generated from data the board already
has:

| Input | Source | Drives |
|---|---|---|
| `capacity` (1/2/3) | `GET /api/map/design/` node row (falls back to map JSON type) | number of paintable storeys |
| building type | Designer pin, else adjacency-aware assignment (§2.2) | the whole plot layout — see §2.1 |
| neighbourhood theme | `floor(theta / 45)` → sector → `Neighborhood.theme` | palette, sign emblem, one motif around the plot |
| per-floor occupancy | `GET /api/teams/` holdings | the colour of each storey |
| `status: reserved` | holding with `grade == null` | scaffolding around that storey |

**Floor N is the penthouse.** The backend's `grade_attempt` computes
`floor = len(ranked) - index` after sorting best-first; the model renders floor
N physically highest (or outermost, for a stadium), so a promoted team moves up.

### 2.1 Twenty-six building types, each its own builder

`frontend/src/lib/house/buildings.ts` holds one builder per type. A builder
lays out its plot from scratch — this is the change from the first cut, which
gave every type the same box stack and a different hat. Now:

| type | what the plot actually is |
|---|---|
| farm | a fenced field of twelve plots with crop rows **in front**, a small farmhouse at the back, a windmill, a scarecrow |
| stadium | a green pitch with goals and pitch markings; the storeys are **tiers of bleachers** on both long sides; four floodlights |
| caravanserai | a walled courtyard: each storey is a **ring of arcade rooms**, corner domes, an arched gate, a fountain |
| mine | a mound with a timbered tunnel mouth, a headframe with a wheel, rails, an ore cart, ore piles, an office shack |
| observatory | a round tower of drums with ring windows, a slit dome and telescope, a spiral of steps, an annex |
| guardpost | a battlemented wall with a gate arch; the storeys are the **watchtower** rising through it |
| dairy / stable | barn + silo + paddock with cows; long barn with stall doors + paddock with horses and hay |
| courthouse / library / ministry | colonnades, steps, pediments, domes, a great open book, wings and a central tower |
| mint | heavy stepped stone blocks, a giant coin over the door, a press on the roof, coin stacks |
| hotel | a tall narrow tower with a balcony on every floor and an entrance canopy |
| toll (عوارضی) | a **road through the plot** with a dashed centre line, a booth, a striped barrier arm, an overhead gantry with a sign |
| spawn | a pavilion whose base **and flag** wear the team colour |
| center (مرکز شهر) | the city hall on the one `CENTER` node — see §2.4 |
| bakery, restaurant, school, icecream, newspaper, grocery, hospital, trade, industry, sawmill, tailor, smithy | each with its own trade props: oven and bread, terrace and umbrellas, bell tower and flagpole, cone roof and scoop, sawtooth roof and billboard, produce stand, ambulance canopy and helipad, loading dock and crane, smokestacks and gear, saw bench and log piles, mannequin and fabric rolls, forge and anvil |

Two rules hold across all of them:

1. **Every type registers exactly `capacity` paintable storeys** through
   `Ctx.storey()`, whatever a storey means for it (a bleacher tier, a ring of
   rooms, a tower drum). That is what `paint()` colours and what the scaffolding
   stands around.
2. **Everything is the eight pooled geometries, scaled** — cows, cranes and
   windmills included (§4.1).

Reference for the massing came from isometric low-poly farm packs (barn, silo,
fields, fence, windmill as separate props), e.g. the
[Synty POLYGON Farm Pack](https://syntystore.com/products/polygon-farm-pack),
the [Low-poly Isometric Farm on CGTrader](https://www.cgtrader.com/3d-models/exterior/house/low-poly-isometric-farm-1)
and the [stylized windmill on OpenGameArt](https://opengameart.org/content/stylized-wildmill-isometric-with-parts-to-build-animationand-blend).

### 2.2 No two neighbours alike

`lib/mapArchetypes.ts`: greedy graph colouring with 26 colours, nodes in
fixed order, each taking the first type in its own hash-rotated preference list
that no decided neighbour took. The densest node has degree 11. Designer pins
are placed first and never moved. Deterministic; memoised in `useMapDesign`.

### 2.3 Eight sectors, nine themes, each a character

Sector membership is exact: `floor(theta / 45)`. Every connectivity group in
`generateGraph.mjs` sits inside one, no node on a boundary. The brief lists
nine themes for eight neighbourhoods; the Designer picks which eight, and the
seed leaves out **سفید / unbuilt**.

Each theme carries the feel of the character who wears its colour in the story
(`karsoogh-mehregan-characters.md`), through its motif on the plot:

| theme | character | palette feel | motif around the plot |
|---|---|---|---|
| water | سورگیلش the well-digger | cool blues | a stone **well** with posts, roof and bucket |
| fire | غرگیله, angular and anxious | red, dark | **spiked** finials on every corner, embers at their feet |
| lightning | فرگوله the explorer | amber, orange | a **compass rose** on the ground, a bolt-topped signpost |
| history | — | olive, stone | ruins: broken columns, one fallen |
| sport | هوگیلا, sun-shaped and calm | golden yellow | a **sun** on a pole with rays, a bow beneath |
| knowledge | گیسپلی the scribe | violet | a **lectern** with an open scroll and a quill |
| unbuilt | گیلبیب the king | greys, one gold | a site: scaffold poles, a crane, **one royal flag** |
| tribal | فینگیل, the only grey one | stone grey, dark violet | torches, a totem, his floating **halo** above it |
| soil | گلمری the elder farmer | earth browns | roots, sprouts, and his **cane and satchel** by the gate |

`palette.wall` is the colour of an *unclaimed* storey; claimed storeys always
wear the team's colour.

### 2.4 The centre: three storeys, two colonnades, eight neighbourhoods

The `CENTER` node is the `center` tier's only member and gets a fixed building,
the way spawn and toll do: `CENTER_ARCHETYPE` in `archetypes.ts`, returned for
the level whatever a Designer pinned, and skipped by the assignment in
`lib/mapArchetypes.ts`. The panel hides the type picker for it.

The massing follows the brief literally — a square stone city hall: a tall
ground storey with a pointed-arch portal and steps, then an **open colonnade of
eight columns**, a second storey, a second colonnade, a third storey, a flat
roof. The three storeys are the three seats (`Ctx.storey()` as everywhere, so
paint and scaffolding work unchanged).

The eight columns are the eight neighbourhoods. Column *k* stands on the
colonnade's square at the bearing of sector *k*'s bisector on the map
(`22.5° + 45°·k`, with the map's theta mapped to the model as `x = cos θ`,
`z = -sin θ`), which puts two on every side, each pair facing the pair across
the floor, and it wears that neighbourhood's `Neighborhood.color`. So the
building is a compass of the city: the blue column points at the blue quarter.
Those colours arrive on the spec as `neighborhoodColors` (from
`useMapDesign().neighborhoods`) and are applied in `paint()`, through
`Built.sectorParts` — a Designer recolouring a neighbourhood repaints the
column without a rebuild, and `structureKey` is untouched.

Two small departures from the shared chassis, both flags on `Built`: the walls
and cornices are fixed ivory stone (`emptyWall`) rather than the sector-0 theme
the node technically sits in, because the centre belongs to everyone; and the
neighbourhood motif is skipped (`dressing = false`) for the same reason.
Windows and the portal are pointed arches built from a box plus a four-sided
cone squashed flat — square-on it is a triangle — and every repeated piece
(window kits, pilasters, corner piers, column plinths, rings and capitals) goes
through `Ctx.instances()`, so the whole building is ~85 draw calls despite its
size; only the sixteen shafts are individual meshes, because each wears its own
paint.

---

## 3. The 2D map

- **Sector wash.** Eight paths behind everything, `fill-opacity = tint_strength`
  (default now **22%**, was 8% — which read as grey) with a stroke along the
  border at double that. Default colours were resaturated for the same reason;
  a guarded data migration (`0018`) only rewrites rows still on the old defaults.
- **Wandering borders.** `lib/mapNeighborhoods.ts::sectorGeometries()` does not
  cut at 45°. On every ring it finds the gap between the last node of one
  sector and the first of the next (1.9° on L1, 45° on L6), takes its midpoint,
  lets the line swing up to 28% of the gap alternating by ring, and threads a
  Catmull-Rom spline through the points. The border therefore hugs the real
  groups and **never crosses a node**. Computed once from the JSON.
- **Halo.** One ring per node in its sector's colour, `halo_strength` opacity
  (default now 60%).
- **Roads.** `<path>` per edge; straight / curved (bowed away from the centre) /
  dashed, from `road_style`.
- **Toll glyph.** `c34`/`c45` nodes draw a gantry `<symbol>` instead of a dot,
  with an invisible disc behind it so the click lands (the symbol has gaps).

---

## 4. The three optimisations

### 4.1 Eight geometries, shared forever

`lib/house/geometry.ts`: `box · cylinder · cone · pyramid · dome · sphere ·
prism · plane`, built once, never disposed. A scaled unit cube is a storey, a
crate, a bleacher, a fence rail, the arms of the courthouse scales. Materials
are pooled by colour in `materials.ts` (`solid()`, `glass()`), `flatShading`
on. Windows and scaffolding are `InstancedMesh`. No shadow maps — one 128 px
radial-gradient plane fakes the contact shadow.

### 4.2 Rebuild vs. repaint — the `structureKey`

`HouseSpec.structureKey` encodes **only what changes geometry**:

```
`${archetype.key}:${theme.key}:${capacity}:${reservedMask}`   e.g. "farm:soil:3:100"
```

`stage.ts::setSpec`: **match → `paint()`** (material reassignment, zero
allocation); **differ → rebuild**. Every SSE board frame recomputes the spec
for the open node; almost all concern other nodes, so the key matches and the
cost is one material swap plus one frame.

> **If you change `structureKey`, re-check this.** Widening it (e.g. team
> codes) silently turns every grade in the hall into a rebuild.

### 4.3 One context, zero idle frames

`lib/house/stage.ts` is a singleton. It owns its `<canvas>` and re-parents it
(Chrome caps live WebGL contexts at 16); `mount()`/`unmount()`, never
`dispose()`; render on demand with no standing rAF loop; **zoom** by wheel and
± buttons (0.6×–2.6×); suspends on `visibilitychange`.

### 4.4 Bundle

`HouseCanvas.vue` is the only importer of `three`, loaded through
`defineAsyncComponent`, so Vite splits it.

---

## 5. The Designer role

A third permission tier, narrower than mentor or game god: it changes how the
board **looks**, never who holds what or whether the clock runs.

**Backend** (`game/design.py`, `game/views_design.py`, migrations 0016–0018):
`game.design_map` permission, `Designers` group, `is_designer` on `/api/auth/me/`;
`Neighborhood` rows 0–7 (`name`, `theme`, `color`); `MapDesign` singleton
(`road_style`, `tint_strength`, `halo_strength`); `Node.archetype` pin.

| Endpoint | Who | Does |
|---|---|---|
| `GET /api/map/design/` | any logged-in user | settings + 8 neighbourhoods + every node's `{level, capacity, archetype}` |
| `PATCH /api/map/design/` | Designer | any subset of settings; `neighborhoods: [{index, …}]` by index |
| `PATCH /api/map/nodes/<code>/` | Designer | `archetype` pin/unpin; `level` move — **409 while any team holds a seat there** |

A write publishes a `map.design` SSE frame. **The level-of-record moved:** the
SVG map now reads level/capacity from this endpoint, with the JSON type only as
the fallback before it answers.

**Frontend:** `/design` for the map-wide knobs (tint slider now goes to 60);
per-node pins in the **house panel** under a "طراحی" block, model as live
preview, tier picker disabled while occupied. Native `<select>`s — the shadcn
registry was unreachable.

---

## 6. The panel

`HousePanel.vue`: **27 rem** wide by default (was 20), stage at least 22 rem
tall (was 12), and an **expand** toggle (persisted) that takes the column to
`min(46rem, 58vw)` with a 34 rem stage. Under 1024 px it is a bottom sheet.

---

## 7. File map

**`frontend/src/lib/house/`**

| File | Role |
|---|---|
| `geometry.ts` | Eight cached geometries + the contact-shadow texture |
| `materials.ts` | Colour-keyed pools: `solid()`, `glass()`, `shade()`, `teamColor()` |
| `archetypes.ts` | 26 types `{roof, foundation, props, awning}` + spawn/toll/center; `hashCode()` |
| `themes.ts` | 9 themes: palette, emblem, motif, character |
| `props.ts` | Footprint-aware foundations and roofs (`surfaceY`), positioned emblem, character motifs, `instancedMesh()` |
| `buildings.ts` | **`Ctx` + one builder per type**; `buildArchetype()` |
| `spec.ts` | `buildSpec(code, meta, holdings)` → `HouseSpec`; owns `structureKey` |
| `build.ts` | Orchestration: builder → windows → motif → scaffolding from floor bounds → `paint()` |
| `stage.ts` | Singleton renderer: mount/unmount, resize, zoom, setSpec, render-on-demand |

**Elsewhere in `frontend/src/`**: `lib/mapLevels.ts` (fallback tiers),
`lib/mapNeighborhoods.ts` (sector + wandering borders), `lib/mapArchetypes.ts`
(assignment), `composables/useMapDesign.ts`, `composables/useHouseSpec.ts`,
`stores/inspector.ts`, `components/HouseCanvas.vue`, `components/HousePanel.vue`,
`pages/DesignPage.vue`, `services/design.ts`, `queries/design.ts`.
`GraphView.vue` carries the wedges, halos, roads, toll glyph and click → inspector.

**Dependency added:** `three` (+ `@types/three`).

---

## 8. Measured numbers

Live app, `L6_0` (hard, three floors: two owned, one reserved), water theme:

| pinned type | draw calls | triangles |
|---|---|---|
| newspaper (auto) | 43 | 840 |
| mine | 53 | 1 298 |
| stable | 69 | 1 272 |
| toll (`C45_0`) | 43 | 610 |

`0` requestAnimationFrame calls while idle · `1` WebGL context · `473` halo rings
· `8` sector paths · `780` road paths (static SVG).

```
dist/assets/index-*.js         485 kB │ gzip 144 kB   ← main bundle, no three.js
dist/assets/HouseCanvas-*.js   568 kB │ gzip 144 kB   ← lazy, first house only
```

Backend: 285 tests pass (19 in `tests/test_map_design.py`), ruff clean, no
migration drift.

---

## 9. Invariants to preserve

1. **`structureKey` encodes geometry only.** §4.2.
2. **Every builder registers `capacity` storeys via `Ctx.storey()`.** Miss one
   and that floor can neither be painted nor scaffolded.
3. **Never `dispose()` the renderer or the pools** on panel close.
4. **The stage owns the canvas.**
5. **`three` stays confined to `HouseCanvas.vue` and `lib/house/`.**
6. **Archetype keys are duplicated on purpose** — `backend/game/design.py` and
   `frontend/src/lib/house/archetypes.ts`. Add to both, and add a builder.
   The three fixed plots (spawn, toll, center) are frontend-only and keyed by
   level, not by pin.
7. **Sector = `floor(theta/45)`; borders come from the real ring gaps.** If
   `generateGraph.mjs` changes layer offsets, re-check `sectorGeometries()`.
8. **Roof-mounted pieces ask `roof.surfaceY(x, z)`.** Never guess a height.
9. **Add variety with `mesh.scale`, not new geometry.**

---

## 10. How to run and verify

```bash
cd backend && uv run manage.py migrate && uv run manage.py runserver   # :8000
cd frontend && npm run dev                                             # :3000
```

Make a Designer (add a user to the `Designers` group). Log in, click any node;
use the "طراحی" picker to walk through all 26 types on one node — the model
rebuilds on save. `/design` for the map-wide knobs.

Verified by eye this round: stable, farm, stadium, caravanserai, mine,
newspaper, toll, plus observatory and newspaper from the round before. The
other types share the same primitives and helpers; risk is cosmetic.

**On clicking nodes from browser automation:** a synthetic click that moves the
pointer *while* the button is down reads as a drag to the map's slop guard and
is dropped, by design. Hover to the node first and the click lands every time.
A real mouse is already at the node when the button goes down, so this does not
affect players.

---

## 11. Known gaps and follow-ups

- **Fence posts are one mesh each.** Stable/dairy/farm reach 60–70 draw calls
  because every post is its own `Mesh`. Still cheap, but an `InstancedMesh`
  for fence posts would halve it. Same for the stadium's floodlights.
- **Per-building-per-theme prose is not modelled.** The theme layer (palette +
  emblem + character motif) is where that fidelity goes; a builder can also
  branch on `c.theme.key` for one-off touches.
- **Road style is global**, not per neighbourhood.
- **House glyphs on the map itself** are still rings; the plan (a `<symbol>`
  silhouette above `LABEL_ZOOM`, viewport-culled) is unchanged.

## 12. Local dev state you may inherit

`backend/db.sqlite3` on this machine: `designer / demo1234` in the `Designers`
group; `L6_0` **unpinned** (back on auto); road style `curved`; three seeded
holdings on `L6_0` (البرز floor 3, دریا floor 2, هما reserved) with colours on
those teams. Sector colours and strengths are on the new defaults via migration
0018. **کنترل بازی → restart** clears the holdings and colours; design data
survives a restart by design.

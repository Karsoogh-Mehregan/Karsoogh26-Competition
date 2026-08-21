# Karsoogh 26 Competition

Platform for the Karsoogh 26 competition.

- `backend/` — Django + DRF API
- `frontend/` — Vite + Vue single-page app

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/) (manages Python 3.13 itself)
and Node 20+.

### Backend

```bash
cd backend
cp .env.example .env
uv run python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
# paste the result into SECRET_KEY in .env

uv sync                          # creates .venv from uv.lock
uv run manage.py migrate
uv run manage.py createsuperuser # optional, for /admin
uv run manage.py runserver
```

API at http://127.0.0.1:8000, Django admin at http://127.0.0.1:8000/admin/.
Swagger UI at http://127.0.0.1:8000/api/docs/ and the raw OpenAPI schema at
`/api/schema/` — both registered only when `DEBUG` is on.

`SECRET_KEY` is the only value you have to fill in. With `DATABASE_URL` and
`REDIS_URL` left unset, development runs on SQLite and Django's local-memory
cache — no services to install.

### Running against PostgreSQL and Redis

Production uses PostgreSQL and Redis, and some behaviour differs — notably
`select_for_update()`, which SQLite ignores. Run against the real thing before
trusting anything that depends on row locking:

```bash
docker compose up -d   # from the repo root
```

Then uncomment `DATABASE_URL` and `REDIS_URL` in `backend/.env`; the defaults
there match the credentials in `docker-compose.yml`. Setting `REDIS_URL` also
switches the cache from local-memory to Redis.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App at http://localhost:3000. The dev server binds `0.0.0.0`, so it is also
reachable from other devices on your network.

### Other commands

```bash
uv run pytest        # backend tests        (in backend/)
uv run ruff check .  # backend lint         (in backend/)
npm run build        # type-check + bundle  (in frontend/)
npm run preview      # serve the build      (in frontend/)
```

## Chosen stack

| Layer | Choice | Note |
|---|---|---|
| Backend | Django 6 + DRF | Django admin is the big win — bermudia spent ~1/3 of its frontend rebuilding it |
| DB | PostgreSQL | Required, not optional — row locking is core to correctness |
| Realtime | SSE (ASGI view + Redis Streams) | |
| Auth | Django session cookies, same domain | Avoids JWT expiry mid-contest (bermudia's 16h tokens) |
| Frontend | Vite + Vue 3 + TypeScript | Not Nuxt — no SSR/SEO value in a logged-in realtime map |
| Map | SVG + panzoom | Custom; no component library helps here |
| Server state | TanStack Query (`@tanstack/vue-query`) | |
| Client state | Pinia | |
| Routing | Vue Router | |
| Styling | Tailwind v4, native logical properties | |
| UI components | shadcn-vue (Reka UI + Tailwind) | Player HUD, dialogs, forms. Budget an RTL sweep. |

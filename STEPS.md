# kingdom-scraper — Build Steps

> Claude follows this list top to bottom, one step at a time.
> After each step: suggest commit → wait for approval → suggest push to main.

---

## Commit & Push Protocol

After every step Claude must:

1. Deliver the module + mandatory 4 sections (📦 🔗 🧪 ➡️)
2. **Stop and wait** for approval
3. On approval, suggest exact commit:
   > 💾 `type(scope): description`
4. Wait for commit approval
5. Suggest push:
   ```bash
   git checkout main && git merge --no-ff feat/<step-branch> && git push origin main
   ```
6. **Stop completely** — do not start the next step until explicitly told to

---

## Steps

### 🏗️ Step 1 — Project scaffold
**Branch:** `feat/scaffold`

Create the full directory skeleton with empty placeholder files and root-level config:

```
kingdom-scraper/
├── interface/
│   ├── app.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── dashboard.py
│   │   └── control.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   └── control.html
│   ├── static/
│   ├── Dockerfile
│   └── requirements.txt
├── engine/
│   ├── main.py
│   ├── worker.py
│   ├── crawler.py
│   ├── parser.py
│   ├── queue_manager.py
│   ├── db_writer.py
│   ├── Dockerfile
│   └── requirements.txt
├── database/
│   ├── init/
│   │   └── init.js
│   └── Dockerfile
├── shared/
│   ├── __init__.py
│   ├── models.py
│   └── constants.py
├── docker-compose.yml
├── .env.example
├── .gitignore
├── CLAUDE.md
├── STEPS.md
└── README.md
```

> Placeholder files contain only a module docstring or `# TODO`.
> `requirements.txt` files list all dependencies (pinned versions).
> `docker-compose.yml` defines all 4 services with correct networking.
> `.env.example` contains all required keys with safe default values.

💾 Suggested commit: `chore(scaffold): initialize project structure and docker-compose`

---

### 🧩 Step 2 — Shared models & constants
**Branch:** `feat/shared`

Implement `shared/models.py` and `shared/constants.py`:

- `models.py` — dataclasses: `Offer`, `Address`, `Contact`
- `constants.py` — `TARGET_URL`, collection names, Redis key names, seed URLs list

No external dependencies beyond stdlib `dataclasses` and `datetime`.

💾 Suggested commit: `feat(shared): add Offer, Address, Contact models and constants`

---

### 🔴 Step 3 — Redis queue manager
**Branch:** `feat/engine-queue`

Implement `engine/queue_manager.py`:

- `push_url(url)` — RPUSH to `queue:urls` if not in `set:visited`
- `pop_url()` — BLPOP from `queue:urls` (blocking, timeout=5s)
- `mark_visited(url)` — SADD to `set:visited`
- `is_visited(url)` — SISMEMBER on `set:visited`
- `push_many(urls)` — batch push, filters already-visited
- `increment_stat(key)` — INCR on `stats:scraped` / `stats:errors`
- `get_stats()` — returns dict with all current counters
- `set_engine_status(status)` — SET `engine:status`
- `get_engine_status()` — GET `engine:status`

💾 Suggested commit: `feat(engine): add Redis queue manager with deduplication`

---

### 🌐 Step 4 — Crawler (aiohttp)
**Branch:** `feat/engine-crawler`

Implement `engine/crawler.py`:

- `fetch_page(session, url)` — async GET with User-Agent header, returns HTML string or None on error
- `get_offer_links(html, base_url)` — extracts all `/oferta/...` links from a listing page
- `get_next_page_url(html, base_url)` — extracts pagination link if present
- Respects `REQUEST_DELAY` from env between requests
- Raises `CrawlerError` on non-200 / timeout / connection error
- Logs every fetch at DEBUG, errors at ERROR

💾 Suggested commit: `feat(engine): add async aiohttp crawler with rate limiting`

---

### 🍜 Step 5 — Parser (BeautifulSoup)
**Branch:** `feat/engine-parser`

Implement `engine/parser.py` using BeautifulSoup4:

- `parse_offer(html, url)` → `Offer` — extracts: title, category, transaction type, price, area, rooms, address fields, offer_id from URL
- `parse_contact(html)` → `Contact` — extracts: email, phone, office address from footer/contact page
- `parse_listing_urls(html, base_url)` → `list[str]` — all offer links on a listing page
- Each parser function is independent, testable in isolation
- Returns `None` (not raises) when a field is not found — never crash on missing data

💾 Suggested commit: `feat(engine): add BeautifulSoup parser for offers and contacts`

---

### 🗄️ Step 6 — MongoDB writer
**Branch:** `feat/engine-db`

Implement `engine/db_writer.py`:

- `save_offer(offer: Offer)` — upsert by `offer_id` into `offers` collection
- `save_contact(contact: Contact)` — upsert by `email` into `contacts` collection
- `get_all_offers(limit, skip)` — paginated read for Flask UI
- `get_stats()` — count of documents per collection
- `ensure_indexes()` — called once on startup: index on `offer_id`, `category`, `transaction`, `scraped_at`

💾 Suggested commit: `feat(engine): add MongoDB writer with upsert and index setup`

---

### ⚙️ Step 7 — Worker (asyncio event loop)
**Branch:** `feat/engine-worker`

Implement `engine/worker.py`:

- `run_worker(worker_id)` — entry point for a single process
- Starts asyncio event loop with `M = COROUTINES_PER_WORKER` concurrent tasks
- Each task: pop URL → fetch → parse → save → push new links → update stats
- Handles `CrawlerError` and `ParserError` gracefully — log + increment `stats:errors`, continue
- Sets `engine:status = running` on start, `stopped` on clean exit
- Exits cleanly on `KeyboardInterrupt` or when queue is empty for >30s

💾 Suggested commit: `feat(engine): add asyncio worker with coroutine pool and error handling`

---

### 🚀 Step 8 — Engine entry point (multiprocessing)
**Branch:** `feat/engine-main`

Implement `engine/main.py`:

- Reads `WORKER_COUNT` from env (default: `os.cpu_count()`)
- Seeds Redis queue with URLs from `constants.SEED_URLS`
- Spawns `N` worker processes via `multiprocessing.Pool` or `Process`
- Waits for all processes, handles `SIGTERM` / `SIGINT` gracefully
- Logs startup summary: worker count, seed URL count, target

💾 Suggested commit: `feat(engine): add multiprocessing entry point with graceful shutdown`

---

### 🖥️ Step 9 — Flask interface
**Branch:** `feat/interface`

Implement the full Flask application:

**`app.py`** — app factory, register blueprints, connect to MongoDB/Redis

**`routes/dashboard.py`**:
- `GET /` — list of scraped offers (paginated), stats summary
- `GET /offers/<offer_id>` — single offer detail

**`routes/control.py`**:
- `POST /engine/start` — push seed URLs to Redis, set status `running`
- `POST /engine/stop` — set status `stopped` (workers poll this)
- `GET /engine/status` — returns JSON with status + stats

**Templates** — clean, functional HTML with Jinja2. No JS frameworks required.
Display: offer cards with address, price, area, category badge, transaction type.

💾 Suggested commit: `feat(interface): add Flask UI with dashboard, offer list, and engine control`

---

### 🐳 Step 10 — Docker wiring & final integration
**Branch:** `feat/docker`

Finalize all Docker configuration:

- `interface/Dockerfile` — multi-stage if needed, exposes port 5000
- `engine/Dockerfile` — installs deps, runs `python main.py`
- `database/Dockerfile` — MongoDB with `init/init.js` mounted
- `docker-compose.yml` — correct `depends_on`, named network `scraper-net`, volume mounts for MongoDB and Redis persistence, all env vars from `.env`
- Verify full `docker compose up --build` works end-to-end
- Add `healthcheck` for MongoDB and Redis services

💾 Suggested commit: `chore(docker): finalize all Dockerfiles and compose wiring`

---

### 🧪 Step 11 — Smoke test & README update
**Branch:** `feat/docs`

- Manual end-to-end test: `docker compose up`, open UI, start engine, verify offers appear in dashboard
- Fix any integration issues found during smoke test
- Update `README.md` with accurate setup instructions, screenshots description, and data schema
- Add `STEPS.md` note marking all steps complete

💾 Suggested commit: `docs: final README update and smoke test sign-off`

---

## Status tracker

| Step | Description | Status |
|---|---|---|
| 1 | Project scaffold | ✅ done |
| 2 | Shared models & constants | ✅ done |
| 3 | Redis queue manager | ✅ done |
| 4 | Crawler (aiohttp) | ✅ done |
| 5 | Parser (BeautifulSoup) | ✅ done |
| 6 | MongoDB writer | ✅ done |
| 7 | Worker (asyncio) | ✅ done |
| 8 | Engine entry point (multiprocessing) | ✅ done |
| 9 | Flask interface | ✅ done |
| 10 | Docker wiring & integration | ✅ done |
| 11 | Smoke test & README update | ✅ done |
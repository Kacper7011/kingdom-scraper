# Sprawozdanie — kingdom-scraper

**Rozproszony scraper nieruchomości z kingdomelblag.pl**

Projekt indywidualny — Kacper  
Repozytorium: https://github.com/Kacper7011/kingdom-scraper

---

## Spis treści

1. [Cel i zakres projektu](#1-cel-i-zakres-projektu)
2. [Architektura systemu](#2-architektura-systemu)
3. [Schemat i profil danych](#3-schemat-i-profil-danych)
4. [Decyzje architektoniczne](#4-decyzje-architektoniczne)
5. [Wieloprocesowość — moduł multiprocessing](#5-wieloprocesowość--moduł-multiprocessing)
6. [Współbieżność — moduł asyncio](#6-współbieżność--moduł-asyncio)
7. [Redis — kolejka i deduplicacja](#7-redis--kolejka-i-deduplicacja)
8. [Parsowanie HTML — BeautifulSoup4](#8-parsowanie-html--beautifulsoup4)
9. [Baza danych — MongoDB](#9-baza-danych--mongodb)
10. [Interfejs graficzny — Flask](#10-interfejs-graficzny--flask)
11. [Konteneryzacja — Docker Compose](#11-konteneryzacja--docker-compose)
12. [Przepływ danych end-to-end](#12-przepływ-danych-end-to-end)
13. [Napotkane problemy i ich rozwiązania](#13-napotkane-problemy-i-ich-rozwiązania)
14. [Wnioski](#14-wnioski)

---

## 1. Cel i zakres projektu

Celem projektu jest zbudowanie **rozproszonej aplikacji scrapującej** dane o nieruchomościach z serwisu [kingdomelblag.pl](https://www.kingdomelblag.pl) — biura obrotu nieruchomościami działającego na rynku elbląskim.

Aplikacja realizuje następujące wymagania:

- pobieranie danych z witryny internetowej przy użyciu asynchronicznego klienta HTTP,
- parsowanie treści HTML za pomocą biblioteki BeautifulSoup4,
- przetwarzanie wieloprocesowe skalujące się na rdzenie CPU,
- składowanie danych w bazie dokumentowej MongoDB,
- deduplicacja odwiedzonych URL-i przez Redis,
- graficzny interfejs zarządzania oparty na Flask,
- podział na minimum 3 kontenery Docker.

**Profil danych** obejmuje 4 grupy tematyczne:

| # | Grupa | Przykładowe pola |
|---|---|---|
| 1 | Dane oferty | `offer_id`, `title`, `price`, `area_m2`, `rooms`, `scraped_at` |
| 2 | Klasyfikacja | `category` (mieszkanie / dom / działka / lokal), `transaction` (sprzedaż / wynajem / dzierżawa) |
| 3 | Adres nieruchomości | `street`, `city`, `region` |
| 4 | Dane kontaktowe biura | `name`, `email`, `phone`, `address` |

---

## 2. Architektura systemu

System składa się z **4 kontenerów Docker** połączonych wewnętrzną siecią `scraper-net`:

```
┌─────────────────────────────────────────────────────────────┐
│                        Docker Compose                       │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   interface  │    │    engine    │    │   mongodb    │  │
│  │  Flask :5000 │◄──►│  N workers  │◄──►│   :27017     │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│          │                  │                               │
│          └──────────────────┤                               │
│                      ┌──────▼───────┐                       │
│                      │    redis     │                       │
│                      │    :6379     │                       │
│                      └──────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

### Moduły i ich odpowiedzialności

| Moduł | Kontener | Główna odpowiedzialność |
|---|---|---|
| `engine/` | `kingdom-engine` | pobieranie, parsowanie, zapis — silnik scrapujący |
| `interface/` | `kingdom-interface` | panel zarządzania, podgląd danych |
| `database/` | `kingdom-mongodb` | trwałe składowanie ofert i kontaktów |
| `redis` (obraz oficjalny) | `kingdom-redis` | kolejka URL-i, deduplicacja, statystyki |
| `shared/` | (kopiowane do obu) | modele danych i stałe współdzielone |

### Zależności między modułami

```
interface  →  shared/models    (odczyt ofert z Mongo)
interface  →  redis            (status silnika, statystyki)
interface  →  mongodb          (odczyt kolekcji offers)

engine     →  shared/models    (tworzenie obiektów Offer, Contact)
engine     →  redis            (BLPOP/RPUSH kolejka, SADD/SISMEMBER deduplicacja)
engine     →  mongodb          (upsert ofert i kontaktów)

shared/    →  (nic nie importuje — czyste modele)
```

---

## 3. Schemat i profil danych

### Modele danych (`shared/models.py`)

Dane są reprezentowane przez dataclassy Pythona z metodami `to_dict()` / `from_dict()` umożliwiającymi konwersję do/z dokumentów MongoDB:

```python
@dataclass
class Address:
    city: str
    street: str | None = None
    region: str | None = None

@dataclass
class Offer:
    offer_id: str          # np. "986-2-2" — unikalny klucz upserta
    title: str
    category: str          # mieszkanie | dom | dzialka | lokal
    transaction: str       # sprzedaz | wynajem | dzierzawa
    url: str
    address: Address
    price: float | None = None
    area_m2: float | None = None
    rooms: int | None = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class Contact:
    name: str
    email: str             # klucz upserta w kolekcji contacts
    phone: str
    address: str
```

Zastosowanie `dataclass` zamiast zwykłych słowników daje:
- walidację typów przez type hintsy,
- czytelną reprezentację obiektów (`__repr__`),
- łatwy dostęp do pól przez atrybuty zamiast `dict["klucz"]`.

### Przykładowy dokument MongoDB (kolekcja `offers`)

```json
{
  "offer_id": "986-2-2",
  "title": "Na wynajem nowe 2-pokojowe mieszkanie na parterze",
  "category": "mieszkanie",
  "transaction": "wynajem",
  "price": 1800.0,
  "area_m2": 35.66,
  "rooms": 2,
  "address": {
    "street": "Gwiezdna",
    "city": "Elbląg",
    "region": "warmińsko-mazurskie"
  },
  "url": "https://www.kingdomelblag.pl/oferta/986-2-2/...",
  "scraped_at": { "$date": "2026-06-09T19:27:46Z" }
}
```

---

## 4. Decyzje architektoniczne

### 4.1 Dlaczego MongoDB, a nie relacyjna baza danych?

Dane nieruchomości z serwisu kingdomelblag.pl mają **niejednorodny schemat** — oferty różnych kategorii (mieszkania, domy, działki, lokale) mogą zawierać różne pola. Mieszkanie ma liczbę pokoi i piętro, działka może mieć klasę bonitacyjną, lokal może mieć metraż antresoli. Wymuszenie stałego schematu tabelarycznego (PostgreSQL, MySQL) wymagałoby albo wielu `NULL`-owalnych kolumn, albo normalizacji do wielu tabel i kosztownych JOINów.

MongoDB przechowuje dokumenty JSON bez narzuconego schematu — każda oferta może mieć inne pola, a nowe pola można dodać bez migracji. Zapis przez `update_one` z opcją `upsert=True` zapewnia idempotentność — wielokrotne scrapowanie tej samej strony nie tworzy duplikatów.

```python
# engine/db_writer.py
def save_offer(client: MongoClient, offer: Offer) -> None:
    doc = offer.to_dict()
    _offers_col(client).update_one(
        {"offer_id": offer.offer_id},   # filtr — szukaj po ID
        {"$set": doc},                   # zaktualizuj wszystkie pola
        upsert=True,                     # wstaw jeśli nie istnieje
    )
```

Indeks unikalny na `offer_id` gwarantuje integralność danych na poziomie bazy:

```javascript
// database/init/init.js
db.offers.createIndex({ offer_id: 1 }, { unique: true });
db.offers.createIndex({ category: 1 });
db.offers.createIndex({ scraped_at: -1 });
db.contacts.createIndex({ email: 1 }, { unique: true });
```

### 4.2 Dlaczego Redis jako kolejka?

Wymaganie wieloprocesowości stawia pytanie: jak N niezależnych procesów ma koordynować dostęp do puli URL-i bez duplikowania pracy?

**Podejście naiwne — współdzielona lista Python:** nie działa między procesami (każdy proces ma własną przestrzeń pamięci). Można użyć `multiprocessing.Queue`, ale działa tylko lokalnie i nie przeżywa restartu kontenera.

**Redis** rozwiązuje oba problemy:

1. **Kolejka URL-i** (`queue:urls` — typ Lista) — operacja `BLPOP` jest atomowa po stronie serwera Redis. Gdy wiele workerów jednocześnie czeka na URL, Redis gwarantuje, że każdy URL trafi do dokładnie jednego workera. Nie ma wyścig, nie ma duplikacji pracy.

2. **Deduplicacja** (`set:visited` — typ Zbiór) — `SISMEMBER` i `SADD` są operacjami O(1). Sprawdzenie czy URL był już odwiedzony i oznaczenie go jako odwiedzonego to pojedyncze wywołania Redis, bez potrzeby odpytywania bazy MongoDB.

3. **Statystyki i status** — liczniki `stats:scraped`, `stats:errors` inkrementowane przez `INCR` (atomowe) i flaga `engine:status` umożliwiają Flask UI śledzenie postępów bez odpytywania Mongo.

```python
# engine/queue_manager.py — kluczowe operacje Redis

def push_url(self, url: str) -> bool:
    if self._r.sismember(KEY_VISITED, url):   # O(1) — sprawdź odwiedzony
        return False
    self._r.rpush(KEY_QUEUE, url)              # dodaj na koniec listy
    return True

def pop_url(self, timeout: int = 5) -> str | None:
    result = self._r.blpop(KEY_QUEUE, timeout=timeout)  # blokuj do 5s
    if result is None:
        return None
    _, url = result
    return url

def mark_visited(self, url: str) -> None:
    self._r.sadd(KEY_VISITED, url)             # dodaj do zbioru
```

### 4.3 Dlaczego multiprocessing zamiast threading?

Python posiada **Global Interpreter Lock (GIL)** — mechanizm zapewniający, że w danej chwili tylko jeden wątek Pythona wykonuje bytecode. Oznacza to, że `threading` nie daje realnej równoległości dla kodu CPU-bound.

Scraping jest w dużej mierze **I/O-bound** (czekanie na odpowiedź serwera), więc GIL nie byłby problemem dla podstawowej wersji. Jednak wymaganie projektu mówi o skalowaniu na rdzenie CPU, co wymaga `multiprocessing` — każdy proces ma własny interpreter Pythona z własnym GIL.

Konfiguracja liczby procesów przez zmienną środowiskową `WORKER_COUNT` (domyślnie `os.cpu_count()`) umożliwia skalowanie do możliwości sprzętowych:

```python
# engine/main.py
def _spawn_workers(n: int) -> None:
    from worker import run_worker

    for i in range(n):
        proc = multiprocessing.Process(
            target=run_worker,
            args=(i,),
            name=f"Worker-{i}",
            daemon=False,
        )
        proc.start()
        _processes.append(proc)
```

### 4.4 Dlaczego asyncio wewnątrz każdego procesu?

Sam `multiprocessing` (bez asyncio) dałby N procesów wykonujących requesty sekwencyjnie — jeden request na raz per proces. Przy opóźnieniu `REQUEST_DELAY=1.0s` i timeoucie 30s jeden worker przetwarza ~1 URL/sekundę.

`asyncio` pozwala jednemu procesowi obsługiwać **M coroutines równocześnie**. Gdy coroutine #1 czeka na odpowiedź HTTP (`await aiohttp.get(...)`), event loop przełącza się na coroutine #2, która może w tym czasie parsować inną stronę lub pobierać kolejny URL. Czas oczekiwania na I/O jest wykorzystywany przez inne zadania.

Łączna równoległość systemu: `WORKER_COUNT × COROUTINES_PER_WORKER = 4 × 8 = 32` równoczesne zadania.

### 4.5 Dlaczego aiohttp zamiast requests?

Biblioteka `requests` jest synchroniczna — blokuje wątek do czasu otrzymania odpowiedzi. W środowisku asyncio oznaczałoby to zablokowanie całego event loop na czas trwania requestu.

`aiohttp` jest zbudowane na asyncio od podstaw — `await session.get(url)` oddaje kontrolę event loop natychmiast, bez blokowania. Jeden `aiohttp.ClientSession` może obsługiwać wiele współbieżnych połączeń.

```python
# engine/crawler.py
async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(
        url,
        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    ) as resp:
        if resp.status != 200:
            raise CrawlerError(f"HTTP {resp.status} for {url}")
        html = await resp.text(errors="replace")
    await asyncio.sleep(REQUEST_DELAY)   # grzeczne opóźnienie
    return html
```

---

## 5. Wieloprocesowość — moduł multiprocessing

### Architektura procesu głównego

`engine/main.py` jest punktem wejścia kontenera engine. Wykonuje trzy zadania:

1. **Seeduje kolejkę** — wypchnięcie startowych URL-i do Redis (9 kategorii listingów),
2. **Spawnuje N procesów** — każdy uruchamia funkcję `run_worker(i)`,
3. **Czeka na zakończenie** — `proc.join()` dla każdego procesu; obsługuje SIGTERM/SIGINT.

```python
# engine/main.py — pełny cykl życia silnika

def main() -> None:
    n = int(os.getenv("WORKER_COUNT", str(WORKER_COUNT)))

    signal.signal(signal.SIGTERM, _shutdown)   # obsługa Docker stop
    signal.signal(signal.SIGINT, _shutdown)    # obsługa Ctrl+C

    queue = QueueManager()
    _seed_queue(queue)    # RPUSH 9 seed URLs
    _spawn_workers(n)     # fork N procesów

    for proc in _processes:
        proc.join()       # czekaj na zakończenie wszystkich

    QueueManager().set_engine_status(STATUS_STOPPED)
```

### Graceful shutdown

Gdy Docker Compose wysyła SIGTERM (np. przy `docker compose down`), handler `_shutdown` ustawia flagę `engine:status = stopped` w Redis. Workery sprawdzają tę flagę w każdej iteracji pętli i kończą pracę po przetworzeniu bieżącego URL-a — bez przerywania w środku zapisu do MongoDB.

```python
def _shutdown(signum, frame) -> None:
    qm = QueueManager()
    qm.set_engine_status(STATUS_STOPPED)   # workerzy zobaczą flagę

    for proc in _processes:
        if proc.is_alive():
            proc.terminate()

    for proc in _processes:
        proc.join(timeout=10)   # daj max 10s na clean exit

    sys.exit(0)
```

### Diagram procesów

```
Docker Container: kingdom-engine
│
└── [MainProcess] main.py  (PID 1)
    ├── RPUSH seed URLs → Redis
    ├── fork Worker-0  (PID 7)  ──► asyncio event loop
    ├── fork Worker-1  (PID 8)  ──► asyncio event loop
    ├── fork Worker-2  (PID 9)  ──► asyncio event loop
    └── fork Worker-3  (PID 10) ──► asyncio event loop
        └── join() — czeka na wszystkie
```

Każdy Worker-N jest **niezależnym procesem** z własnym interpreterem Pythona, własnym połączeniem do Redis i MongoDB, własnym event loop asyncio.

---

## 6. Współbieżność — moduł asyncio

### Event loop i coroutines

Każdy proces worker uruchamia własny event loop przez `asyncio.run()`. Wewnątrz loopa M coroutines działa współbieżnie — nie równolegle (jeden wątek), ale z przełączaniem kontekstu przy każdym `await`.

```python
# engine/worker.py — uruchomienie M coroutines w jednym procesie

def run_worker(worker_id: int) -> None:
    queue = QueueManager()
    db_client = _get_client()
    ensure_indexes(db_client)
    queue.set_engine_status(STATUS_RUNNING)

    n = int(os.getenv("COROUTINES_PER_WORKER", str(COROUTINES_PER_WORKER)))

    async def _run_all() -> None:
        tasks = [_worker_loop(worker_id, queue, db_client) for _ in range(n)]
        await asyncio.gather(*tasks)   # uruchom wszystkie równocześnie

    asyncio.run(_run_all())
```

### Pętla przetwarzania URL-i

Każda coroutine wykonuje nieskończoną pętlę: pobierz URL → pobierz stronę → parsuj → zapisz → enqueue nowe linki. Przełączenie kontekstu następuje przy każdym `await`:

```python
async def _worker_loop(worker_id: int, queue: QueueManager, db_client) -> None:
    idle_ticks = 0
    async with build_session() as session:
        while True:
            # Sprawdź sygnał stop z Flask UI
            if queue.get_engine_status() == STATUS_STOPPED:
                break

            # BLPOP w thread pool — nie blokuje event loop
            url = await _pop_url_async(queue, timeout=5)

            if url is None:
                idle_ticks += 1
                if idle_ticks >= _IDLE_LIMIT:   # 30s ciszy → exit
                    break
                continue

            idle_ticks = 0
            if queue.is_visited(url):
                continue

            await _process_url(url, session, queue, db_client)
```

### Kluczowe rozwiązanie: non-blocking BLPOP

`redis-py` jest biblioteką synchroniczną. Wywołanie `blpop()` z timeoutem blokowałoby cały event loop asyncio na czas oczekiwania — inne coroutines nie mogłyby w tym czasie odbierać odpowiedzi HTTP, co prowadziło do kaskadowych timeoutów.

Rozwiązanie: `run_in_executor` uruchamia blokujące wywołanie Redis w osobnym wątku puli (`ThreadPoolExecutor`), zwracając coroutine z `await`. Event loop pozostaje wolny.

```python
async def _pop_url_async(queue: QueueManager, timeout: int = 5) -> str | None:
    """Uruchamia blokujące BLPOP w thread pool — event loop pozostaje wolny."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, queue.pop_url, timeout)
    #                                 ^^^^ domyślny ThreadPoolExecutor
```

### Diagram event loop

```
Proces Worker-0 — jeden wątek, jeden event loop
│
├── coroutine #0: await fetch_page(url_A)  ──► sieć (czeka)
│                                                │
├── coroutine #1: await fetch_page(url_B)  ──► sieć (czeka)
│                                                │
├── coroutine #2: parse_offer(html_C) ──► CPU (szybkie)
│                                                │
├── coroutine #3: await _pop_url_async()  ──► thread (BLPOP)
│                                                │
│   ← odpowiedź dla url_A wraca ←───────────────┘
│
└── coroutine #0 wznawia: save_offer() → MongoDB
```

---

## 7. Redis — kolejka i deduplicacja

### Struktury danych Redis użyte w projekcie

| Klucz Redis | Typ | Operacje | Cel |
|---|---|---|---|
| `queue:urls` | Lista | `RPUSH`, `BLPOP` | kolejka FIFO URL-i do przetworzenia |
| `set:visited` | Zbiór | `SADD`, `SISMEMBER` | deduplicacja odwiedzonych URL-i |
| `stats:scraped` | String | `INCR`, `GET` | licznik zapisanych ofert |
| `stats:errors` | String | `INCR`, `GET` | licznik błędów |
| `engine:status` | String | `SET`, `GET` | kanał komunikacji UI ↔ engine |

### Dlaczego Lista (nie inne typy)?

Redis `LIST` z operacją `BLPOP` to klasyczna kolejka producent-konsument. `BLPOP` jest **atomowe** — gdy kilka klientów jednocześnie czeka na tym samym kluczu, Redis zagwarantuje dostarczenie każdego elementu dokładnie jednemu klientowi. Nie ma wyścigu, nie można zduplikować pracy.

`RPUSH` dodaje na koniec (prawy koniec), `BLPOP` zdejmuje z początku (lewy koniec) — klasyczne FIFO. Nowe strony listingowe i linki ofert wpadają na koniec kolejki, a workery pobierają od początku.

### Dlaczego Zbiór dla visited?

`SET` (zbiór) Redis przechowuje unikalne wartości z operacją sprawdzenia `SISMEMBER` w O(1) niezależnie od liczby elementów. Dla 10 000 odwiedzonych URL-i sprawdzenie zajmuje tyle samo czasu co dla 10.

Alternatywą byłoby przechowywanie odwiedzonych URL-i w MongoDB — każda deduplicacja wymagałaby roundtripa do bazy (kilka ms). Redis odpowiada w mikrosekundach.

### Kanał komunikacji UI ↔ engine

`engine:status` to jedyny mechanizm komunikacji między kontenerem `interface` a kontenerem `engine`. Flask UI ustawia `SET engine:status stopped`, workery sprawdzają `GET engine:status` w każdej iteracji pętli i reagują na zmianę:

```python
# engine/worker.py — sprawdzenie sygnału stop
if queue.get_engine_status() == STATUS_STOPPED:
    logger.info("Worker-%d received stop signal", worker_id)
    break

# interface/routes/control.py — wysłanie sygnału stop
@control_bp.route("/engine/stop", methods=["POST"])
def engine_stop():
    _redis().set(KEY_ENGINE_STATUS, STATUS_STOPPED)
    return redirect(url_for("control.control"))
```

---

## 8. Parsowanie HTML — BeautifulSoup4

### Strategia parsowania

Strona kingdomelblag.pl ma dwa typy stron:
- **Strony listingowe** (`/oferty/kategoria`) — lista kart ofert z linkami
- **Strony ofert** (`/oferta/id/slug`) — szczegóły jednej nieruchomości

Parser (`engine/parser.py`) rozróżnia je na podstawie ścieżki URL i stosuje odpowiednią strategię:

```python
# engine/worker.py — routing na podstawie URL
if "/oferta/" in url:
    offer = parse_offer(html, url)      # parsuj stronę oferty
    contact = parse_contact(html)       # wyciągnij dane biura z footera
else:
    new_links = parse_listing_urls(html, TARGET_URL)   # wyciągnij linki
    next_page = get_next_page_url(html, url)           # paginacja
```

### Parsowanie strony oferty

Rzeczywista struktura HTML strony oferty (zweryfikowana przez inspekcję):

```html
<!-- Tytuł oferty -->
<h2>Na wynajem nowe 2-pokojowe mieszkanie na parterze</h2>

<!-- Cena -->
<p class="price">
    <span class="amout">1 800 </span>
    <span>PLN</span>
</p>

<!-- Szczegóły: powierzchnia, pokoje, piętro -->
<div class="area">Powierzchnia<strong>35.66 m<sup>2</sup></strong></div>
<div class="area">Liczba pokoi<strong>2</strong></div>

<!-- Lokalizacja -->
<h6>warmińsko-mazurskie, Elbląg, Gwiezdna</h6>
```

Parsery wyodrębniają dane regexem i metodami BeautifulSoup:

```python
def _parse_price(soup: BeautifulSoup) -> float | None:
    tag = soup.find("p", class_="price")
    if not tag:
        return None
    amount = tag.find("span", class_="amout")
    raw = re.sub(r"[^\d,\.]", "", amount.get_text())   # usuń białe znaki
    raw = raw.replace(",", ".")
    return float(raw)

def _parse_area(soup: BeautifulSoup) -> float | None:
    for div in soup.find_all("div", class_="area"):
        text = div.get_text(" ", strip=True)
        if "Powierzchnia" in text:
            match = re.search(r"([\d,\.]+)\s*m", text)
            if match:
                return float(match.group(1).replace(",", "."))
    return None
```

### Klasyfikacja oferty z URL

Kategoria i typ transakcji są zakodowane w URL-u strony oferty (np. `/oferta/986-2-2/elblag-gwiezdna-**na-wynajem**-nowe-**2-pokojowe-mieszkanie**`). Parser wyodrębnia je bez konieczności analizowania HTML:

```python
def _classify_from_url(url: str) -> tuple[str, str]:
    path = urlparse(url).path.lower()

    category_map  = {"mieszkan": "mieszkanie", "dom": "dom",
                     "dzialk": "dzialka", "lokal": "lokal"}
    transaction_map = {"sprzedaz": "sprzedaz",
                       "wynajem": "wynajem", "dzierzawa": "dzierzawa"}

    category    = next((v for k, v in category_map.items()    if k in path), "inne")
    transaction = next((v for k, v in transaction_map.items() if k in path), "sprzedaz")
    return category, transaction
```

### Parsowanie danych kontaktowych

Dane biura (email, telefon, adres) są obecne w stopce na każdej stronie serwisu — parser wyciąga je jednorazowo z dowolnej odwiedzonej strony:

```python
def parse_contact(html: str) -> Contact | None:
    soup = _soup(html)

    name_tag  = soup.find("p", class_="company")
    email_tag = soup.find("a", href=re.compile(r"^mailto:"))
    phone_tag = soup.find("a", href=re.compile(r"^tel:"))

    email = email_tag["href"].replace("mailto:", "").strip() if email_tag else ""
    phone = phone_tag.get_text(strip=True) if phone_tag else ""

    return Contact(name=..., email=email, phone=phone, address=...)
```

### Defensywne parsowanie

Każda funkcja parsera zwraca `None` zamiast rzucać wyjątek gdy pole nie zostanie znalezione — brak ceny lub powierzchni nie jest powodem do porzucenia całej oferty:

```python
def parse_offer(html: str, url: str) -> Offer | None:
    try:
        # ... parsowanie ...
        return Offer(
            price=_parse_price(soup),    # może być None
            area_m2=_parse_area(soup),   # może być None
            rooms=_parse_rooms(soup),    # może być None
            ...
        )
    except Exception as exc:
        logger.error("parse_offer failed for %s: %s", url, exc)
        return None   # nigdy nie crashujemy workera
```

---

## 9. Baza danych — MongoDB

### Uzasadnienie wyboru

MongoDB zostało wybrane z trzech powodów:

1. **Elastyczny schemat** — różne typy nieruchomości mają różne atrybuty. Brak konieczności migracji schematu przy dodaniu nowych pól.
2. **Natywny format JSON** — dane scrapowane jako Python dict trafiają bezpośrednio do MongoDB bez transformacji.
3. **Upsert atomowy** — `update_one(..., upsert=True)` w jednej operacji sprawdza istnienie i wstawia lub aktualizuje. Wielokrotne uruchomienie scrapera nie tworzy duplikatów.

### Indeksy

Indeksy tworzone przy starcie silnika (idempotentnie — bezpieczne do wielokrotnego wywołania):

```python
def ensure_indexes(client: MongoClient) -> None:
    offers = _offers_col(client)
    offers.create_index([("offer_id",   pymongo.ASCENDING)], unique=True)
    offers.create_index([("category",   pymongo.ASCENDING)])
    offers.create_index([("transaction",pymongo.ASCENDING)])
    offers.create_index([("scraped_at", pymongo.DESCENDING)])

    contacts = _contacts_col(client)
    contacts.create_index([("email", pymongo.ASCENDING)], unique=True)
```

- Indeks unikalny na `offer_id` — zapobiega duplikatom na poziomie bazy (druga linia obrony po deduplicacji Redis).
- Indeks na `scraped_at DESC` — szybkie pobieranie najnowszych ofert dla dashboardu.
- Indeks na `category` / `transaction` — podstawa przyszłego filtrowania.

### Paginacja w Flask UI

```python
def get_all_offers(client: MongoClient, limit: int = 20, skip: int = 0) -> list[dict]:
    cursor = (
        _offers_col(client)
        .find({}, {"_id": 0})          # wyklucz pole _id z wyników
        .sort("scraped_at", pymongo.DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    return list(cursor)
```

---

## 10. Interfejs graficzny — Flask

### Struktura aplikacji

Flask UI działa w oddzielnym kontenerze i komunikuje się z silnikiem wyłącznie przez Redis i MongoDB — nie ma bezpośredniego połączenia procesowego.

```python
# interface/app.py — fabryka aplikacji
def create_app() -> Flask:
    app = Flask(__name__)
    app.config["mongo_client"] = MongoClient(MONGO_URI)
    app.config["mongo_db"]     = app.config["mongo_client"][MONGO_DB]
    app.config["redis"]        = redis.Redis(host=REDIS_HOST, port=REDIS_PORT,
                                             decode_responses=True)

    from routes.dashboard import dashboard_bp
    from routes.control   import control_bp
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(control_bp)
    return app
```

### Endpointy

| Metoda | Ścieżka | Opis |
|---|---|---|
| `GET` | `/` | dashboard: lista ofert (12/stronę), statystyki |
| `GET` | `/offers/<offer_id>` | szczegóły jednej oferty |
| `GET` | `/control` | panel sterowania |
| `POST` | `/engine/start` | seeduje kolejkę + ustawia status `running` |
| `POST` | `/engine/stop` | ustawia status `stopped` |
| `POST` | `/engine/reset` | czyści kolejkę, visited set, liczniki |
| `GET` | `/engine/status` | JSON: status + wszystkie statystyki Redis |

### Live stats

Panel sterowania odpytuje `/engine/status` co 3 sekundy przez natywny `fetch` API przeglądarki — bez żadnego zewnętrznego frameworka JS:

```javascript
function refreshStats() {
    fetch('/engine/status')
        .then(r => r.json())
        .then(d => {
            document.getElementById('live-stats').innerHTML =
                '<li>Status: ' + d.status + '</li>' +
                '<li>Pobrane: ' + d.scraped + '</li>' +
                '<li>Błędy: '  + d.errors  + '</li>' + ...;
        });
}
setInterval(refreshStats, 3000);
```

---

## 11. Konteneryzacja — Docker Compose

### Struktura kontenerów

```yaml
# docker-compose.yml (fragment)
services:
  mongodb:
    build: ./database          # Mongo 7.0 + init.js
    healthcheck:
      test: mongosh --eval "db.adminCommand('ping')"
      interval: 10s

  redis:
    image: redis:7.4-alpine
    healthcheck:
      test: redis-cli ping

  engine:
    build:
      context: .               # kontekst = root projektu
      dockerfile: engine/Dockerfile
    depends_on:
      mongodb: {condition: service_healthy}
      redis:   {condition: service_healthy}

  interface:
    build:
      context: .
      dockerfile: interface/Dockerfile
    ports:
      - "${FLASK_PORT:-5000}:5000"
    depends_on:
      mongodb: {condition: service_healthy}
      redis:   {condition: service_healthy}
```

### Kluczowe decyzje Docker

**Kontekst budowania = root projektu** — obie aplikacje (engine i interface) potrzebują modułu `shared/`. Przy kontekście podkatalogu (`build: ./engine`) Docker nie ma dostępu do `../shared/`. Rozwiązanie: kontekst na poziomie root + dedykowany `Dockerfile` wskazany przez `dockerfile:`.

```dockerfile
# engine/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engine/ .          # pliki silnika do /app/
COPY shared/ ./shared/  # moduł shared dostępny jako /app/shared/
CMD ["python", "main.py"]
```

**`depends_on` z `condition: service_healthy`** — engine i interface startują dopiero gdy MongoDB i Redis przejdą healthcheck. Bez tego silnik próbowałby połączyć się z bazą przed jej inicjalizacją.

**Brak zewnętrznych portów dla MongoDB i Redis** — oba serwisy są dostępne tylko wewnątrz sieci `scraper-net`. Jedyny port eksponowany na zewnątrz to `5000` (Flask UI). Minimalizuje to powierzchnię ataku.

---

## 12. Przepływ danych end-to-end

```
1. docker compose up
   └─► MongoDB inicjalizuje kolekcje i indeksy (init.js)
   └─► engine/main.py startuje

2. main.py: RPUSH 9 seed URLs → Redis queue:urls
   ├─ /oferty/mieszkania-sprzedaz
   ├─ /oferty/domy-sprzedaz
   ├─ /oferty/dzialki-sprzedaz
   ├─ ... (6 więcej kategorii)
   └─ /kontakt

3. main.py fork → Worker-0, Worker-1, Worker-2, Worker-3

4. Każdy Worker: asyncio.gather(8 coroutines)

5. Coroutine pobiera stronę listingową:
   a. BLPOP queue:urls → url = "/oferty/mieszkania-sprzedaz"
   b. SISMEMBER set:visited → False (nowy URL)
   c. await aiohttp.get(url) → HTML listingu
   d. parse_listing_urls(html) → ["/oferta/985-2-1/...", "/oferta/986-2-2/...", ...]
   e. get_next_page_url(html) → "/oferty/mieszkania-sprzedaz?page=2"
   f. RPUSH queue:urls [oferty + paginacja]
   g. SADD set:visited url

6. Coroutine pobiera stronę oferty:
   a. BLPOP queue:urls → url = "/oferta/986-2-2/..."
   b. await aiohttp.get(url) → HTML oferty
   c. parse_offer(html, url) → Offer(offer_id="986-2-2", price=1800, ...)
   d. MongoDB update_one({"offer_id": "986-2-2"}, {$set: ...}, upsert=True)
   e. parse_contact(html) → Contact(email="biuro@kingdomelblag.pl", ...)
   f. MongoDB update_one({"email": "biuro@..."}, {$set: ...}, upsert=True)
   g. INCR stats:scraped
   h. SADD set:visited url

7. Flask UI (niezależnie od silnika):
   a. GET / → MongoDB.find().sort().skip().limit() → karty ofert
   b. GET /engine/status → Redis MGET stats → JSON
   c. POST /engine/stop → Redis SET engine:status stopped
```

---

## 13. Napotkane problemy i ich rozwiązania

### Problem 1: Blokujący BLPOP w asyncio

**Objaw:** Wszystkie HTTP requesty kończyły się timeoutem (`Timeout for https://...`). `scraped = 0`, `visited_count = 0` po 30 sekundach działania.

**Przyczyna:** Redis-py jest biblioteką synchroniczną. `blpop(timeout=5)` blokuje wątek — a co za tym idzie cały event loop asyncio — na 5 sekund. Przy 8 coroutines każda czekała kolejno na BLPOP (łącznie 40s blokady), zanim oddała kontrolę. Odpowiedzi HTTP docierały podczas blokady ale nie mogły być odczytane, co powodowało timeouty.

**Rozwiązanie:** `loop.run_in_executor(None, queue.pop_url, timeout)` — BLPOP wykonuje się w wątku puli (ThreadPoolExecutor), event loop pozostaje wolny:

```python
async def _pop_url_async(queue: QueueManager, timeout: int = 5) -> str | None:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, queue.pop_url, timeout)
```

### Problem 2: Status `stopped` ustawiany przez pierwszy kończący się worker

**Objaw:** Silnik przerywał pracę po 30 sekundach nawet gdy queue nie była pusta, bo jeden worker ustawiał `engine:status = stopped`, a pozostałe workery reagowały na tę flagę.

**Przyczyna:** Każdy `run_worker()` w bloku `finally` wywoływał `set_engine_status(STATUS_STOPPED)`. Pierwszy worker który skończył (bo np. jego 8 coroutines zdążyło przetworzyć przydzielone URL-e i trafiło na timeout BLPOP), ustawiał globalną flagę, przerywając pozostałe 3 workery.

**Rozwiązanie:** Usunięcie `set_engine_status` z bloku `finally` workera. Flagę ustawia wyłącznie `main.py` po zakończeniu wszystkich procesów (`proc.join()`).

### Problem 3: Moduł `shared/` niedostępny w kontenerze

**Objaw:** `ModuleNotFoundError: No module named 'shared'` przy starcie kontenera engine.

**Przyczyna:** `build: ./engine` kopiuje tylko zawartość katalogu `engine/` do kontenera. Katalog `shared/` jest na zewnątrz, poza kontekstem budowania.

**Rozwiązanie:** Zmiana kontekstu budowania na root projektu z dedykowanym Dockerfile:

```yaml
engine:
  build:
    context: .
    dockerfile: engine/Dockerfile
```

```dockerfile
COPY engine/ .
COPY shared/ ./shared/
```

### Problem 4: Nieprawidłowe seed URLs

**Objaw:** Silnik seedował URL-e `/mieszkania-na-sprzedaz`, które zwracały HTTP 404.

**Przyczyna:** Seed URL-e były napisane z pamięci, bez weryfikacji rzeczywistej struktury serwisu.

**Rozwiązanie:** Pobranie strony głównej i ekstrakcja linków kategorii. Rzeczywista struktura: `/oferty/mieszkania-sprzedaz` (nie `/mieszkania-na-sprzedaz`).

---

## 14. Wnioski

### Co zostało zrealizowane

Projekt spełnia wszystkie wymagania określone w specyfikacji:

- [x] Pobieranie danych z witryny internetowej (aiohttp)
- [x] 4 grupy danych (oferta, klasyfikacja, adres, kontakt)
- [x] Parsowanie HTML (BeautifulSoup4 + lxml)
- [x] Wieloprocesowość (multiprocessing, skalowanie na CPU)
- [x] Własna implementacja silnika (multiprocessing + asyncio)
- [x] Baza danych (MongoDB)
- [x] Interfejs graficzny (Flask)
- [x] Podział na min. 3 moduły/kontenery (engine, interface, mongodb, redis)

### Wyniki działania

W testach dymnych (smoke test):
- **75 ofert zapisanych w ~25 sekund** przy konfiguracji 4 workers × 8 coroutines
- Pełna odporność na duplikaty (upsert + Redis visited set)
- Czysty graceful shutdown przez sygnał Redis

### Możliwe kierunki rozwoju

| Kierunek | Opis |
|---|---|
| **Skalowanie horyzontalne** | Uruchomienie kilku instancji kontenera `engine` — każda pobiera URL-e z tej samej kolejki Redis. Redis gwarantuje brak duplikacji. |
| **Eksport danych** | Endpoint `/export/csv` lub `/export/json` w Flask UI |
| **Harmonogram** | Automatyczne uruchamianie scrapera w określonych godzinach (cron w kontenerze) |
| **Monitoring** | Integracja z Prometheus + Grafana — metryki z liczników Redis |
| **Asynchroniczny klient MongoDB** | `motor` zamiast `pymongo` — eliminacja ostatnich blokujących wywołań I/O |

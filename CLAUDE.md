# kingdom-scraper — CLAUDE.md

> Rozproszony scraper nieruchomości z kingdomelblag.pl.
> Architektura: Flask UI + silnik multiprocessing/asyncio + MongoDB + Redis, całość w Docker Compose.

---

## Tech Stack

| Warstwa | Technologia | Uwagi |
|---|---|---|
| Język | Python 3.12 | |
| Scraping | `aiohttp` + `BeautifulSoup4` | async HTTP + parsowanie HTML |
| Równoległość | `multiprocessing` + `asyncio` | procesy × coroutines |
| Kolejka zadań | `Redis` (lista + zbiór) | URL queue + deduplicacja |
| Baza danych | `MongoDB` + `pymongo` | składowanie ofert |
| Interfejs | `Flask` + `Jinja2` | panel zarządzania + podgląd danych |
| Konteneryzacja | `Docker` + `Docker Compose` | 4 kontenery |
| Konfiguracja | `python-dotenv` + `.env` | brak hardkodowanych wartości |
| Logowanie | `logging` (stdlib) | strukturowane, poziomy DEBUG/INFO/WARN/ERROR |

---

## Architektura

### Kontenery (docker-compose.yml)

```
┌─────────────────────────────────────────────────────────────┐
│                        Docker Compose                       │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   interface  │    │    engine    │    │   mongodb    │  │
│  │  Flask :5000 │◄──►│  workers    │◄──►│   :27017     │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                             │                               │
│                      ┌──────────────┐                       │
│                      │    redis     │                       │
│                      │    :6379     │                       │
│                      └──────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

### Moduły (katalogi)

- `interface/` — Flask UI: uruchamianie silnika, podgląd danych, statystyki
- `engine/` — silnik: crawler, parser, worker pool, queue manager
- `database/` — inicjalizacja MongoDB (indeksy, kolekcje)
- `shared/` — modele danych, stałe, typy wspólne dla interface i engine

### Zależności między modułami

```
interface → shared/models
engine    → shared/models
engine    → redis (queue)
engine    → mongodb (zapis)
interface → mongodb (odczyt)
interface → redis (status/statystyki)
```

`shared/` nie importuje z `interface/` ani `engine/`.

---

## Struktura projektu

```
kingdom-scraper/
│
├── interface/
│   ├── app.py                  # Flask app factory
│   ├── routes/
│   │   ├── dashboard.py        # podgląd ofert, statystyki
│   │   └── control.py          # start/stop silnika
│   ├── templates/
│   ├── static/
│   ├── Dockerfile
│   └── requirements.txt
│
├── engine/
│   ├── main.py                 # entry point, tworzy worker pool
│   ├── worker.py               # jeden proces: pętla asyncio
│   ├── crawler.py              # aiohttp: pobieranie stron
│   ├── parser.py               # BeautifulSoup: parsowanie HTML
│   ├── queue_manager.py        # Redis: RPUSH/BLPOP/SADD/SISMEMBER
│   ├── db_writer.py            # pymongo: zapis do kolekcji
│   ├── Dockerfile
│   └── requirements.txt
│
├── database/
│   ├── init/
│   │   └── init.js             # indeksy, kolekcje
│   └── Dockerfile
│
├── shared/
│   ├── models.py               # dataclasses: Offer, Contact, Address
│   └── constants.py            # TARGET_URL, nazwy kolekcji, klucze Redis
│
├── docker-compose.yml
├── .env.example
├── .gitignore
├── CLAUDE.md
└── README.md
```

---

## Schemat danych

### MongoDB — kolekcja `offers`

```python
@dataclass
class Offer:
    offer_id: str          # np. "986-2-2"
    title: str
    category: str          # mieszkanie | dom | dzialka | lokal
    transaction: str       # sprzedaz | wynajem | dzierzawa
    price: float | None
    area_m2: float | None
    rooms: int | None
    address: Address
    url: str
    scraped_at: datetime
```

### MongoDB — kolekcja `contacts`

```python
@dataclass
class Contact:
    name: str
    email: str
    phone: str
    address: str
```

### MongoDB — kolekcja `addresses`

```python
@dataclass
class Address:
    street: str | None
    city: str
    region: str | None
```

### Redis — klucze

| Klucz | Typ | Opis |
|---|---|---|
| `queue:urls` | Lista | URL-e do przetworzenia (RPUSH/BLPOP) |
| `set:visited` | Zbiór | Odwiedzone URL-e (deduplicacja) |
| `stats:scraped` | String | Licznik pobranych ofert (INCR) |
| `stats:errors` | String | Licznik błędów (INCR) |
| `engine:status` | String | `running` / `stopped` |

---

## Przepływ danych

```
1. Flask UI → RPUSH queue:urls [seed URLs]
2. engine/main.py → tworzy N = cpu_count() procesów
3. Każdy proces → uruchamia pętlę asyncio z M coroutines
4. Coroutine:
   a. BLPOP queue:urls         (pobierz URL)
   b. SISMEMBER set:visited    (czy już był?)
   c. aiohttp.get(url)         (pobierz stronę)
   d. BeautifulSoup.parse()    (wyciągnij dane)
   e. pymongo.insert()         (zapisz do MongoDB)
   f. SADD set:visited url     (oznacz jako odwiedzony)
   g. RPUSH queue:urls [nowe]  (dodaj linki z tej strony)
   h. INCR stats:scraped       (licznik)
5. Flask UI → odczyt MongoDB + Redis stats → wyświetlenie
```

---

## Grupy scrapowanych danych

| Grupa | Źródło | Kolekcja |
|---|---|---|
| **Adresy nieruchomości** | strona oferty | `offers` → `address` |
| **Dane oferty** | strona oferty | `offers` |
| **Klasyfikacja** | URL + strona oferty | `offers` → `category`, `transaction` |
| **Dane kontaktowe biura** | strona główna / kontakt | `contacts` |

---

## Reguły implementacji

- **Nigdy nie blokuj event loop** — wszystkie I/O przez `await`
- **Opóźnienie między requestami** — `asyncio.sleep(REQUEST_DELAY)` w crawlerze
- **User-Agent** — zawsze ustawiaj nagłówek w aiohttp
- **Nigdy nie hardkoduj URL-i, hostów, haseł** — tylko `.env` przez `os.getenv()`
- **Logowanie** — `logging` stdlib, nigdy `print()`. Format: `%(asctime)s [%(processName)s] %(levelname)s — %(message)s`
- **Wyjątki** — nigdy nie połykaj. Własne typy: `CrawlerError`, `ParserError`, `QueueError`
- **Rozmiar pliku** — max ~150 linii. Jedna odpowiedzialność na plik.
- **Rozmiar funkcji** — max ~30 linii. Zamiast komentarzy — czytelne nazwy funkcji.
- **Komentarze** — wyjaśniaj *dlaczego*, nie *co*. Docstring na każdej klasie publicznej.

---

## Workflow & Zasady współpracy

### Jeden moduł na raz

Moduł = jeden spójny wycinek (np. `engine/queue_manager.py`, `engine/parser.py`, cały `interface/`, itp.).  
Nigdy nie implementuj więcej niż jednego modułu na odpowiedź.

### Obowiązkowe sekcje każdej odpowiedzi z kodem

**1. 📦 Co robi** — opis plain-language + publiczne API (klasy/funkcje)  
**2. 🔗 Jak się łączy** — co importuje / co z niego korzysta / miejsce w architekturze  
**3. 🧪 Jak testować ręcznie** — kroki weryfikacji (skrypt testowy lub kroki UI)  
**4. ➡️ Co dalej** — lista logicznych następnych modułów. NIE implementuj ich.

### Stop i czekaj

Po dostarczeniu modułu + czterech sekcji: **zatrzymaj się całkowicie**. Czekaj na wyraźne zatwierdzenie.

Akceptowalne sygnały: `ok`, `wygląda dobrze`, `zatwierdzone`, `dalej`, `następny`

### Decyzje architektoniczne

Gdy dwa podejścia są równorzędne — NIE wybieraj cicho. Przedstaw:

```
⚖️ Decyzja: <temat>

Opcja A — <nazwa>
  ✅ zaleta  ❌ wada

Opcja B — <nazwa>
  ✅ zaleta  ❌ wada

→ Rekomendacja: Opcja A
```

Czekaj na wybór przed napisaniem kodu.

### Nigdy nie
- Pisz kodu dla wielu modułów w jednej odpowiedzi
- Kontynuuj bez zatwierdzenia
- Podejmuj istotne decyzje architektoniczne w ciszy
- Refaktoryzuj niezwiązany kod przy implementacji modułu
- Dodawaj niezatwierdzone zależności

---

## Git & Wersjonowanie

**Branche:** `main` (tylko stabilny) + `feat/<nazwa-modułu>` per moduł.

**Commity (Conventional Commits):** `type(scope): krótki opis`  
Typy: `feat` · `fix` · `refactor` · `style` · `test` · `docs` · `chore`

Po zatwierdzeniu sugeruj dokładny commit:
> 💾 Suggested commit: `feat(engine): add queue_manager with Redis URL deduplication`

Po zatwierdzeniu sugeruj merge (nigdy nie uruchamiaj):
```bash
git checkout main && git merge --no-ff feat/<nazwa-modułu> && git push origin main
```

**SemVer:** start od `0.1.0`.

---

## Zmienne środowiskowe (`.env`)

```env
# MongoDB
MONGO_URI=mongodb://mongodb:27017
MONGO_DB=kingdom_scraper

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Silnik
WORKER_COUNT=4
COROUTINES_PER_WORKER=8
REQUEST_DELAY=1.0
TARGET_URL=https://www.kingdomelblag.pl

# Flask
FLASK_PORT=5000
FLASK_DEBUG=false
SECRET_KEY=change_me
```
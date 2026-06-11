# kingdom-scraper

Rozproszony scraper nieruchomości oparty na danych z [kingdomelblag.pl](https://www.kingdomelblag.pl/).  
Projekt akademicki realizujący wieloprocesowe pobieranie, przetwarzanie i składowanie danych z biura nieruchomości Kingdom Elbląg.

---

## Opis projektu

Aplikacja pobiera, selekcjonuje i składuje dane o ofertach nieruchomości w 4 grupach tematycznych:

| Grupa | Przykładowe dane |
|---|---|
| **Adresy nieruchomości** | ulica, miasto, województwo |
| **Dane oferty** | cena, powierzchnia (m²), liczba pokoi, typ transakcji |
| **Klasyfikacja** | kategoria (mieszkanie / dom / działka / lokal), transakcja (sprzedaż / wynajem / dzierżawa) |
| **Dane kontaktowe biura** | email, telefon, adres biura |

---

## Architektura

Aplikacja podzielona jest na **4 kontenery Docker** komunikujące się przez wewnętrzną sieć `scraper-net`:

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

### Moduł: interface

- **Flask + Jinja2** — panel zarządzania dostępny pod `http://localhost:5000`
- Dashboard z kartami ofert (paginacja, filtrowanie po kategorii)
- Panel sterowania: start / stop silnika, reset kolejki, live stats (polling co 3 s)
- Endpoint JSON `GET /engine/status` — aktualny status + liczniki Redis

### Moduł: engine

- **multiprocessing** — `WORKER_COUNT` (domyślnie: `os.cpu_count()`) niezależnych procesów
- **asyncio** — każdy proces uruchamia `COROUTINES_PER_WORKER` współbieżnych coroutines
- **aiohttp** — asynchroniczne requesty HTTP z `User-Agent` i `REQUEST_DELAY`
- **BeautifulSoup4 + lxml** — parsowanie HTML ofert i stron listingowych
- **Redis** — kolejka BLPOP/RPUSH z deduplicacją przez `SISMEMBER`

### Moduł: database (MongoDB)

- **MongoDB 7.0** — składowanie dokumentów JSON
- Skrypt `init.js` tworzy kolekcje i indeksy przy pierwszym uruchomieniu
- Kolekcje: `offers` (indeks unikalny na `offer_id`), `contacts` (indeks na `email`)

### Shared

- `shared/models.py` — dataclassy `Offer`, `Address`, `Contact` z `to_dict()` / `from_dict()`
- `shared/constants.py` — wszystkie stałe i zmienne środowiskowe; jedyne źródło konfiguracji

---

## Przepływ danych

```
1. engine/main.py  →  RPUSH seed URLs do Redis (9 kategorii)
2. main.py         →  spawn N procesów Worker-0 … Worker-N
3. Każdy Worker    →  asyncio.gather(M coroutines)
4. Każda coroutine:
   a. BLPOP queue:urls        (non-blocking via run_in_executor)
   b. SISMEMBER set:visited   (deduplicacja)
   c. aiohttp.get(url)        (async fetch z timeoutem 30 s)
   d. BeautifulSoup.parse()   (wyciągnij dane)
   e. pymongo.update_one()    (upsert do MongoDB)
   f. SADD set:visited url    (oznacz jako odwiedzony)
   g. RPUSH queue:urls [nowe] (linki z tej strony + paginacja)
   h. INCR stats:scraped      (licznik)
5. Flask UI  →  odczyt MongoDB + Redis stats → wyświetlenie
```

---

### Uruchomienie

```bash
git clone https://github.com/Kacper7011/kingdom-scraper.git
cd kingdom-scraper
cp .env.example .env        # dostosuj wartości jeśli potrzeba
docker compose up --build
```

- Dashboard ofert: `http://localhost:5000`
- Panel sterowania: `http://localhost:5000/control`
- Status JSON: `http://localhost:5000/engine/status`

Silnik uruchamia się automatycznie i zaczyna scrapować. Możesz go zatrzymać lub zrestartować przez panel sterowania.

---

## Licencja

Projekt akademicki. Dane scrapowane wyłącznie w celach edukacyjnych.

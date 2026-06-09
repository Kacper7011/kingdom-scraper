# 🏠 kingdom-scraper

Rozproszony scraper nieruchomości oparty na danych z [kingdomelblag.pl](https://www.kingdomelblag.pl/).  
Projekt akademicki realizujący wieloprocesowe pobieranie, przetwarzanie i składowanie danych z biura nieruchomości Kingdom Elbląg.

---

## 📋 Opis projektu

Aplikacja pobiera, selekcjonuje i składuje dane o ofertach nieruchomości w 4 grupach tematycznych:

| Grupa | Przykładowe dane |
|---|---|
| 📍 **Adresy nieruchomości** | ulica, miasto, województwo |
| 💰 **Dane oferty** | cena, powierzchnia (m²), liczba pokoi, typ transakcji |
| 🏷️ **Klasyfikacja** | kategoria (mieszkanie/dom/działka/lokal), rynek (PL/BG/ES) |
| 📞 **Dane kontaktowe biura** | email, telefon, adres biura |

---

## 🏗️ Architektura

Aplikacja podzielona jest na **3 moduły**, każdy w osobnym kontenerze Docker:

```
┌─────────────────────────────────────────────────────────────┐
│                        Docker Compose                       │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   INTERFEJS  │    │    SILNIK    │    │      BD      │  │
│  │  (Flask UI)  │◄──►│  (Scraper)  │◄──►│  (MongoDB)   │  │
│  │  :5000       │    │  workers    │    │  :27017      │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                             │                               │
│                      ┌──────────────┐                       │
│                      │    REDIS     │                       │
│                      │  (kolejka)   │                       │
│                      │  :6379       │                       │
│                      └──────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

### Moduły

#### 1. Interfejs (`/interface`)
- **Flask** – panel zarządzania scrapingiem
- Podgląd zebranych danych w czasie rzeczywistym
- Uruchamianie/zatrzymywanie silnika
- Statystyki i eksport danych

#### 2. Silnik (`/engine`)
- **multiprocessing** – skalowanie na rdzenie CPU
- **asyncio** – asynchroniczne requesty HTTP
- **BeautifulSoup4** – parsowanie HTML
- **Redis** – kolejka URL-i do przetworzenia
- Worker Pool: `cpu_count()` procesów × N coroutines

#### 3. Baza danych (`/database`)
- **MongoDB** – składowanie dokumentów JSON
- Kolekcje: `offers`, `contacts`, `locations`, `meta`

---

## 🔧 Technologie

| Warstwa | Technologia |
|---|---|
| Scraping | `requests`, `aiohttp`, `BeautifulSoup4` |
| Równoległość | `multiprocessing`, `asyncio` |
| Kolejkowanie | `Redis` |
| Baza danych | `MongoDB` + `pymongo` |
| Interfejs | `Flask`, `Jinja2` |
| Konteneryzacja | `Docker`, `Docker Compose` |

---

## 🚀 Uruchomienie

### Wymagania
- Docker >= 24.0
- Docker Compose >= 2.0

### Szybki start

```bash
git clone https://github.com/<username>/kingdom-scraper.git
cd kingdom-scraper
cp .env.example .env
docker compose up --build
```

Interfejs dostępny pod: `http://localhost:5000`

---

## 📁 Struktura projektu

```
kingdom-scraper/
│
├── interface/              # Moduł UI (Flask)
│   ├── app.py
│   ├── templates/
│   ├── Dockerfile
│   └── requirements.txt
│
├── engine/                 # Moduł silnika (scraper)
│   ├── main.py
│   ├── crawler.py          # asyncio crawling
│   ├── parser.py           # BeautifulSoup parsers
│   ├── worker.py           # multiprocessing workers
│   ├── queue_manager.py    # Redis queue
│   ├── Dockerfile
│   └── requirements.txt
│
├── database/               # Moduł bazy danych
│   ├── init/
│   │   └── init.js         # inicjalizacja kolekcji i indeksów
│   └── Dockerfile
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## ⚙️ Konfiguracja (`.env`)

```env
# MongoDB
MONGO_URI=mongodb://mongodb:27017
MONGO_DB=kingdom_scraper

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Silnik
WORKER_COUNT=4          # liczba procesów (domyślnie: cpu_count)
COROUTINES_PER_WORKER=8 # liczba coroutines na proces
REQUEST_DELAY=1.0       # opóźnienie między requestami (sekundy)
TARGET_URL=https://www.kingdomelblag.pl

# Flask
FLASK_PORT=5000
FLASK_DEBUG=false
```

---

## 🗄️ Schemat danych (MongoDB)

### Kolekcja `offers`

```json
{
  "_id": "ObjectId",
  "offer_id": "986-2-2",
  "title": "Na wynajem nowe 2-pokojowe mieszkanie na parterze",
  "category": "mieszkanie",
  "transaction": "wynajem",
  "price": 1800,
  "area_m2": 35.66,
  "rooms": 2,
  "floor": 0,
  "address": {
    "street": "ul. Gwiezdna",
    "city": "Elbląg",
    "region": "warmińsko-mazurskie"
  },
  "url": "https://www.kingdomelblag.pl/oferta/986-2-2/...",
  "scraped_at": "2025-01-01T12:00:00Z"
}
```

### Kolekcja `contacts`

```json
{
  "name": "Kingdom Nieruchomości",
  "email": "biuro@kingdomelblag.pl",
  "phone": "665 850 098",
  "address": "ul. Ogólna 63A, 82-300 Elbląg"
}
```

---

## 📊 Diagram przepływu danych

```
kingdomelblag.pl
      │
      ▼
  [Seed URLs]
      │
      ▼
  Redis Queue  ◄────────────────────────┐
      │                                 │
      ▼                                 │
  Worker #1 (process)              nowe URL-e
  Worker #2 (process)    ──────────────►│
  Worker #N (process)
      │
      ▼ (asyncio coroutines)
  aiohttp fetch
      │
      ▼
  BeautifulSoup parse
      │
      ▼
  MongoDB save
      │
      ▼
  Flask UI (podgląd)
```

---

## 👥 Autorzy

- Imię Nazwisko – nr indeksu

---

## 📄 Licencja

Projekt akademicki. Dane scrapowane wyłącznie w celach edukacyjnych.  
`robots.txt` serwisu: `Disallow:` (brak ograniczeń).